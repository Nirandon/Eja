import json, tempfile, threading, unittest, urllib.request, urllib.error, sqlite3, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
class WorkspaceHTTPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();server.DB=Path(self.tmp.name)/'db';server.init()
  self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
  threading.Thread(target=self.http.serve_forever,daemon=True).start();self.base='http://127.0.0.1:'+str(self.http.server_port)
 def tearDown(self): self.http.shutdown();self.http.server_close();self.tmp.cleanup()
 def api(self,path,data=None):
  req=urllib.request.Request(self.base+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(req) as r:return r.status,json.loads(r.read())
  except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
 def row(self,account=1):return dict(date='2026-11-15',description='Lunch',amount='120',category='Food',type='expense',account_id=account)
 def test_workspace_isolation(self):
  status,p=self.api('workspace',{'name':'Project A'});self.assertEqual(status,200);w=p['workspace_id'];self.assertNotEqual(w,1)
  self.assertEqual([a['name'] for a in p['accounts']],['KBank','SCB','Cash'])
  self.assertEqual(self.api('save',{'workspace_id':w,'transactions':[self.row(1)]})[0],400)
  self.assertEqual(self.api('save',{'workspace_id':w,'transactions':[self.row(p['accounts'][0]['id'])]})[0],200)
  _,personal=self.api('state?workspace=1');self.assertEqual(personal['transactions'],[])
  _,project=self.api('state?workspace='+str(w));tid=project['transactions'][0]['id']
  edit=self.row();edit['id']=tid
  self.assertEqual(self.api('save',{'transactions':[edit]})[0],400)
  self.api('delete',{'id':tid})
  self.assertEqual(len(self.api('state?workspace='+str(w))[1]['transactions']),1)
 def test_atomic_batch(self):
  bad=self.row();bad['amount']='-1'
  self.assertEqual(self.api('save',{'transactions':[self.row(),bad]})[0],400)
  self.assertEqual(self.api('state')[1]['transactions'],[])
 def test_cross_origin(self):
  req=urllib.request.Request(self.base+'/api/save',data=b'{}',headers={'Content-Type':'application/json','Origin':'http://evil.example'})
  with self.assertRaises(urllib.error.HTTPError) as ctx:urllib.request.urlopen(req)
  self.assertEqual(ctx.exception.code,403)
 def test_draft_does_not_save(self):
  status,d=self.api('parse',{'mode':'demo','text':'กินข้าว 120 KBank'})
  self.assertEqual(status,200);self.assertTrue(d['transactions']);self.assertEqual(self.api('state')[1]['transactions'],[])
 def test_model_cannot_move_workspace(self):
  original=server.ollama
  server.ollama=lambda prompt:{'transactions':[dict(self.row(),workspace_id=999,id=999)],'questions':[]}
  try:
   result=server.parse('test','ai');self.assertNotIn('workspace_id',result['transactions'][0]);self.assertNotIn('id',result['transactions'][0]);self.assertTrue(result['questions'])
  finally:server.ollama=original
class MigrationTests(unittest.TestCase):
 def test_existing_ledger_moves_to_personal(self):
  with tempfile.TemporaryDirectory() as d:
   server.DB=Path(d)/'old.db'
   with sqlite3.connect(server.DB) as c:
    c.executescript("CREATE TABLE accounts(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,opening INTEGER NOT NULL DEFAULT 0);CREATE TABLE transactions(id INTEGER PRIMARY KEY,date TEXT,description TEXT,amount INTEGER,category TEXT,type TEXT,account_id INTEGER,destination_id INTEGER);INSERT INTO accounts VALUES(1,'KBank',50000);INSERT INTO transactions VALUES(1,'2026-11-15','Coffee',9000,'Drinks','expense',1,NULL);")
   server.init();server.init();s=server.state();self.assertEqual(s['accounts'][0]['balance'],41000);self.assertEqual(len(s['transactions']),1);self.assertEqual(s['workspaces'][0]['name'],'Personal')
if __name__=='__main__':unittest.main()
