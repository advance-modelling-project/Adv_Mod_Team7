"""Small isolated fixtures for the static dashboard build; no Mesa model needed."""
import json
import tempfile
import unittest
from pathlib import Path
import pandas as pd
from dashboard.build_data import build_reports,build_run,find_run_files


class DashboardBuildTests(unittest.TestCase):
    def test_extracts_real_excel_structure(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/'run_baseline_2030.01.01_10.00';folder.mkdir()
            workbook=folder/'sim_log_2030.01.01_10.00.xlsx'
            with pd.ExcelWriter(workbook) as writer:
                pd.DataFrame([
                    {'Step':0,'Warehouse':'POOL_WASHED','Crate Type':'TYPE_1','Quantity':200},
                    {'Step':1,'Warehouse':'POOL_WASHED','Crate Type':'TYPE_1','Quantity':400},
                    {'Step':1,'Warehouse':'POOL_UNWASHED','Crate Type':'TYPE_1','Quantity':150},
                    {'Step':1,'Warehouse':'PRO_1','Crate Type':'TYPE_1','Quantity':900},
                    {'Step':1,'Warehouse':'RDC_REVERSE','Crate Type':'TYPE_1','Quantity':500},
                    {'Step':1,'Warehouse':'RPOS_DISPLAY','Crate Type':'TYPE_1','Quantity':100},
                ]).to_excel(writer,sheet_name='Stock',index=False)
                pd.DataFrame([{'Step':1,'Origin':'POOL','Destination':'PRO_1','Crate Type':'TYPE_1','Quantity':40},
                              {'Step':1,'Origin':'RDC','Destination':'POOL','Crate Type':'TYPE_1','Quantity':60}]).to_excel(writer,sheet_name='Flows',index=False)
                pd.DataFrame([{'Step':1,'Warehouse':'PRO_1','Crate Type':'TYPE_1','Quantity':0}]).to_excel(writer,sheet_name='Backorders',index=False)
                pd.DataFrame([{'Step':1,'screened_uls':4,'screened_backlog_uls':2,'bypassed_uls':3,'arrived_uls':7,'capacity_uls':10}]).to_excel(writer,sheet_name='Screening',index=False)
                pd.DataFrame([{'Step':1,'producer_on_time_fill_rate_pct':97.2,'pooler_on_time_fill_rate_pct':99.0}]).to_excel(writer,sheet_name='Fulfillment',index=False)
            result=build_run('baseline',workbook)
            self.assertEqual(result['series']['nodes']['pool'][-1],550)
            self.assertEqual(result['series']['flows']['pool_pro'][-1],40)
            self.assertEqual(result['series']['flows']['rdc_pool'][-1],60)
            self.assertEqual(result['metrics']['screen_utilization'],60)
            self.assertEqual(result['metrics']['bypass_rate'],42.86)
            self.assertEqual(result['metrics']['producer_fill'],97.2)
            self.assertIn('baseline',find_run_files(Path(td)))

    def test_missing_optional_sheets(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/'run_2030.01.01_10.00';folder.mkdir()
            workbook=folder/'sim_log_x.xlsx'
            with pd.ExcelWriter(workbook) as writer:
                pd.DataFrame([{'Step':0,'Warehouse':'POOL_WASHED','Crate Type':'TYPE_1','Quantity':100},
                              {'Step':1,'Warehouse':'POOL_WASHED','Crate Type':'TYPE_1','Quantity':90}]).to_excel(writer,sheet_name='Stock',index=False)
                pd.DataFrame([{'Step':1,'Origin':'POOL','Destination':'PRO_1','Crate Type':'TYPE_1','Quantity':10}]).to_excel(writer,sheet_name='Flows',index=False)
            result=build_run('baseline',workbook)
            self.assertIsNone(result['metrics']['screen_utilization'])
            self.assertFalse(result['has_fulfillment'])

    def test_reports_sanitize_html(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td)/'report.md').write_text('# Proof\n\n**Safe** <script>alert(1)</script>\n\n|A|B|\n|-|-|\n|1|2|',encoding='utf-8')
            docs=build_reports(Path(td))
            self.assertEqual(len(docs),1)
            self.assertIn('<strong>Safe</strong>',docs[0]['body'])
            self.assertNotIn('<script>',docs[0]['body'])
            self.assertIn('<table>',docs[0]['body'])


if __name__=='__main__': unittest.main()
