"""Build a self-contained, read-only GitHub Pages site from Team 7 simulation workbooks.

Usage: python dashboard/build_data.py --runs-root . --reports analysis/reports
       --site dashboard/site --output dashboard/dist --sha "$GITHUB_SHA"

No simulation or GitHub API calls happen here; the workflow supplies the workbooks.
"""
from __future__ import annotations
import argparse
import datetime as dt
import html
import json
import re
import shutil
from pathlib import Path

import pandas as pd


def to_number(value):
    if pd.isna(value):
        return 0
    return float(value) if isinstance(value, float) and not value.is_integer() else int(value)


def normalized_table(path: Path, name: str) -> pd.DataFrame:
    try:
        df = pd.read_excel(path, sheet_name=name)
    except ValueError:
        return pd.DataFrame()
    if 'Step' in df.columns:
        df['Step'] = pd.to_numeric(df['Step'], errors='coerce')
        df = df.dropna(subset=['Step']).copy()
        df['Step'] = df['Step'].astype(int)
    return df


def daily_group(df: pd.DataFrame, days: list[int], column: str, select=None) -> list[int | float]:
    if df.empty or column not in df.columns:
        return [0 for _ in days]
    filtered = df if select is None else df.loc[select(df)].copy()
    if filtered.empty:
        return [0 for _ in days]
    values = pd.to_numeric(filtered[column], errors='coerce').fillna(0)
    grp = values.groupby(filtered['Step']).sum()
    return [to_number(grp.get(day, 0)) for day in days]


def single_col(df: pd.DataFrame, days: list[int], key: str):
    if df.empty or key not in df:
        return [0 for _ in days]
    s = df.drop_duplicates('Step', keep='last').set_index('Step')[key]
    return [to_number(s.get(day, 0)) for day in days]


def find_run_files(root: Path):
    grouped = {}
    for f in root.glob('run_*/sim_log_*.xlsx'):
        folder = f.parent.name.lower()
        if folder.startswith('run_traceability_'):
            scenario = 'traceability'
        else:
            scenario = 'baseline' if folder.startswith('run_baseline_') or folder.startswith('run_') else folder
        if scenario not in grouped or (f.stat().st_mtime, f.name) > (grouped[scenario].stat().st_mtime, grouped[scenario].name):
            grouped[scenario] = f
    return dict(sorted(grouped.items()))


