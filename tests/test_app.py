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

    def test_multichannel_single_task_and_report_pdf(self):
        ch=self.channel()
        self.call('post','/channels',{'name':'YouTube','url':'https://youtube.com/example','color':'#102b55'},201)
        second=self.state()['channels'][1]['id']
        self.call('post','/formats',{'name':'Conteúdo único','channel_ids':[ch,second,ch],'responsible_id':1,'frequency':{str(m.today().weekday()):2},'active_from':str(m.today())},201)
        state=self.state()
        self.assertEqual(len(state['tasks']),2)
        self.assertEqual(state['formats'][0]['color'],'#3b82f6')
        for t in state['tasks']:self.assertEqual(t['channel_ids'],[ch,second])
        task=state['tasks'][0]
        self.call('patch',f"/tasks/{task['id']}",{'version':1,'status':'Finalizado'})
        self.assertEqual(len(self.state()['tasks']),2)
        finished=self.state()['tasks'][0]
        self.assertTrue(finished['archived']);self.assertIsNotNone(finished['completed_at'])
        query=f'?start={m.today()}&end={m.today()+timedelta(days=6)}'
        r=self.call('get','/insights'+query)['report']
        self.assertEqual((r['planned'],r['delivered'],r['pending'],r['on_time']),(2,1,1,1))
        self.assertEqual(sum(x['planned'] for x in r['channels']),4)
        self.assertEqual(r['rate'],50)
        response=self.client.get('/api/insights.pdf'+query)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.mimetype,'application/pdf')
        from pypdf import PdfReader
        pdf=PdfReader(io.BytesIO(response.data));content=''.join(page.extract_text() for page in pdf.pages)
        self.assertIn('Conteúdo único',content)
        self.assertIn('YouTube',content)
        self.assertIn('Entregas concluídas',content)
        self.assertIn('Demandas em aberto',content)
        self.assertGreaterEqual(len(pdf.pages),2)
        response.close()
        self.assertEqual(m.app.test_client().get('/api/insights.pdf'+query).status_code,401)
        # Editing a finished task preserves its completion timestamp; reopening restores it to active work.
        self.call('patch',f"/tasks/{task['id']}",{'version':2,'status':'Agendado','channel_ids':[second]})
        updated=self.call('get',f"/tasks/{task['id']}")
        self.assertEqual(updated['completed_at'],finished['completed_at'])
        self.assertEqual(updated['channel_ids'],[second])
        m.init()  # migration must not re-add the removed channel on subsequent boots
        self.assertEqual(self.call('get',f"/tasks/{task['id']}")['channel_ids'],[second])
        self.call('patch',f"/tasks/{task['id']}",{'version':3,'status':'Em andamento'})
        self.assertFalse(self.call('get',f"/tasks/{task['id']}")['archived'])
        self.assertIsNone(self.call('get',f"/tasks/{task['id']}")['completed_at'])

    def test_comments_mentions_authorship_and_read_scope(self):
        self.call('post','/users',{'name':'Paloma Teste','email':'paloma@example.com','role':'Social media'},201)
        member=next(u for u in self.state()['users'] if u['email']=='paloma@example.com')
        tid=self.task()[0]
        self.call('post',f'/tasks/{tid}/comments',{'body':'@Paloma Teste confira <script>alert(1)</script>','mentions':[member['id']], 'author_id':member['id']},201)
        browser=m.app.test_client();self.login(browser,member['email'])
        self.call('post','/password',{'current':'Initial-Test-2026!','password':'Personal-Social-2026!'},client=browser)
        comments=self.call('get',f'/tasks/{tid}/comments',client=browser)['comments']
        self.assertEqual(comments[0]['author_id'],1)
        self.assertEqual(comments[0]['mentions'][0]['id'],member['id'])
        self.assertEqual(len(self.state(browser)['mentions']),1)
        self.call('post',f'/tasks/{tid}/mentions/read')
        self.assertEqual(len(self.state(browser)['mentions']),1)  # another user cannot clear their notice
        self.call('post',f'/tasks/{tid}/mentions/read',client=browser)
        self.assertEqual(self.state(browser)['mentions'],[])
        self.call('post',f'/tasks/{tid}/comments',{'body':'No mention','mentions':[member['id']]},400)
        self.call('post',f'/tasks/{tid}/comments',{'body':'','mentions':[]},400)
        self.call('get',f'/tasks/{tid}/comments',expected=401,client=m.app.test_client())

    def test_report_range_unknown_dates_empty_and_long_pdf(self):
        old=str(m.today()-timedelta(days=2))
        self.task(deadline=old,status='Finalizado')
        query=f'?start={old}&end={old}'
        with m.db() as c:c.execute('UPDATE tasks SET completed_at=NULL')
        report=self.call('get','/insights'+query)['report']
        self.assertEqual(report['undated_delivery'],1)
        self.assertIsNone(report['on_time_rate'])
        self.assertEqual(report['overdue'],0)
        self.assertEqual(self.call('get',f'/insights?start={m.today()}&end={m.today()}')['report']['planned'],0)
        self.call('get',f'/insights?start={m.today()}&end={old}',expected=400)
        self.task(title='Título de conteúdo com acentuação <teste> & referências '*3,quantity=45)
        with self.client.get(f'/api/insights.pdf?start={m.today()}&end={m.today()}') as response:
            self.assertEqual(response.status_code,200)
            from pypdf import PdfReader
            pdf=PdfReader(io.BytesIO(response.data))
            self.assertGreater(len(pdf.pages),3)
            self.assertIn('45',''.join(p.extract_text() for p in pdf.pages))

    def test_format_edit_preserves_existing_deliveries(self):
        ch=self.channel()
        self.call('post','/formats',{'name':'Original','channel_ids':[ch],'responsible_id':1,'frequency':{str(m.today().weekday()):1},'active_from':str(m.today())},201)
        state=self.state();f=state['formats'][0];t=state['tasks'][0]
        self.call('post','/channels',{'name':'YouTube','url':'https://youtube.com/example','color':'#102b55'},201)
        second=self.state()['channels'][1]['id']
        self.call('patch',f"/formats/{f['id']}",{'name':'Novo','channel_ids':[ch,second],'responsible_id':1,'frequency':{str(m.today().weekday()):1},'active_from':str(m.today())})
        self.assertEqual(self.state()['tasks'][0]['channel_ids'],[ch])
        nextweek=m.today()+timedelta(days=7)
        new=self.call('get',f'/state?start={nextweek}&end={nextweek}')['tasks']
        self.assertEqual(len(new),1);self.assertEqual(new[0]['channel_ids'],[ch,second])
        self.call('patch',f"/tasks/{t['id']}",{'version':1,'channel_ids':[ch,second]})
        self.assertEqual(len(self.state()['tasks']),1)

if __name__=='__main__':unittest.main()
