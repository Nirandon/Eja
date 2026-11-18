import base64,sys,json,tempfile,unittest,urllib.request,urllib.error,threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from reports import monthly_report
class FeatureTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();server.DB=Path(self.tmp.name)/'test.db';server.init()
  self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=self.http.serve_forever,daemon=True).start();self.base='http://127.0.0.1:'+str(self.http.server_port)
 def tearDown(self):self.http.shutdown();self.http.server_close();self.tmp.cleanup()
 def api(self,path,data=None):
  r=urllib.request.Request(self.base+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(r) as response:return response.status,json.loads(response.read())
  except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
 def plan(self,**kw):
  d=dict(month='2027-01',total='1000',notes='Keep it simple',limits=[dict(category='Food',amount='500')],items=[dict(description='Dinner',category='Food',amount='100')]);d.update(kw);return self.api('plan',d)
 def test_plans_persist_and_do_not_change_ledger(self):
  status,s=self.plan();self.assertEqual(status,200);self.assertEqual(s['plans'][0]['total'],100000);self.assertEqual(s['accounts'][0]['balance'],0);self.assertEqual(s['transactions'],[])
  server.init();self.assertEqual(server.state()['plans'][0]['items'][0]['amount'],10000)
  self.assertEqual(self.plan(total='0',limits=[])[1]['plans'][0]['total'],0)
  self.assertIsNone(self.plan(total='')[1]['plans'][0]['total'])
 def test_invalid_plan_rolls_back(self):
  self.plan()
  for kw in [dict(total='NaN'),dict(total='-1'),dict(month='2027-13'),dict(limits=[dict(category='notmine',amount=1)]),dict(items=[dict(description='',category='Food',amount=1)])]:self.assertEqual(self.plan(**kw)[0],400)
  self.assertEqual(server.state()['plans'][0]['total'],100000)
 def test_custom_category_rename_updates_plans_and_transactions(self):
  _,s=self.api('category',dict(name='Party'));cid=next(c['id'] for c in s['category_details'] if c['name']=='Party')
  self.api('save',dict(transactions=[dict(date='2027-01-01',description='Fun',category='Party',amount=100,type='expense',account_id=1)]))
  self.plan(limits=[dict(category='Party',amount=500)],items=[dict(description='More fun',category='Party',amount=100)])
  status,s=self.api('category',dict(id=cid,name='GF'));self.assertEqual(status,200);self.assertEqual(s['transactions'][0]['category'],'GF');self.assertEqual(s['plans'][0]['limits'][0]['category'],'GF');self.assertEqual(s['plans'][0]['items'][0]['category'],'GF');self.assertEqual(s['accounts'][0]['balance'],-10000)
  self.assertEqual(self.api('category',dict(name='gf'))[0],400)
  other=next(c['id'] for c in s['category_details'] if c['name']=='Other');self.assertEqual(self.api('category',dict(id=other,name='Misc'))[0],400)
 def test_theme_notes_and_plans_are_workspace_specific(self):
  self.api('theme',dict(color='#ac4775'));self.api('reminder',dict(text='Call GF',due='2027-01-01'));self.plan()
  _,project=self.api('workspace',dict(name='csiiarsa'));w=project['workspace_id'];self.assertEqual(project['plans'],[]);self.assertEqual(project['reminders'],[]);self.assertEqual(next(s for s in project['workspaces'] if s['id']==w)['theme'],'#575d41')
  personal=self.api('state?workspace=1')[1];self.assertEqual(personal['reminders'][0]['text'],'Call GF');self.assertEqual(personal['workspaces'][0]['theme'],'#ac4775')
  rid=personal['reminders'][0]['id'];self.assertEqual(self.api('reminder',dict(workspace_id=w,id=rid,text='attack'))[0],400)
  self.api('reminder/delete',dict(workspace_id=w,id=rid));self.assertEqual(len(server.state()['reminders']),1)
  self.assertEqual(self.api('theme',dict(color='red;display:none'))[0],400)
  self.assertEqual(self.api('reminder',dict(text='test',due='2027-02-30'))[0],400)
 def test_reminder_edit_done_delete(self):
  _,s=self.api('reminder',dict(text='Pay rent'));rid=s['reminders'][0]['id']
  _,s=self.api('reminder',dict(id=rid,text='Paid rent',done=True));self.assertEqual(s['reminders'][0]['done'],1)
  self.api('reminder/delete',dict(id=rid));self.assertEqual(server.state()['reminders'],[])
 def test_balance_snapshots_not_income_or_spending(self):
  date=str(server.today());payload=dict(balances=[dict(account_id=1,date=date,amount='500',reason='Screenshot')])
  status,s=self.api('balance',payload);self.assertEqual(status,200);self.assertEqual(s['accounts'][0]['balance'],50000);self.assertEqual(s['transactions'],[])
  _,s=self.api('balance',payload);self.assertEqual(s['accounts'][0]['balance'],50000);self.assertEqual(s['adjustments'][0]['delta'],0)
  self.api('balance/delete',dict(id=s['adjustments'][-1]['id']));self.assertEqual(server.state()['accounts'][0]['balance'],0)
 def test_balance_scope_and_batch_rollback(self):
  _,s=self.api('workspace',dict(name='Other'));w=s['workspace_id']
  self.assertEqual(self.api('balance',dict(workspace_id=w,balances=[dict(account_id=1,date=str(server.today()),amount=100)]))[0],400)
  self.assertEqual(self.api('balance',dict(balances=[dict(account_id=1,date=str(server.today()),amount=100),dict(account_id=999,date=str(server.today()),amount=100)]))[0],400)
  self.assertEqual(server.state()['adjustments'],[])
 def test_pdf_report_has_selected_workspace_month_and_escapes_text(self):
  self.api('reminder',dict(text='Private note not for report'))
  self.api('save',dict(transactions=[dict(date='2026-11-15',description='<script>alert(1)</script> กาแฟ',category='Drinks',amount=30,type='expense',account_id=1)]))
  html=monthly_report(server.state(),'2026-11');self.assertIn('THB 30.00',html);self.assertIn('กาแฟ',html);self.assertIn('&lt;script&gt;',html);self.assertNotIn('<script>alert(1)</script>',html);self.assertNotIn('Private note not for report',html)
  with urllib.request.urlopen(self.base+'/report?month=2026-11&workspace=1') as r:self.assertEqual(r.status,200);self.assertIn('window.print()',r.read().decode())
 def test_image_validation_and_proposals_never_write(self):
  self.assertEqual(self.api('vision',dict(image='bad'))[0],400)
  # Model is mocked; this tests pipeline validation, not real visual recognition.
  image=base64.b64encode(b'\x89PNG\r\n\x1a\nFAKE').decode()
  fake=dict(transactions=[dict(id=99,workspace_id=9,date='2569-11-15',description='กาแฟ',amount=30,category='Drinks',account_id=999,type='expense')],balances=[dict(date='unreadable',amount=500,account_id=1)],questions=['Choose account'])
  with patch.object(server,'ollama',return_value=fake):
   status,r=self.api('vision',dict(image=image));self.assertEqual(status,200);self.assertEqual(r['transactions'][0]['date'],'2026-11-15');self.assertIsNone(r['transactions'][0]['account_id']);self.assertNotIn('id',r['transactions'][0]);self.assertIsNone(r['balances'][0]['date']);self.assertEqual(server.state()['transactions'],[]);self.assertEqual(server.state()['adjustments'],[])
if __name__=='__main__':unittest.main()
