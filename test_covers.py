import sys,tempfile,unittest,sqlite3,base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
import test_features
class CoverTests(test_features.FeatureTests):
 def test_cover_storage_scoping_and_clear(self):
  image='data:image/jpeg;base64,'+base64.b64encode(b'\xff\xd8\xfftest').decode()
  status,s=self.api('cover',dict(image=image));self.assertEqual(status,200);self.assertEqual(s['cover_image'],image);self.assertTrue(all('cover_image' not in w for w in s['workspaces']))
  _,project=self.api('workspace',dict(name='Cover Project'));self.assertIsNone(project['cover_image']);self.assertEqual(server.state()['cover_image'],image)
  self.api('cover',dict(image=None));self.assertIsNone(server.state()['cover_image'])
 def test_bad_cover_rejected(self):
  self.assertEqual(self.api('cover',dict(image='data:image/svg+xml;base64,abc'))[0],400)
  self.assertIsNone(server.state()['cover_image'])
for name in list(test_features.FeatureTests.__dict__):
 if name.startswith('test_') and name not in CoverTests.__dict__:setattr(CoverTests,name,None)
class PaletteTests(unittest.TestCase):
 def test_old_default_migrates_custom_unchanged_and_idempotent(self):
  with tempfile.TemporaryDirectory() as d:
   server.DB=Path(d)/'db'
   with sqlite3.connect(server.DB) as c:
    c.executescript("CREATE TABLE workspaces(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,theme TEXT NOT NULL);INSERT INTO workspaces VALUES(1,'Personal','#287867');INSERT INTO workspaces VALUES(2,'Custom','#ac4775');")
   server.init();s=server.state();self.assertEqual(s['workspaces'][0]['theme'],'#575d41');self.assertEqual(s['workspaces'][1]['theme'],'#ac4775')
   with server.connect() as c:c.execute("UPDATE workspaces SET theme='#287867' WHERE id=1")
   server.init();self.assertEqual(server.state()['workspaces'][0]['theme'],'#287867')
if __name__=='__main__':unittest.main()
