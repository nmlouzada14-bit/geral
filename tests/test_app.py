import os, tempfile, unittest, io
from datetime import timedelta

TMP=tempfile.TemporaryDirectory()
os.environ['DATA_DIR']=TMP.name
os.environ['INITIAL_PASSWORD']='Initial-Test-2026!'
import app as m

class Workflow(unittest.TestCase):
    def setUp(self):
        self.client=m.app.test_client()
        with m.db() as c:
            for table in ['attachments','tasks','formats','channels','login_attempts']:
                c.execute('DELETE FROM '+table)
            c.execute('DELETE FROM users WHERE email!=?',(m.ADMIN,))
            c.execute('UPDATE users SET password=?,must_change=1',(m.generate_password_hash('Initial-Test-2026!'),))
        self.login(self.client,m.ADMIN)
        self.call('post','/password',{'current':'Initial-Test-2026!','password':'Personal-Test-2026!'},expected=200)

    def call(self,method,path,data=None,expected=200,client=None):
        r=getattr(client or self.client,method)('/api'+path,json=data,headers={'X-ContentOS':'1'})
        self.assertEqual(r.status_code,expected,r.get_json())
        return r.get_json()

    def login(self,client,email,pw='Initial-Test-2026!'):
        return self.call('post','/login',{'email':email,'password':pw},client=client)

    def state(self,client=None):
        start=m.today();end=start+timedelta(days=6)
        return self.call('get',f'/state?start={start}&end={end}',client=client)

    def channel(self):
        self.call('post','/channels',{'name':'Instagram','url':'https://instagram.com/test','color':'#3b82f6'},201)
        return self.state()['channels'][0]['id']

    def task(self,**extra):
        return self.call('post','/tasks',{'title':'Entrega','deadline':str(m.today()),'description':'Briefing https://example.com','status':'Pendente','quantity':1,**extra},201)['ids']

    def test_auth_and_admin_enforced_server_side(self):
        other=m.app.test_client()
        self.call('get','/state',expected=401,client=other)
        self.call('post','/users',{'name':'Social','email':'social@example.com','role':'Social media'},201)
        self.login(other,'social@example.com')
        self.call('get','/state',expected=403,client=other)
        self.call('post','/password',{'current':'Initial-Test-2026!','password':'Personal-Social-2026!'},client=other)
        self.call('post','/users',{'name':'Intruso','email':'x@example.com','role':'Admin'},403,client=other)
        self.assertEqual(len(self.state(other)['users']),2)
        r=other.post('/api/tasks',json={'title':'Sem proteção'})
        self.assertEqual(r.status_code,403)
        r=other.post('/api/logout',headers={'X-ContentOS':'1','Origin':'https://evil.example'})
        self.assertEqual(r.status_code,403)

    def test_recurrence_idempotency_pause_and_month_overlap(self):
        ch=self.channel();weekday=str(m.today().weekday())
        self.call('post','/formats',{'name':'Reels','channel_id':ch,'responsible_id':1,'frequency':{weekday:3},'color':'#102b55','active_from':str(m.today())},201)
        first=self.state(); self.assertEqual(len(first['tasks']),3)
        self.assertEqual([t['id'] for t in first['tasks']],[t['id'] for t in self.state()['tasks']])
        fmt=first['formats'][0]['id']
        self.call('patch',f'/formats/{fmt}',{'active':False})
        nextweek=m.today()+timedelta(days=7)
        self.assertEqual(self.call('get',f'/state?start={nextweek}&end={nextweek+timedelta(days=6)}')['tasks'],[])
        self.assertEqual(len(self.state()['tasks']),3)
        self.call('patch',f'/formats/{fmt}',{'active':True})
        self.assertEqual(len(self.call('get',f'/state?start={m.today()}&end={m.today()+timedelta(days=27)}')['tasks']),12)
        self.assertEqual(len(self.state()['tasks']),3)

    def test_bulk_frequency_shared_updates_conflicts_and_uploads(self):
        weekday=str(m.today().weekday())
        ids=self.task(quantity=5,frequency={weekday:2})
        with m.db() as c:
            rows=c.execute('SELECT deadline FROM tasks ORDER BY id').fetchall()
        self.assertEqual([r[0] for r in rows],[str(m.today())]*2+[str(m.today()+timedelta(days=7))]*2+[str(m.today()+timedelta(days=14))])
        self.call('patch',f'/tasks/{ids[0]}',{'status':'Revisão','version':1})
        self.call('patch',f'/tasks/{ids[0]}',{'status':'Postado','version':1},409)
        browser=m.app.test_client();self.login(browser,m.ADMIN,'Personal-Test-2026!')
        self.assertEqual(self.state(browser)['tasks'][0]['status'],'Revisão')
        r=self.client.post(f'/api/tasks/{ids[0]}/attachments',data={'file':(io.BytesIO(b'briefing'),'brief.txt')},headers={'X-ContentOS':'1'})
        self.assertEqual(r.status_code,201)
        a=self.state(browser)['tasks'][0]['attachments'][0]
        r=browser.get('/api/attachments/'+str(a['id']))
        self.assertEqual(r.data,b'briefing');self.assertIn('attachment',r.headers['Content-Disposition']);r.close()
        self.assertEqual(m.app.test_client().get('/api/attachments/'+str(a['id'])).status_code,401)

    def test_overdue_and_invalid_inputs(self):
        yesterday=str(m.today()-timedelta(days=1))
        ids=self.task(deadline=yesterday)
        s=self.call('get',f'/state?start={yesterday}&end={m.today()}')
        self.assertTrue(s['tasks'][0]['overdue'])
        self.call('patch',f'/tasks/{ids[0]}',{'version':1,'status':'Agendado'})
        self.assertFalse(self.call('get',f'/state?start={yesterday}&end={m.today()}')['tasks'][0]['overdue'])
        self.call('post','/tasks',{'title':'A','deadline':'invalid'},400)
        self.call('post','/tasks',{'title':'A','deadline':str(m.today()),'quantity':101},400)
        self.call('post','/channels',{'name':'Unsafe','url':'javascript:alert(1)','color':'#ffffff'},400)
        self.call('get','/state?start=2026-01-01&end=2030-01-01',expected=400)

    def test_login_rate_limit(self):
        browser=m.app.test_client()
        for _ in range(10): self.call('post','/login',{'email':'invalid@example.com','password':'wrong'},401,client=browser)
        self.call('post','/login',{'email':'invalid@example.com','password':'wrong'},429,client=browser)

    def test_health_and_persistence(self):
        self.task()
        m.init()
        self.assertEqual(len(self.state()['tasks']),1)
        self.assertEqual(self.client.get('/healthz').get_json(),{'ok':True})
        with self.client.get('/') as response: self.assertEqual(response.status_code,200)

if __name__=='__main__':unittest.main()
