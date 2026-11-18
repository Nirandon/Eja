import sys,tempfile,unittest,json,io,urllib.error
from pathlib import Path
from datetime import date
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from extraction import calendar_dates,enrich
import test_features
class PreferenceAPITests(test_features.FeatureTests):
 # Inherit fixture/API helper, not the other feature cases.
 def test_default_account_scope(self):
  status,s=self.api('default-account',dict(account_id=2));self.assertEqual(status,200);self.assertEqual(s['workspaces'][0]['default_account_id'],2)
  _,s=self.api('workspace',dict(name='Project'));w=s['workspace_id'];self.assertIsNone(s['workspaces'][-1]['default_account_id']);self.assertEqual(self.api('default-account',dict(workspace_id=w,account_id=2))[0],400)
  self.assertEqual(self.api('default-account',dict(account_id=None))[0],200)
 def test_category_keywords_persist(self):
  _,s=self.api('category',dict(name='GF',keywords='แฟน, เดต'));c=next(c for c in s['category_details'] if c['name']=='GF');self.assertEqual(c['keywords'],'แฟน, เดต')
  _,s=self.api('category',dict(id=c['id'],name='GF',keywords='girlfriend'));self.assertEqual(next(c['keywords'] for c in s['category_details'] if c['name']=='GF'),'girlfriend')
 # prevent inherited test repetition
for name in list(test_features.FeatureTests.__dict__):
 if name.startswith('test_') and name not in PreferenceAPITests.__dict__:setattr(PreferenceAPITests,name,None)
class EnrichmentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();server.DB=Path(self.tmp.name)/'test';server.init()
  with server.connect() as c:
   c.execute('UPDATE workspaces SET default_account_id=1 WHERE id=1');c.execute("INSERT INTO categories(workspace_id,name,keywords) VALUES(1,'GF','แฟน, เดต')")
  self.context=server.state();self.anchor=date(2026,11,15)
 def tearDown(self):self.tmp.cleanup()
 def resolve(self,text,**kw):
  row=dict(type='expense',account_id=None,category='Other',description=text,date='2026-10-01',amount=30);row.update(kw)
  return enrich(text,dict(transactions=[row],questions=['Choose the payment account.']),self.context,self.anchor)['transactions'][0]
 def test_default_fills_missing_account(self):self.assertEqual(self.resolve('กาแฟ30')['account_id'],1)
 def test_explicit_account_overrides_default(self):self.assertEqual(self.resolve('กาแฟ30จ่ายSCB',account_id=1)['account_id'],2)
 def test_unknown_bank_does_not_use_default(self):self.assertIsNone(self.resolve('ซื้อของ30จ่ายกรุงไทย',account_id=1)['account_id'])
 def test_transfers_do_not_guess(self):self.assertIsNone(self.resolve('โอน500',type='transfer')['account_id'])
 def test_custom_keywords_override_generic(self):self.assertEqual(self.resolve('กินข้าวกับแฟน300',category='Food')['category'],'GF')
 def test_explicit_category_overrides_keywords(self):self.assertEqual(self.resolve('กินข้าวกับแฟน300 หมวด Food')['category'],'Food')
 def test_exact_corrected_example(self):
  self.context['transactions']=[dict(id=1,type='expense',description='Little gift',category='GF',account_id=2,date='2026-10-01')]
  self.assertEqual(self.resolve('Little gift')['category'],'GF');self.assertEqual(self.resolve('แก้ Little gift 40',id=1)['account_id'],2)
 def test_thai_buddhist_date(self):self.assertEqual(calendar_dates('ซื้อของวันที่15/11/2569',self.anchor),['2026-11-15'])
 def test_thai_month_and_short_year(self):self.assertEqual(calendar_dates('15 พ.ย. 69',self.anchor),['2026-11-15'])
 def test_weekday(self):self.assertEqual(calendar_dates('วันศุกร์ที่แล้ว',self.anchor),['2026-11-13'])
 def test_multiple_dates(self):self.assertEqual(calendar_dates('เมื่อวานข้าว100 วันนี้กาแฟ30',self.anchor),['2026-11-14','2026-11-15'])
 def test_image_never_invents_year(self):self.assertEqual(calendar_dates('15 พฤศจิกายน',self.anchor,image=True),[])
 def test_image_default_respects_explicit_unknown(self):
  r=enrich('',dict(transactions=[dict(type='expense',account_id=None,category='Other',description='Coffee',account_mentioned=True)],questions=[]),self.context,self.anchor,image=True);self.assertIsNone(r['transactions'][0]['account_id'])
 def test_image_default_fills_receipt(self):
  r=enrich('',dict(transactions=[dict(type='expense',account_id=None,category='Other',description='Coffee',account_mentioned=False)],questions=[]),self.context,self.anchor,image=True);self.assertEqual(r['transactions'][0]['account_id'],1)
 def test_ollama_passes_context_and_original_error(self):
  error=urllib.error.HTTPError('local',400,'Bad Request',{},io.BytesIO(b'{"error":"context exceeds 4096"}'))
  with patch('urllib.request.urlopen',side_effect=error) as call:
   with self.assertRaisesRegex(ValueError,'context exceeds 4096'):server.ollama('hello')
   self.assertEqual(json.loads(call.call_args.args[0].data)['options']['num_ctx'],8192)
if __name__=='__main__':unittest.main()