def build_run(key: str, path: Path):
    st = normalized_table(path, 'Stock')
    fl = normalized_table(path, 'Flows')
    bo = normalized_table(path, 'Backorders')
    sc = normalized_table(path, 'Screening')
    fu = normalized_table(path, 'Fulfillment')
    det = normalized_table(path, 'Detention')
    if st.empty or fl.empty:
        raise ValueError(f'Missing Stock/Flows data in {path}')
    max_day = int(st.Step.max())
    if max_day < 1:
        raise ValueError(f'No operating days in {path}')
    days = list(range(0, max_day + 1))
    # These are *snapshot* inventories; the RDC forward transit buffer is not modeled as held stock.
    stock_by = lambda pred: daily_group(st, days, 'Quantity', lambda d: pred(d['Warehouse'].astype(str)))
    pool_washed = stock_by(lambda w: w.eq('POOL_WASHED'))
    pool_unwashed = stock_by(lambda w: w.eq('POOL_UNWASHED'))
    pool_buffer = stock_by(lambda w: w.eq('POOL_BUFFER'))
    producer = stock_by(lambda w: w.str.startswith('PRO_'))
    rdc = stock_by(lambda w: w.eq('RDC_REVERSE'))
    rpos_display = stock_by(lambda w: w.eq('RPOS_DISPLAY'))
    rpos_reverse = stock_by(lambda w: w.eq('RPOS_REVERSE'))
    pool = [a+b+c for a,b,c in zip(pool_washed, pool_unwashed, pool_buffer)]
    rpos = [a+b for a,b in zip(rpos_display, rpos_reverse)]
    def flow(origin, dest):
        return daily_group(fl, days, 'Quantity', lambda d: origin(d['Origin'].astype(str)) & dest(d['Destination'].astype(str)))
    flows = {
        'pool_pro': flow(lambda s:s.eq('POOL'), lambda s:s.str.startswith('PRO_')),
        'pro_rdc': flow(lambda s:s.str.startswith('PRO_'), lambda s:s.eq('RDC')),
        'rdc_rpos': flow(lambda s:s.eq('RDC'),lambda s:s.eq('RPOS')),
        'rpos_rdc': flow(lambda s:s.eq('RPOS'),lambda s:s.eq('RDC')),
        'rdc_pool': flow(lambda s:s.eq('RDC'),lambda s:s.eq('POOL')),
    }
    backorders = daily_group(bo, days, 'Quantity') if not bo.empty else [0]*len(days)
    screening = {name:single_col(sc,days,name) for name in ['arrived_uls','screened_uls','screened_backlog_uls','bypassed_uls','processed_uls','capacity_uls','utilization_pct']}
    # Current pool screening admission means new arrivals; historical workbook may lack backlog field.
    fulfillment = {name:single_col(fu,days,name) for name in ['producer_on_time_fill_rate_pct','pooler_on_time_fill_rate_pct','producer_outstanding_due_rtis','pooler_outstanding_due_rtis','producer_late_rtis','pooler_late_rtis']}
    detentions = {}
    if not det.empty and {'Node','Average Days','Step'}.issubset(det.columns):
        for node in ['pool','pro','r_dc','r_pos']:
            detentions[node]=daily_group(det,days,'Average Days',lambda d:d['Node'].astype(str).eq(node))
    elif not det.empty:
        for node in ['pool','pro','r_dc','r_pos']:
            col = next((c for c in det.columns if c == f'{node}_average_days' or c == f'{node}|average_days'),None)
            detentions[node]=single_col(det,days,col) if col else [0]*len(days)
    else:
        detentions={x:[0]*len(days) for x in ['pool','pro','r_dc','r_pos']}
    def safe_pct(num,den):
        return round(100*num/den,2) if den else None
    screened = sum(screening['screened_uls'][1:])+sum(screening['screened_backlog_uls'][1:])
    capacity = sum(screening['capacity_uls'][1:])
    arrivals = sum(screening['arrived_uls'][1:])
    bypasses = sum(screening['bypassed_uls'][1:])
    has_sc = not sc.empty
    has_fu = not fu.empty
    detention_means = {}
    for node in ['pool', 'pro', 'r_dc', 'r_pos']:
        t=f'{node}|total_days'
        dep=f'{node}|departures'
        if t in det.columns and dep in det.columns:
            d=det.loc[det.Step>0]
            total_days=float(pd.to_numeric(d[t],errors='coerce').fillna(0).sum())
            departures=float(pd.to_numeric(d[dep],errors='coerce').fillna(0).sum())
            detention_means[node]=round(total_days/departures,2) if departures else None
        else:
            detention_means[node]=None
    metrics = {
        'detention_pool':detention_means['pool'],
        'detention_pro':detention_means['pro'],
        'detention_rdc':detention_means['r_dc'],
        'detention_retail':detention_means['r_pos'],
        'return_dispatch_ratio':round(100*sum(flows['rdc_pool'][1:])/sum(flows['pool_pro'][1:]),2) if sum(flows['pool_pro'][1:]) else None,
        'screen_utilization':safe_pct(screened,capacity) if has_sc else None,
        'bypass_rate':safe_pct(bypasses,arrivals) if has_sc else None,
        'producer_fill':round(fulfillment['producer_on_time_fill_rate_pct'][-1],2) if has_fu else None,
        'pooler_fill':round(fulfillment['pooler_on_time_fill_rate_pct'][-1],2) if has_fu else None,
        'producer_overdue':int(fulfillment['producer_outstanding_due_rtis'][-1]) if has_fu else None,
        'pooler_overdue':int(fulfillment['pooler_outstanding_due_rtis'][-1]) if has_fu else None,
        'pool_washed_mean':round(sum(pool_washed[1:])/max_day),
        'pool_unwashed_mean':round(sum(pool_unwashed[1:])/max_day),
        'total_returned':int(sum(flows['rdc_pool'][1:])),
        'total_dispatched':int(sum(flows['pool_pro'][1:])),
    }
    return {
      'id':key, 'name': {'baseline':'Baseline','traceability':'RFID Traceability'}.get(key,key.replace('_',' ').title()),
      'source':path.parent.name,'days':max_day,'has_screening':has_sc,'has_fulfillment':has_fu,'has_detention':not det.empty,
      'metrics':metrics,
      'series':{'day':days,'nodes':{'pool':pool,'producer':producer,'rdc':rdc,'rpos':rpos},
                'stocks':{'pool_washed':pool_washed,'pool_unwashed':pool_unwashed,'pool_buffer':pool_buffer,
                          'producer':producer,'rdc_reverse':rdc,'rpos_display':rpos_display,'rpos_reverse':rpos_reverse},
                'flows':flows,'backorders':backorders,'screening':screening,'fulfillment':fulfillment,
                'detention':detentions},
    }


