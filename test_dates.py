import sys,tempfile,unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
class DateAmountTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();server.DB=Path(self.tmp.name)/'db';server.init()
 def tearDown(self):self.tmp.cleanup()
 def parse(self,text,**overrides):
  draft=dict(date='2026-10-30',description='สกุชชี่',amount=None,category='Shopping',type='expense',account_id=None,destination_id=None);draft.update(overrides)
  with patch.object(server,'today',return_value=date(2026,11,15)),patch.object(server,'ollama',return_value={'transactions':[draft],'questions':[]}):return server.parse(text,'ai')['transactions'][0]
 def test_no_date_defaults_to_bangkok_today(self):self.assertEqual(self.parse('ซื้อสกุชชี่30')['date'],'2026-11-15')
 def test_bare_purchase_number_is_baht(self):self.assertEqual(self.parse('ซื้อสกุชชี่30')['amount'],30)
 def test_yesterday(self):self.assertEqual(self.parse('เมื่อวานซื้อสกุชชี่ 30')['date'],'2026-11-14')
 def test_day_before_yesterday(self):self.assertEqual(self.parse('เมื่อวานซืนซื้อสกุชชี่30')['date'],'2026-11-13')
 def test_relative_month_boundary(self):
  with patch.object(server,'today',return_value=date(2026,11,1)):
   r=server.normalize_drafts('เมื่อวานซื้อกาแฟ 30',{'transactions':[{'date':'2026-11-1','amount':30}],'questions':[]},{'transactions':[]})
  self.assertEqual(r['transactions'][0]['date'],'2026-10-31')
 def test_explicit_october_not_overwritten(self):self.assertEqual(self.parse('วันที่ 30 ตุลาคม ซื้อสกุชชี่ 30',amount=30)['date'],'2026-10-30')
 def test_duration_is_not_assumed_price(self):self.assertIsNone(self.parse('ซื้อคอร์สเรียน 30 วัน')['amount'])
 def test_edit_retains_original_date(self):
  with server.connect() as c:c.execute("INSERT INTO transactions(date,description,amount,category,type,account_id,workspace_id) VALUES('2026-10-02','สกุชชี่',2000,'Shopping','expense',1,1)")
  self.assertEqual(self.parse('แก้ราคาสกุชชี่เป็น30บาท',id=1)['date'],'2026-10-02')
 def test_multiple_dates_not_flattened(self):
  r=server.normalize_drafts('เมื่อวานกินข้าว120 วันนี้กาแฟ80',{'transactions':[{'date':'2026-11-14','amount':120},{'date':'2026-11-15','amount':80}],'questions':[]},{'transactions':[]})
  self.assertEqual([x['date'] for x in r['transactions']],['2026-11-14','2026-11-15'])
 def test_invalid_date_requires_review(self):self.assertIsNone(self.parse('วันที่30กุมภาพันธ์ ซื้อสกุชชี่30',date='2026-02-30')['date'])
if __name__=='__main__':unittest.main()
