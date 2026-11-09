/* Team 7 ORBIT. No build step, no backend, no dependencies. Data comes from published Actions artifacts. */
'use strict';
const $ = id => document.getElementById(id);
const fmt = n => (n == null || !Number.isFinite(+n)) ? '—' : Math.round(+n).toLocaleString('en-US');
const pct = n => (n == null || !Number.isFinite(+n)) ? '—' : (+n).toFixed(2)+'%';
const clamp = (n,a,b) => Math.min(b,Math.max(a,n));
const keys={pool_washed:'Pooler washed RTIs',pool_unwashed:'Pooler unwashed RTIs',producer:'Producer RTIs',rpos_display:'Retail displayed RTIs',backorders:'Outstanding backorders',producer_fill:'RDC on-time fill rate',pooler_fill:'Pooler on-time fill rate'};
const names={pool:'POOL',producer:'PRODUCERS',rdc:'RDC',rpos:'RETAIL'};
const positions=[{key:'pool',x:40,y:117,num:'01',subtitle:'Recovery & washing'}, {key:'producer',x:322,y:117,num:'07',subtitle:'Fruit producers'}, {key:'rdc',x:605,y:117,num:'01',subtitle:'Distribution center'}, {key:'rpos',x:888,y:117,num:'20',subtitle:'Retail locations'}];
const links=[{id:'pool_pro',start:'pool',end:'producer',path:'M 198 148 C 239 102, 285 102, 322 148',label:'SUPPLY',color:'#59e0d1'},{id:'pro_rdc',start:'producer',end:'rdc',path:'M 480 148 C 521 102, 565 102, 605 148',label:'FORWARD',color:'#59e0d1'},{id:'rdc_rpos',start:'rdc',end:'rpos',path:'M 763 148 C 802 102, 848 102, 888 148',label:'RETAIL',color:'#59e0d1'},{id:'rpos_rdc',start:'rpos',end:'rdc',path:'M 888 211 C 846 250, 805 250, 763 211',label:'RETURNS',color:'#f1b87d'},{id:'rdc_pool',start:'rdc',end:'pool',path:'M 605 225 C 525 350, 292 350, 198 225',label:'RETURN TO POOL',color:'#f1b87d'}];
const S={data:null,runId:'baseline',view:'overview',day:0,speed:1,playing:false,lastFrame:0,phase:0,lastPaint:0,activeReport:null,source:false,chartMetric:'pool_washed'};
let particles=[];
const run=()=>S.data?.runs?.find(r=>r.id===S.runId) || S.data?.runs?.[0] || null;
const val=(arr,day)=>Array.isArray(arr)?(+arr[clamp(day,0,arr.length-1)]||0):0;
function showNotice(message){const n=$('notice');n.textContent=message;n.classList.toggle('hidden',!message)}
function navigate(view){
  if(!$(view))return; S.view=view; document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id===view));
  document.querySelectorAll('[data-nav]').forEach(n=>n.classList.toggle('active',n.dataset.nav===view));
  $('current-section').textContent=({overview:'Overview',replay:'Simulation replay',comparison:'Scenario lab',reports:'Report library'})[view]||view;
  history.replaceState(null,'','#'+view); if(view!=='replay')pause();window.scrollTo({top:0,behavior:'instant'});
  if(view==='overview')paintOverviewChart();if(view==='comparison')paintCompareChart();if(view==='replay')paintReplay();
}
async function loadData(silent=false){
  if(!silent)$('run-status').innerHTML='<span class="live-dot"></span> Checking build';
  try{
    const response=await fetch('./data/site.json?_='+Date.now(),{cache:'no-store'});
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    const data=await response.json();
    if(!data||!Array.isArray(data.runs)||!Array.isArray(data.reports))throw new Error('Invalid published data');
    const changed=JSON.stringify([data.sha,data.generated_at])!==JSON.stringify([S.data?.sha,S.data?.generated_at]);
    S.data=data;
    if(!data.runs.some(r=>r.id===S.runId))S.runId=data.runs[0]?.id||'baseline';
    const date=new Date(data.generated_at);
    const when=Number.isFinite(+date)?date.toLocaleString('en-GB',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'UTC'})+' UTC':'unknown time';
    $('build-date').textContent=`LATEST PUBLISHED BUILD · ${when}`;
    $('side-build').textContent=`Updated ${when}\nCommit ${(data.sha||'local').slice(0,7)}`;
    $('footer-sha').textContent='Commit '+(data.sha||'local').slice(0,7);
    $('run-status').innerHTML='<span class="live-dot"></span> '+(data.runs.length?`${data.runs.length} published run${data.runs.length===1?'':'s'}`:'No published runs');
    $('overview-source').textContent=data.runs.length ? `${data.runs.length} scenario${data.runs.length===1?'':'s'} · Seed ${data.seed} · ${data.reports.length} reports` : 'No simulation workbooks published yet';
    $('report-count').textContent=String(data.reports.length); $('report-list-count').textContent=String(data.reports.length);
    showNotice(data.runs.length?'':'No run snapshots have been published yet. A successful Actions build will populate the animated replay.');
    if(changed){renderOverview();renderScenarioOptions();renderComparison();renderReportList();paintReplay();}
  }catch(error){
    $('run-status').textContent='No published data';
    if(!S.data){showNotice('The dashboard is installed, but the generated data bundle is not available yet. Check the GitHub Actions deployment and Pages settings.');renderOverview();renderComparison();renderReportList();}
    else if(!silent){showNotice(`Could not refresh: ${error.message}. Showing the most recently loaded build.`)}
  }
}
function kpi(label,value,foot,color=''){return `<div class="kpi-card"><div class="card-caption">${label}</div><div class="number ${color}">${value}</div><div class="card-foot">${foot}</div></div>`}
function renderOverview(){
  const r=run();const m=r?.metrics||{};
  $('overview-kpis').innerHTML=[
    kpi('Pooler screening',pct(m.screen_utilization),'Share of available daily capacity','aqua'),
    kpi('RDC order service',pct(m.producer_fill),'On-time quantity fill rate','blue'),
    kpi('Pooler order service',pct(m.pooler_fill),'On-time quantity fill rate',''),
    kpi('Recovery bypass',pct(m.bypass_rate),'Share of new arriving unit loads','amber')].join('');
  paintOverviewChart();
}
function renderScenarioOptions(){
  const r=S.data?.runs||[];
  $('replay-scenario').innerHTML=r.length?r.map(x=>`<option value="${x.id}">${x.name}</option>`).join(''):'<option>No runs available</option>';
  $('replay-scenario').value=S.runId;
}
function renderComparison(){
  const runs=S.data?.runs||[];
  $('comparison-legend').innerHTML=runs.map((r,i)=>`<span><i class="scenario-color" style="background:${i%2?'#f3b678':'#59e0d1'}"></i>${r.name} · ${r.days} days</span>`).join('');
  const cols=[['producer_fill','RDC on-time quantity fill','%',true],['pooler_fill','Pooler on-time quantity fill','%',true],['screen_utilization','Screening capacity used','%',false],['bypass_rate','Arrival bypass rate','%',false],['pool_washed_mean','Average washed pool stock','RTIs',false],['pool_unwashed_mean','Average unwashed pool stock','RTIs',false],['total_returned','Return flow, RDC → POOL','RTIs',false],['total_dispatched','Outflow, POOL → PRO','RTIs',false],['pooler_overdue','Overdue pooler orders','RTIs',false],['detention_pool','Pooler completed-stay detention','days',false],['detention_pro','Producer completed-stay detention','days',false],['return_dispatch_ratio','Returns / Pooler dispatches','%',false]];
  const [a,b]=runs;
  $('comparison-grid').innerHTML=cols.map(([key,label,unit])=>{
    const x=a?.metrics?.[key],y=b?.metrics?.[key],exists=x!=null&&y!=null;
    const format=v=>unit==='%'?pct(v):unit==='days'?(v==null?'—':(+v).toFixed(2)+' d'):fmt(v);
    const diff=exists?y-x:null;
    const delta=diff==null?'Awaiting two comparable runs':`${diff>0?'+':''}${unit==='%'?diff.toFixed(2)+' percentage points':unit==='days'?diff.toFixed(2)+' days':Math.round(diff).toLocaleString('en-US')+' RTIs'} · RFID − baseline`;
    return `<div class="compare-card"><div class="caption">${label}</div><div class="compare-values"><div><small>${a?.name||'BASELINE'}</small><strong>${format(x)}</strong></div><div><small>${b?.name||'TRACEABILITY'}</small><strong class="accent">${format(y)}</strong></div></div><div class="compare-delta"><b>Δ</b> ${delta}</div></div>`;
  }).join('');
  paintCompareChart();
}
function seriesFor(r,key){if(!r)return[]; if(key==='backorders')return r.series.backorders||[];if(key==='producer_fill')return r.series.fulfillment?.producer_on_time_fill_rate_pct||[];if(key==='pooler_fill')return r.series.fulfillment?.pooler_on_time_fill_rate_pct||[];if(key==='detention_pool')return r.series.detention?.pool||[];if(key==='detention_pro')return r.series.detention?.pro||[];return r.series.stocks?.[key]||[]}
function drawLineChart(canvas,sets,unit='RTIs'){
  if(!canvas)return;
  const rect=canvas.getBoundingClientRect();if(rect.width<10)return;
  const dpr=Math.min(window.devicePixelRatio||1,2),h=250,w=rect.width;
  canvas.width=Math.floor(w*dpr);canvas.height=Math.floor(h*dpr);
  const ctx=canvas.getContext('2d'); ctx.scale(dpr,dpr);
  ctx.clearRect(0,0,w,h);
  const L=50,T=24,R=16,B=35,pw=w-L-R,ph=h-T-B;
  const values=sets.flatMap(s=>s.values.filter(Number.isFinite));
  let max=Math.max(1,...values),min=Math.min(0,...values);
  max=max*1.1; const span=Math.max(1,max-min);
  ctx.font='10px DM Sans, sans-serif';ctx.lineWidth=1;
  for(let i=0;i<=4;i++){
    const y=T+i*ph/4,v=max-i*span/4;
    ctx.strokeStyle='#27364c';ctx.beginPath();ctx.moveTo(L,y);ctx.lineTo(w-R,y);ctx.stroke();
    ctx.fillStyle='#7a8fae';ctx.textAlign='right';ctx.fillText(v>=10000?`${(v/1000).toFixed(0)}k`:v>=1000?`${(v/1000).toFixed(1)}k`:v.toFixed(v<10?1:0),L-8,y+4);
  }
  const days=Math.max(1,...sets.map(s=>s.values.length-1));
  ctx.textAlign='center';ctx.fillStyle='#7a8fae';
  for(let i=0;i<=4;i++){const x=L+i*pw/4;ctx.fillText(String(Math.round(i*days/4)),x,h-12)}
  sets.forEach((s,idx)=>{
    if(!s.values.length)return;
    ctx.beginPath();ctx.lineWidth=idx===0?2.8:2.3;ctx.lineJoin='round';ctx.strokeStyle=s.color;
    s.values.forEach((v,i)=>{const x=L+(i/days)*pw,y=T+ph-(v-min)/span*ph; if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});
    ctx.stroke();
    if(idx===0){const day=clamp(S.day,0,s.values.length-1),x=L+day/days*pw;
      ctx.strokeStyle='#b8cff655';ctx.setLineDash([4,5]);ctx.beginPath();ctx.moveTo(x,T);ctx.lineTo(x,T+ph);ctx.stroke();ctx.setLineDash([]);
      ctx.fillStyle=s.color;ctx.beginPath();ctx.arc(x,T+ph-(s.values[day]-min)/span*ph,4,0,Math.PI*2);ctx.fill();
    }
  });
  ctx.fillStyle='#6c819f';ctx.textAlign='left';ctx.fillText(`DAY / ${unit}`,L,12);
}
function paintOverviewChart(){
  const r=run();$('overview-chart-empty').classList.toggle('hidden',!!r);
  if(r)drawLineChart($('overview-chart'),[{values:seriesFor(r,$('overview-metric').value),color:'#62e0d3'}]);
}
function paintCompareChart(){
  const runs=S.data?.runs||[]; $('compare-chart-empty').classList.toggle('hidden',runs.length>=2);
  const key=$('compare-metric').value;const units=key.includes('fill')?'%':key.includes('detention')?'days':'RTIs';
  if(runs.length)drawLineChart($('compare-chart'),runs.slice(0,4).map((r,i)=>({values:seriesFor(r,key),color:['#5ce1d2','#f4bb7e','#7caaff','#ce90ef'][i]})),units);
}
function svgEl(name,attrs={},text=''){
  const e=document.createElementNS('http://www.w3.org/2000/svg',name);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,String(v));if(text)e.textContent=text;return e;
}
function initNetwork(){
 const f=$('network-flows'),n=$('network-nodes'),p=$('network-particles');f.replaceChildren();n.replaceChildren();p.replaceChildren();particles=[];
 for(const l of links){
   const path=svgEl('path',{id:'flow-'+l.id,d:l.path,fill:'none',stroke:l.color,'stroke-width':2.6,opacity:.55,'stroke-linecap':'round'});f.append(path);
   const labelPos=path.getPointAtLength(path.getTotalLength()*.52);
   f.append(svgEl('text',{x:labelPos.x,y:labelPos.y+(l.id==='rdc_pool'?23:-16),fill:'#8196b3','font-size':10,'font-family':'DM Sans,sans-serif','text-anchor':'middle','letter-spacing':1.7},l.label));
   for(let i=0;i<4;i++){
     const c=svgEl('circle',{r:i===0?4.5:3.1,fill:l.color,opacity:.0,filter:'url(#softglow)'});p.append(c);particles.push({circle:c,path,l,offset:i/4});
   }
 }
 for(const pos of positions){
   const g=svgEl('g',{'data-node':pos.key});g.append(svgEl('rect',{x:pos.x,y:pos.y,width:160,height:115,rx:15,fill:'#182941',stroke:'#36516e','stroke-width':1.3}));
   g.append(svgEl('rect',{x:pos.x+14,y:pos.y+15,width:29,height:27,rx:8,fill:'#224859'}));
   g.append(svgEl('text',{x:pos.x+28,y:pos.y+33,fill:'#65e4d2','font-size':11,'font-weight':700,'font-family':'Space Grotesk','text-anchor':'middle'},pos.num));
   g.append(svgEl('text',{x:pos.x+52,y:pos.y+33,fill:'#dae8fb','font-size':11,'font-weight':700,'font-family':'DM Sans','letter-spacing':1},names[pos.key]));
   g.append(svgEl('text',{x:pos.x+14,y:pos.y+68,fill:'#f2f9ff','font-size':25,'font-weight':700,'font-family':'Space Grotesk','data-value':pos.key},'—'));
   g.append(svgEl('text',{x:pos.x+14,y:pos.y+94,fill:'#839bb8','font-size':10,'font-family':'DM Sans'},'RTIs · '+pos.subtitle));
   n.append(g);
 }
}
function paintReplay(){
 const r=run();if(!r)return;
 S.day=clamp(S.day,0,r.days);$('day-range').max=r.days;$('day-range').value=S.day;$('day-range').style.setProperty('--progress',`${100*S.day/r.days}%`);
 $('scrub-day').textContent=String(S.day);$('replay-day-label').textContent=`DAY ${S.day} / ${r.days}`;$('timeline-end').textContent='DAY '+r.days;
 $('scrub-status').textContent=S.playing?'Replay in progress':(S.day===r.days?'End of simulation':'Drag to inspect a day');
 for(const pos of positions){const el=$('network-nodes').querySelector(`[data-value="${pos.key}"]`);if(el)el.textContent=fmt(val(r.series.nodes[pos.key],S.day))}
 const sc=r.series.screening,fu=r.series.fulfillment;
 const metrics=[['Daily return volume',fmt(val(r.series.flows.rdc_pool,S.day))+' RTIs'],['New loads screened',fmt(val(sc.screened_uls,S.day))+' ULs'],['Recovered backlog',fmt(val(sc.screened_backlog_uls,S.day))+' ULs'],['Overdue pooler orders',r.has_fulfillment?fmt(val(fu.pooler_outstanding_due_rtis,S.day))+' RTIs':'—']];
 $('replay-stats').innerHTML=metrics.map(([t,v])=>`<div class="replay-stat"><small>${t}</small><strong>${v}</strong></div>`).join('');
 const flowLabels={pool_pro:'POOL → PRO',pro_rdc:'PRO → RDC',rdc_rpos:'RDC → RPOS',rpos_rdc:'RPOS → RDC',rdc_pool:'RDC → POOL'};
 const maxFlow=Math.max(1,...Object.values(r.series.flows).map(a=>val(a,S.day)));
 $('flow-bars').innerHTML=links.map(l=>{const n=val(r.series.flows[l.id],S.day);return `<div><div class="flow-bar-label"><span>${flowLabels[l.id]}</span><strong>${fmt(n)}</strong></div><div class="flow-track"><div class="flow-fill ${l.id.includes('rpos_rdc')||l.id==='rdc_pool'?'reverse':''}" style="width:${100*n/maxFlow}%"></div></div></div>`}).join('');
 $('replay-footnote').textContent=`Data source: ${r.source}. Each day represents a completed simulation step; movements between the four echelons are aggregated across seven producers and twenty stores.`;
 paintOverviewChart();if(S.view==='comparison')paintCompareChart();updateParticles();
}
function updateParticles(){
 const r=run();if(!r)return;
 for(const p of particles){
   const flow=val(r.series.flows[p.l.id],S.day);
   if(!flow||S.day===0){p.circle.setAttribute('opacity','0');continue}
   const progress=(S.phase*.00006+p.offset)%1;
   const point=p.path.getPointAtLength(progress*p.path.getTotalLength());
   p.circle.setAttribute('cx',point.x);p.circle.setAttribute('cy',point.y);
   p.circle.setAttribute('opacity',Math.min(.92,.35+flow/18000));
 }
}
function pause(){S.playing=false;$('play').textContent='▶';$('play').setAttribute('aria-label','Play replay')}
function play(){if(!run())return; if(S.day>=run().days)S.day=0; S.playing=true;S.lastFrame=0;$('play').textContent='Ⅱ';$('play').setAttribute('aria-label','Pause replay');requestAnimationFrame(animationFrame)}
function animationFrame(now){
 if(!S.playing)return;
 if(!S.lastFrame)S.lastFrame=now;
 const elapsed=Math.min(160,now-S.lastFrame);S.lastFrame=now;S.phase+=elapsed*S.speed;
 if(now-S.lastPaint>1000/S.speed){S.lastPaint=now;S.day++;if(S.day>=run().days){S.day=run().days;pause()}paintReplay()}
 updateParticles();if(S.playing)requestAnimationFrame(animationFrame);
}
function renderReportList(){
 const items=S.data?.reports||[],q=$('report-search').value.trim().toLowerCase();
 const displayed=items.filter(r=>`${r.title} ${r.path} ${r.raw}`.toLowerCase().includes(q));
 $('report-list-count').textContent=displayed.length;
 $('report-items').innerHTML=displayed.map(r=>`<button class="report-item ${r.id===S.activeReport?'selected':''}" data-report="${r.id}"><strong>${escapeHtml(r.title)}</strong><small>${escapeHtml(r.path)} · ${(r.size/1024).toFixed(1)} KB</small></button>`).join('')||'<p style="color:#899db7;padding:10px">No matching reports yet.</p>';
 document.querySelectorAll('[data-report]').forEach(el=>el.onclick=()=>openReport(el.dataset.report));
 if(!S.activeReport&&items.length)openReport(items[0].id);
 else if(S.activeReport)openReport(S.activeReport,false);
}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function openReport(id,resetSource=true){
 const report=S.data?.reports?.find(r=>r.id===id);if(!report)return;
 S.activeReport=id;if(resetSource)S.source=false;
 $('toggle-source').textContent=S.source?'View rendered':'View source';
 $('report-body').innerHTML=S.source?`<pre class="markdown-source">${escapeHtml(report.raw)}</pre>`:report.body;
 document.querySelectorAll('[data-report]').forEach(e=>e.classList.toggle('selected',e.dataset.report===id));
 $('report-body').scrollTop=0;
 // Links in user-supplied reports may only open safely in a new tab.
 $('report-body').querySelectorAll('a').forEach(a=>{a.target='_blank';a.rel='noopener noreferrer'});
}
async function copyReport(){const report=S.data?.reports?.find(r=>r.id===S.activeReport);if(!report)return;try{await navigator.clipboard.writeText(report.raw);$('copy-report').textContent='Copied!';setTimeout(()=>$('copy-report').textContent='Copy Markdown',1200)}catch{showNotice('Clipboard access unavailable. Use View source to select and copy the Markdown.')}}
function initialize(){
 document.querySelectorAll('[data-nav]').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.nav)));
 document.querySelectorAll('[data-goto]').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.goto)));
 $('refresh').onclick=()=>loadData();
 $('overview-metric').onchange=paintOverviewChart;
 $('compare-metric').onchange=paintCompareChart;
 $('replay-scenario').onchange=e=>{pause();S.runId=e.target.value;S.day=0;renderOverview();paintReplay()};
 $('day-range').oninput=e=>{pause();S.day=+e.target.value;paintReplay()};
 $('play').onclick=()=>S.playing?pause():play();
 $('step-back').onclick=()=>{pause();S.day=Math.max(0,S.day-1);paintReplay()};
 $('step-forward').onclick=()=>{pause();S.day=Math.min(run()?.days||365,S.day+1);paintReplay()};
 $('speed').onchange=e=>{S.speed=+e.target.value};
 $('report-search').oninput=renderReportList;
 $('toggle-source').onclick=()=>{S.source=!S.source;openReport(S.activeReport,false)};
 $('copy-report').onclick=copyReport;
 window.addEventListener('resize',()=>{if(S.view==='overview')paintOverviewChart();if(S.view==='comparison')paintCompareChart()});
 document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();else loadData(true)});
 setInterval(()=>{if(!document.hidden)loadData(true)},60000);
 initNetwork(); navigate(['overview','replay','comparison','reports'].includes(location.hash.slice(1))?location.hash.slice(1):'overview'); loadData();
}
window.addEventListener('DOMContentLoaded',initialize);