def build_reports(folder:Path):
    result=[]
    if not folder.exists(): return result
    try:
        import mistune
        import bleach
    except ImportError as ex:
        raise SystemExit('For report rendering install: pip install mistune bleach') from ex
    allowed = set(bleach.sanitizer.ALLOWED_TAGS)|{'h1','h2','h3','h4','h5','h6','p','pre','code','hr','table','thead','tbody','tr','th','td','div','span','img','del','input'}
    attrs={'a':['href','title'], 'img':['src','alt','title'], 'th':['align'],'td':['align'],'input':['type','checked','disabled']}
    # Do not allow external images in reports: only safe text formatting and safe links.
    allowed.remove('img')
    for path in sorted(folder.rglob('*.md')):
        raw=path.read_text(encoding='utf-8')
        rendered=mistune.create_markdown(plugins=['table'])(raw)
        clean=bleach.clean(rendered,tags=allowed,attributes=attrs,protocols=['https','http','mailto'],strip=True)
        title=next((line.lstrip('# ').strip() for line in raw.splitlines() if line.startswith('# ')),path.stem.replace('_',' ').title())
        result.append({'id':path.stem,'title':title,'path':path.as_posix(), 'body':clean,'raw':raw,
                       'size':len(raw),'group':'Report'})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs-root',type=Path,default=Path('.'))
    p.add_argument('--reports',type=Path,default=Path('analysis/reports'))
    p.add_argument('--site',type=Path,default=Path('dashboard/site'))
    p.add_argument('--output',type=Path,default=Path('dashboard/dist'))
    p.add_argument('--sha',default='local')
    p.add_argument('--seed',type=int,default=42)
    args=p.parse_args()
    if args.output.exists():shutil.rmtree(args.output)
    shutil.copytree(args.site,args.output)
    (args.output/'data').mkdir(exist_ok=True)
    runs=[]
    for key,path in find_run_files(args.runs_root).items():
        print(f'Building scenario {key} from {path}')
        runs.append(build_run(key,path))
    if not runs:
        print('No simulation workbooks found; publishing reports with an empty-simulation state.')
    bundle={'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
            'sha':args.sha,'seed':args.seed,'runs':runs,'reports':build_reports(args.reports)}
    out=args.output/'data'/'site.json'
    out.write_text(json.dumps(bundle,separators=(',',':'),ensure_ascii=False,allow_nan=False),encoding='utf-8')
    (args.output/'.nojekyll').touch()
    print(f'Published {len(runs)} scenarios, {len(bundle["reports"])} reports; {out.stat().st_size:,} bytes -> {out}')

if __name__=='__main__':main()
