import json, os, sqlite3, subprocess, sys, tempfile, unittest
from pathlib import Path

class Migration(unittest.TestCase):
    def test_existing_database_is_backed_up_and_migrated_once(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)/'data';data.mkdir()
            env={**os.environ,'DATA_DIR':str(data),'INITIAL_PASSWORD':'Migration-Test-2026!','PYTHONPATH':str(root)}
            with sqlite3.connect(data/'contentos.sqlite') as c:
                c.executescript((root/'tests/fixtures/schema_v1.sql').read_text())
                c.execute("INSERT INTO users VALUES(1,'Admin','nmlouzada14@gmail.com','Administrador','preserve-this-hash',0)")
                c.execute("INSERT INTO channels VALUES(1,'Canal legado','https://example.com','#3b82f6')")
                c.execute("INSERT INTO formats VALUES(1,'Formato legado',1,1,'#aabbcc','{}','2026-01-01',0)")
                c.execute("INSERT INTO tasks(title,deadline,channel_id,format_id,status) VALUES('Não perder','2026-10-26',1,1,'Postado')")
                c.execute("INSERT INTO attachments(task_id,name,disk) VALUES(1,'anexo.txt','preservado')")
            run="""
import app
app.init()
with app.db() as c:
 assert c.execute('PRAGMA user_version').fetchone()[0]==5
 assert c.execute('SELECT password FROM users').fetchone()[0]=='preserve-this-hash'
 assert c.execute('SELECT title FROM tasks').fetchone()[0]=='Não perder'
 assert c.execute('SELECT completed_at FROM tasks').fetchone()[0] is None
 assert c.execute('SELECT name FROM attachments').fetchone()[0]=='anexo.txt'
 assert c.execute('SELECT count(*) FROM task_channels').fetchone()[0]==1
 assert c.execute('SELECT count(*) FROM format_channels').fetchone()[0]==1
"""
            subprocess.run([sys.executable,'-c',run],cwd=root,env=env,check=True,capture_output=True)
            backup=Path(env['DATA_DIR'])/'backups/before-v2.sqlite'
            self.assertTrue(backup.exists())
            with sqlite3.connect(backup) as c:
                self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],0)
                self.assertEqual(c.execute('SELECT title FROM tasks').fetchone()[0],'Não perder')
            before=backup.read_bytes()
            subprocess.run([sys.executable,'-c',run],cwd=root,env=env,check=True,capture_output=True)
            self.assertEqual(before,backup.read_bytes())

    def test_v2_responsible_backfill_and_restart(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            env={**os.environ,'DATA_DIR':folder,'INITIAL_PASSWORD':'Migration-Test-2026!','PYTHONPATH':str(root)}
            run="""
import app
with app.db() as c:
 c.execute("INSERT INTO tasks(title,deadline,status,responsible_id) VALUES('Legada','2026-10-26','Pendente',1)")
 c.execute('DROP TABLE task_responsibles')
 c.execute('DROP TABLE format_responsibles')
 c.execute('PRAGMA user_version=2')
app.init()
with app.db() as c:
 assert list(c.execute('SELECT user_id FROM task_responsibles'))[0][0]==1
 c.execute('DELETE FROM task_responsibles')
 c.execute('UPDATE tasks SET responsible_id=NULL')
app.init()
with app.db() as c:
 assert c.execute('SELECT count(*) FROM task_responsibles').fetchone()[0]==0
"""
            subprocess.run([sys.executable,'-c',run],cwd=root,env=env,check=True,capture_output=True)
            with sqlite3.connect(Path(folder)/'backups/before-v3.sqlite') as c:
                self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],2)
                self.assertEqual(c.execute('SELECT responsible_id FROM tasks').fetchone()[0],1)
