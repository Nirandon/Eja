import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
class LedgerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();server.DB=Path(self.tmp.name)/'test.db';server.init()
 def tearDown(self): self.tmp.cleanup()
 def save(self,**kw):
  t=dict(date='2026-11-15',description='test',amount='100',category='Food',type='expense',account_id=1);t.update(kw)
  with server.connect() as c:
   values=server.validate(t,c);c.execute('INSERT INTO transactions(date,description,amount,category,type,account_id,destination_id,workspace_id) VALUES(?,?,?,?,?,?,?,1)',values)
 def test_transfer_conserves_total(self):
  self.save(type='transfer',destination_id=2,amount='500')
  a=server.state()['accounts'];self.assertEqual([x['balance'] for x in a],[-50000,50000,0]);self.assertEqual(sum(x['balance'] for x in a),0)
 def test_precision(self):
  self.save(amount='0.10');self.save(amount='0.20');self.assertEqual(server.state()['accounts'][0]['balance'],-30)
 def test_invalid(self):
  for amount in ['0','-1','NaN','1.001','Infinity']:
   with self.assertRaises(ValueError): self.save(amount=amount)
  with self.assertRaises(ValueError): self.save(type='transfer',destination_id=1)
  with self.assertRaises(ValueError): self.save(account_id=999)
 def test_edit_delete_reverses_balances(self):
  self.save()
  with server.connect() as c: c.execute('UPDATE transactions SET amount=9000 WHERE id=1')
  self.assertEqual(server.state()['accounts'][0]['balance'],-9000)
  with server.connect() as c: c.execute('DELETE FROM transactions')
  self.assertEqual(server.state()['accounts'][0]['balance'],0)
 def test_demo_multiple_thai(self):
  result=server.parse('วันนี้กินข้าว 120 กาแฟ 80 จ่ายจาก KBank','demo')
  self.assertEqual([t['amount'] for t in result['transactions']],[120,80]);self.assertTrue(all(t['account_id']==1 for t in result['transactions']))
 def test_demo_no_guessed_transfer_direction(self):
  result=server.parse('โอน 500 จาก KBank ไป SCB','demo');self.assertIsNone(result['transactions'][0]['account_id']);self.assertTrue(result['questions'])
if __name__=='__main__': unittest.main()
