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
            for table in ['task_requests','attachments','tasks','formats','channels','login_attempts']:
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

    def test_bulk_status_atomicity_dates_and_validation(self):
        ids=self.task(quantity=2)
        overdue=self.task(deadline=str(m.today()-timedelta(days=1)))[0]
        selected=[{'id':tid,'version':1} for tid in ids+[overdue]]
        payload={'tasks':selected,'status':'Criado'}
        self.call('post','/tasks/bulk-status',payload,401,client=m.app.test_client())
        for items in [[],[{'id':True,'version':1}],selected*2,selected*200]:
            self.call('post','/tasks/bulk-status',{'tasks':items,'status':'Criado'},400)
        self.call('post','/tasks/bulk-status',{'tasks':selected,'status':'Agendado'},400)
        result=self.call('post','/tasks/bulk-status',payload)
        self.assertEqual(result['updated'],3)
        first=self.call('get',f'/tasks/{ids[0]}');stamp=first['completed_at']
        self.assertIsNotNone(stamp)
        self.call('patch',f'/tasks/{ids[1]}',{'version':2,'status':'Postado'})
        self.call('post','/tasks/bulk-status',{'tasks':[{'id':tid,'version':2} for tid in ids],'status':'Revisão'},409)
        self.assertEqual(self.call('get',f'/tasks/{ids[0]}')['status'],'Criado')
        self.call('post','/tasks/bulk-status',{'tasks':[{'id':ids[0],'version':2}],'status':'Postado'})
        self.assertEqual(self.call('get',f'/tasks/{ids[0]}')['completed_at'],stamp)
        result=self.call('post','/tasks/bulk-status',{'tasks':[{'id':overdue,'version':2},{'id':ids[0],'version':3}],'status':'Em andamento'})
        self.assertEqual(result['overdue'],1)
        self.assertEqual(self.call('get',f'/tasks/{overdue}')['status'],'Atrasado')
        self.assertIsNone(self.call('get',f'/tasks/{ids[0]}')['completed_at'])
        self.assertEqual(self.call('get',f'/tasks/{ids[0]}')['status'],'Em andamento')
        self.assertEqual(self.call('get',f'/tasks/{ids[1]}')['status'],'Postado')

    def test_whatsapp_delivery_deduplication_and_reentry(self):
        from unittest.mock import patch
        from notifications import process_once
        self.call('patch','/users/1/whatsapp',{'whatsapp':'+55 (11) 99999-9999'})
        self.call('post','/users',{'name':'Editor','email':'editor@example.com','role':'Editor','whatsapp':'5521999999999'},201)
        uid=next(u['id'] for u in self.state()['users'] if u['email']=='editor@example.com')
        tid=self.task(deadline=str(m.today()-timedelta(days=1)),responsible_ids=[1,uid])[0]
        sent=[]
        def sender(config,number,body):
            sent.append((number,body));return 'sent','provider-id'
        env={'WHATSAPP_NOTIFICATIONS_ENABLED':'1','EVOLUTION_API_KEY':'test-only-key'}
        with patch.dict(os.environ,env):
            process_once(sender);process_once(sender);m.init();process_once(sender)
            self.assertEqual(len(sent),2)
            self.assertIn(f'/?task={tid}',sent[0][1]);self.assertIn('Entrega',sent[0][1])
            t=self.call('get',f'/tasks/{tid}')
            self.call('patch',f'/tasks/{tid}',{'version':t['version'],'status':'Criado'})
            t=self.call('get',f'/tasks/{tid}')
            self.call('patch',f'/tasks/{tid}',{'version':t['version'],'status':'Revisão'})
            process_once(sender);self.assertEqual(len(sent),4)
            info=self.call('get','/integrations/whatsapp')
            self.assertEqual(info['counts']['sent'],4)
            self.assertNotIn('test-only-key',str(info))
        member=m.app.test_client();self.login(member,'editor@example.com')
        self.call('post','/password',{'current':'Initial-Test-2026!','password':'Personal-Editor-2026!'},client=member)
        self.call('patch','/users/1/whatsapp',{'whatsapp':'5511999999999'},403,client=member)
        self.call('get','/integrations/whatsapp',expected=403,client=member)
        self.assertTrue(all('whatsapp' not in u for u in self.state(member)['users']))
        self.call('patch','/users/1/whatsapp',{'whatsapp':'not-a-number'},400)

    def test_whatsapp_background_overdue_disabled_cancel_and_uncertain(self):
        from unittest.mock import patch
        from notifications import process_once
        self.call('patch','/users/1/whatsapp',{'whatsapp':'5511999999999'})
        tid=self.task(responsible_ids=[1])[0]
        day=m.today();calls=[]
        def sender(*args):calls.append(args);return 'uncertain','Timeout'
        with patch.dict(os.environ,{'WHATSAPP_NOTIFICATIONS_ENABLED':'0','EVOLUTION_API_KEY':'test-only-key'}):
            process_once(sender)
        self.assertFalse(calls)
        with patch.dict(os.environ,{'WHATSAPP_NOTIFICATIONS_ENABLED':'1','EVOLUTION_API_KEY':'test-only-key'}),patch.object(m,'today',return_value=day+timedelta(days=1)):
            process_once(sender);process_once(sender)
            self.assertEqual(len(calls),1)
            with m.db() as c:
                self.assertEqual(c.execute('SELECT status FROM tasks WHERE id=?',(tid,)).fetchone()[0],'Atrasado')
                self.assertEqual(c.execute('SELECT state FROM overdue_notifications').fetchone()[0],'uncertain')
        # Explicit 429 responses retry, but a task completed before retry is cancelled.
        tid2=self.task(responsible_ids=[1],status='Atrasado')[0]
        with patch.dict(os.environ,{'WHATSAPP_NOTIFICATIONS_ENABLED':'1','EVOLUTION_API_KEY':'test-only-key'}):
            process_once(lambda *args:('retry','429'))
            self.call('patch',f'/tasks/{tid2}',{'version':1,'status':'Postado'})
            process_once(sender)
            with m.db() as c:
                self.assertEqual(c.execute('SELECT state FROM overdue_notifications WHERE task_id=?',(tid2,)).fetchone()[0],'cancelled')
        self.assertEqual(len(calls),1)

    def test_notification_queue_concurrent_workers_and_retry(self):
        from unittest.mock import patch
        from concurrent.futures import ThreadPoolExecutor
        from notifications import process_once
        self.call('patch','/users/1/whatsapp',{'whatsapp':'5511999999999'})
        self.task(responsible_ids=[1],status='Atrasado')
        calls=[]
        def sender(*args): calls.append(args);return 'sent','confirmed'
        with patch.dict(os.environ,{'WHATSAPP_NOTIFICATIONS_ENABLED':'1','EVOLUTION_API_KEY':'test-only-key'}):
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda _:process_once(sender),range(2)))
            self.assertEqual(len(calls),1)
            self.task(responsible_ids=[1],status='Atrasado')
            process_once(lambda *args:('retry','429'))
            with m.db() as c:c.execute("UPDATE overdue_notifications SET next_attempt=0 WHERE state='retry'")
            process_once(sender)
            self.assertEqual(len(calls),2)
            with m.db() as c:self.assertEqual(c.execute("SELECT count(*) FROM overdue_notifications WHERE state='sent'").fetchone()[0],2)

    def test_evolution_payload_and_error_handling_without_network(self):
        from unittest.mock import patch,MagicMock
        from urllib.error import HTTPError,URLError
        from notifications import configuration,send_message
        with patch.dict(os.environ,{'WHATSAPP_NOTIFICATIONS_ENABLED':'1','EVOLUTION_API_KEY':'test-only-key'}):
            config=configuration()
        opener=MagicMock();response=opener.open.return_value.__enter__.return_value
        response.read.return_value=b'{"key":{"id":"confirmed"}}'
        with patch('notifications.request.build_opener',return_value=opener):
            self.assertEqual(send_message(config,'5511999999999','Test'),('sent','confirmed'))
            req=opener.open.call_args.args[0]
            self.assertEqual(req.full_url,'https://evolution-api-evolution-api.2dxvsk.easypanel.host/message/sendText/zayedd')
            import json
            self.assertEqual(json.loads(req.data),{'number':'5511999999999','text':'Test','linkPreview':False})
            for code,state in [(401,'failed'),(429,'retry'),(500,'uncertain')]:
                opener.open.side_effect=HTTPError(req.full_url,code,'error',{},None)
                self.assertEqual(send_message(config,'5511999999999','Test')[0],state)
            opener.open.side_effect=URLError('timeout')
            self.assertEqual(send_message(config,'5511999999999','Test')[0],'uncertain')

    def test_channel_edit_delete_preserves_history_and_pauses_orphans(self):
        ch=self.channel()
        self.call('post','/channels',{'name':'YouTube','url':'https://youtube.com/test','color':'#123456'},201)
        ch2=self.state()['channels'][-1]['id']
        base={'name':'Formato','responsible_id':1,'frequency':{str(m.today().weekday()):1},'active_from':str(m.today())}
        for ids in [[ch],[ch,ch2]]:
            self.call('post','/formats',{**base,'channel_ids':ids},201)
        state=self.state();tid=state['tasks'][0]['id']
        self.call('patch',f'/channels/{ch}',{'name':'Instagram editado','url':'https://example.com','color':'#abcdef'})
        self.assertTrue(all(f['color']=='#abcdef' for f in self.state()['formats']))
        result=self.call('delete',f'/channels/{ch}')
        self.assertEqual(result['paused_formats'],1)
        state=self.state();orphan=next(f for f in state['formats'] if not f['channel_ids'])
        self.assertFalse(orphan['active'])
        self.call('patch',f"/formats/{orphan['id']}",{'active':True},400)
        t=self.call('get',f'/tasks/{tid}')
        self.assertIn(ch,t['channel_ids'])
        self.call('patch',f'/tasks/{tid}',{'status':'Criado','version':t['version']})
        self.call('post','/tasks',{'title':'Invalid','deadline':str(m.today()),'channel_ids':[ch]},400)
        self.call('delete',f'/channels/{ch}',expected=404)
        later=m.today()+timedelta(days=7)
        new=self.call('get',f'/state?start={later}&end={later}')['tasks']
        self.assertEqual(len(new),1);self.assertEqual(new[0]['channel_ids'],[ch2])

    def test_task_delete_bulk_atomic_cleanup_and_idempotency(self):
        payload={'request_id':'delete-request-123456','quantity':2}
        ids=self.task(**payload)
        self.call('post',f'/tasks/{ids[0]}/comments',{'body':'Comentário'},201)
        r=self.client.post(f'/api/tasks/{ids[0]}/attachments',data={'file':(io.BytesIO(b'attachment'),'note.txt')},headers={'X-ContentOS':'1'})
        self.assertEqual(r.status_code,201)
        with m.db() as c: disk=c.execute('SELECT disk FROM attachments WHERE task_id=?',(ids[0],)).fetchone()[0]
        self.assertTrue((m.DATA/'uploads'/disk).exists())
        self.call('delete',f'/tasks/{ids[0]}',expected=401,client=m.app.test_client())
        for invalid in [[],[True],[-1],list(range(1,502))]:
            self.call('post','/tasks/bulk-delete',{'ids':invalid},400)
        self.call('post','/tasks/bulk-delete',{'ids':[ids[0],9999999]},409)
        self.assertEqual(len(self.state()['tasks']),2)
        result=self.call('post','/tasks/bulk-delete',{'ids':ids})
        self.assertEqual(result['deleted'],2)
        self.assertFalse((m.DATA/'uploads'/disk).exists())
        with m.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM comments').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_channels').fetchone()[0],0)
        replacement=self.task()[0];self.assertGreater(replacement,max(ids))
        self.call('post','/tasks',{'title':'Entrega','deadline':str(m.today()),'description':'Briefing https://example.com','status':'Pendente',**payload},410)
        self.call('delete',f'/tasks/{replacement}')
        self.assertEqual(self.state()['tasks'],[])

    def test_deleted_recurring_task_stays_deleted_after_restart(self):
        ch=self.channel()
        self.call('post','/formats',{'name':'Reels','channel_ids':[ch],'responsible_id':1,'frequency':{str(m.today().weekday()):2},'active_from':str(m.today())},201)
        state=self.state();tid=state['tasks'][0]['id'];fid=state['formats'][0]['id']
        self.call('delete',f'/tasks/{tid}')
        m.init()
        self.assertEqual(len(self.state()['tasks']),1)
        later=m.today()+timedelta(days=7)
        self.assertEqual(len(self.call('get',f'/state?start={later}&end={later}')['tasks']),2)
        self.call('delete',f'/formats/{fid}')
        with m.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM suppressed_slots').fetchone()[0],0)

    def test_multiple_responsibles_sync_and_reporting(self):
        ch=self.channel()
        self.call('post','/users',{'name':'Parceiro Teste','email':'partner@example.com','role':'Editor'},201)
        uid=next(u['id'] for u in self.state()['users'] if u['email']=='partner@example.com')
        fields={'name':'Original','channel_ids':[ch],'responsible_ids':[1],'frequency':{str(m.today().weekday()):1},'active_from':str(m.today())}
        self.call('post','/formats',fields,201)
        state=self.state();fid=state['formats'][0]['id'];auto=state['tasks'][0]
        manual=self.task(title='Título personalizado',format_id=fid,responsible_ids=[1],status='Criado')[0]
        unrelated=self.task(responsible_ids=[1])[0]
        before=self.call('get',f'/tasks/{manual}')
        self.call('post',f'/tasks/{manual}/comments',{'body':'Preservar'},201)
        self.call('patch',f'/formats/{fid}',{**fields,'name':'Atualizado','responsible_ids':[uid,1,uid]})
        for tid in [auto['id'],manual]:
            t=self.call('get',f'/tasks/{tid}')
            self.assertEqual(t['responsible_ids'],[1,uid]);self.assertEqual(t['version'],2)
        self.assertEqual(self.call('get',f'/tasks/{auto["id"]}')['title'],'Atualizado · 1')
        final=self.call('get',f'/tasks/{manual}')
        for key in ['title','status','deadline','completed_at','description']:
            self.assertEqual(final[key],before[key])
        self.assertEqual(len(self.call('get',f'/tasks/{manual}/comments')['comments']),1)
        self.assertEqual(self.call('get',f'/tasks/{unrelated}')['responsible_ids'],[1])
        self.call('patch',f'/tasks/{manual}',{'version':1,'status':'Pendente'},409)
        query=f'?start={m.today()}&end={m.today()}'
        report=self.call('get','/insights'+query)['report']
        self.assertEqual(report['planned'],3)
        self.assertEqual(next(p for p in report['people'] if p['name']=='Parceiro Teste')['planned'],2)
        from pypdf import PdfReader
        response=self.client.get('/api/insights.pdf'+query)
        self.assertIn('Parceiro Teste',''.join(p.extract_text() for p in PdfReader(io.BytesIO(response.data)).pages))
        response.close()
        later=m.today()+timedelta(days=7)
        new=self.call('get',f'/state?start={later}&end={later}')['tasks']
        self.assertEqual(len(new),1);self.assertEqual(new[0]['responsible_ids'],[1,uid])
        self.call('patch',f'/tasks/{manual}',{'version':2,'responsible_ids':[uid]})
        m.init()
        self.assertEqual(self.call('get',f'/tasks/{manual}')['responsible_ids'],[uid])
        # Saving an unchanged format must not overwrite a per-task adjustment.
        self.call('patch',f'/formats/{fid}',{**fields,'name':'Atualizado','responsible_ids':[1,uid]})
        self.assertEqual(self.call('get',f'/tasks/{manual}')['responsible_ids'],[uid])
        self.call('patch',f'/formats/{fid}',{**fields,'name':'Atualizado','responsible_ids':[uid]})
        self.assertEqual(self.call('get',f'/tasks/{auto["id"]}')['responsible_ids'],[uid])

    def test_manual_responsibles_validation_clear_and_legacy(self):
        ids=self.task(responsible_ids=[1,1],quantity=2)
        self.assertEqual(len(ids),2)
        for tid in ids:self.assertEqual(self.call('get',f'/tasks/{tid}')['responsible_ids'],[1])
        self.call('patch',f'/tasks/{ids[0]}',{'version':1,'responsible_ids':[]})
        self.assertEqual(self.call('get',f'/tasks/{ids[0]}')['responsible_ids'],[])
        self.call('patch',f'/tasks/{ids[0]}',{'version':2,'responsible_id':1})
        self.assertEqual(self.call('get',f'/tasks/{ids[0]}')['responsible_ids'],[1])
        for values in [[999999],None,'1',[True],[1.5]]:
            self.call('post','/tasks',{'title':'Inválida','deadline':str(m.today()),'responsible_ids':values},400)
        self.assertEqual(len(self.state()['tasks']),2)

    def test_status_migration_and_automatic_deadline_transition(self):
        from unittest.mock import patch
        day=m.today()
        ids=[self.task(status=status)[0] for status in ['Pendente','Em andamento','Revisão','Criado','Postado']]
        with m.db() as c:
            c.execute("UPDATE tasks SET status='Finalizado',completed_at='2026-01-01T10:00:00-03:00' WHERE id=?",(ids[3],))
            c.execute("UPDATE tasks SET status='Agendado' WHERE id=?",(ids[4],))
            c.execute('PRAGMA user_version=3')
        m.init()
        self.assertTrue((m.DATA/'backups/before-v4.sqlite').exists())
        self.assertEqual(self.call('get',f'/tasks/{ids[3]}')['status'],'Criado')
        self.assertEqual(self.call('get',f'/tasks/{ids[4]}')['status'],'Postado')
        self.assertEqual(self.call('get',f'/tasks/{ids[3]}')['completed_at'],'2026-01-01T10:00:00-03:00')
        self.assertEqual(self.call('get',f'/tasks/{ids[0]}')['status'],'Pendente')
        with patch.object(m,'today',return_value=day+timedelta(days=1)):
            for tid in ids[:3]:
                t=self.call('get',f'/tasks/{tid}')
                self.assertEqual(t['status'],'Atrasado');self.assertEqual(t['version'],2)
                self.call('patch',f'/tasks/{tid}',{'version':1,'status':'Criado'},409)
            for tid,status in zip(ids[3:],['Criado','Postado']):
                self.assertEqual(self.call('get',f'/tasks/{tid}')['status'],status)
            self.call('patch',f'/tasks/{ids[0]}',{'version':2,'status':'Criado'})
            self.assertFalse(self.call('get',f'/tasks/{ids[0]}')['overdue'])
            self.call('patch',f'/tasks/{ids[0]}',{'version':3,'status':'Revisão'})
            self.assertEqual(self.call('get',f'/tasks/{ids[0]}')['status'],'Atrasado')
        for old in ['Finalizado','Agendado']:
            self.call('post','/tasks',{'title':'Inválida','deadline':str(day),'status':old},400)
        with m.db() as c:
            self.assertEqual(c.execute('SELECT status FROM tasks WHERE id=?',(ids[1],)).fetchone()[0],'Atrasado')

    def test_insights_daily_totals_and_empty_pdf(self):
        from pypdf import PdfReader
        day=m.today();end=day+timedelta(days=30)
        query=f'?start={day}&end={end}'
        empty=self.call('get','/insights'+query)['report']
        self.assertEqual(sum(r['planned'] for r in empty['daily']),0)
        with self.client.get('/api/insights.pdf'+query) as response:
            self.assertEqual(response.status_code,200)
            self.assertTrue(PdfReader(io.BytesIO(response.data)).pages)
        self.task(title='PRIVATE_TASK_TITLE',quantity=3,status='Criado')
        self.task(quantity=2,deadline=str(end),status='Postado')
        report=self.call('get','/insights'+query)['report']
        self.assertEqual(report['planned'],5)
        self.assertEqual(sum(r['planned'] for r in report['daily']),5)
        self.assertEqual(sum(r['delivered'] for r in report['daily']),5)
        self.assertEqual(report['statuses'],{'Criado':3,'Postado':2})
        with self.client.get('/api/insights.pdf'+query) as response:
            content=''.join(p.extract_text() for p in PdfReader(io.BytesIO(response.data)).pages)
            self.assertNotIn('PRIVATE_TASK_TITLE',content)
            self.assertIn('Distribuição por status',content)

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
        self.call('patch',f'/tasks/{ids[0]}',{'version':1,'status':'Postado'})
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
        self.call('patch',f"/tasks/{task['id']}",{'version':1,'status':'Criado'})
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
        self.assertNotIn('Conteúdo único',content)
        self.assertIn('YouTube',content)
        self.assertIn('Distribuição por status',content)
        self.assertIn('Produção por deadline',content)
        self.assertGreaterEqual(len(pdf.pages),2)
        response.close()
        self.assertEqual(m.app.test_client().get('/api/insights.pdf'+query).status_code,401)
        # Editing a finished task preserves its completion timestamp; reopening restores it to active work.
        self.call('patch',f"/tasks/{task['id']}",{'version':2,'status':'Postado','channel_ids':[second]})
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
        self.task(deadline=old,status='Criado')
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
            self.assertLessEqual(len(pdf.pages),4)
            self.assertNotIn('Título de conteúdo',''.join(p.extract_text() for p in pdf.pages))
            self.assertIn('45',''.join(p.extract_text() for p in pdf.pages))

    def test_format_edit_updates_existing_deliveries(self):
        ch=self.channel()
        self.call('post','/formats',{'name':'Original','channel_ids':[ch],'responsible_id':1,'frequency':{str(m.today().weekday()):1},'active_from':str(m.today())},201)
        state=self.state();f=state['formats'][0];t=state['tasks'][0]
        self.call('post','/channels',{'name':'YouTube','url':'https://youtube.com/example','color':'#102b55'},201)
        second=self.state()['channels'][1]['id']
        self.call('patch',f"/formats/{f['id']}",{'name':'Novo','channel_ids':[ch,second],'responsible_id':1,'frequency':{str(m.today().weekday()):1},'active_from':str(m.today())})
        self.assertEqual(self.state()['tasks'][0]['channel_ids'],[ch,second])
        self.assertEqual(self.state()['tasks'][0]['title'],'Novo · 1')
        nextweek=m.today()+timedelta(days=7)
        new=self.call('get',f'/state?start={nextweek}&end={nextweek}')['tasks']
        self.assertEqual(len(new),1);self.assertEqual(new[0]['channel_ids'],[ch,second])
        self.call('patch',f"/tasks/{t['id']}",{'version':2,'channel_ids':[ch,second]})
        self.assertEqual(len(self.state()['tasks']),1)

    def test_manual_multichannel_and_retry_are_not_duplicates(self):
        ch=self.channel()
        self.call('post','/channels',{'name':'TikTok','url':'https://tiktok.com/@example','color':'#102b55'},201)
        second=self.state()['channels'][1]['id']
        payload={'title':'Um vídeo, dois canais','deadline':str(m.today()),'quantity':1,'channel_ids':[ch,second],'request_id':'test_request_123456789'}
        first=self.call('post','/tasks',payload,201)
        repeated=self.call('post','/tasks',payload,200)
        self.assertEqual(first['ids'],repeated['ids'])
        self.assertEqual(len(self.state()['tasks']),1)
        self.assertEqual(self.state()['tasks'][0]['channel_ids'],[ch,second])
        self.call('post','/tasks',{**payload,'quantity':2},409)
        self.call('post','/tasks',{**payload,'quantity':2,'request_id':'another_request_123456789'},201)
        self.assertEqual(len(self.state()['tasks']),3)
        from concurrent.futures import ThreadPoolExecutor
        import threading
        barrier=threading.Barrier(2)
        def simultaneous(_):
            client=m.app.test_client()
            with client.session_transaction() as sess: sess['uid']=1
            barrier.wait(timeout=5)
            result=client.post('/api/tasks',json={**payload,'request_id':'concurrent_request_123456789'},headers={'X-ContentOS':'1'})
            return result.status_code,result.get_json()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(simultaneous,range(2)))
        self.assertEqual(sorted(r[0] for r in results),[200,201])
        self.assertEqual(results[0][1]['ids'],results[1][1]['ids'])
        self.assertEqual(len(self.state()['tasks']),4)

    def test_delete_format_preserves_tasks_and_does_not_block_reused_id(self):
        ch=self.channel();body={'name':'Excluir este','channel_ids':[ch],'responsible_id':1,'frequency':{str(m.today().weekday()):1},'active_from':str(m.today())}
        self.call('post','/formats',body,201)
        state=self.state();f=state['formats'][0];t=state['tasks'][0]
        self.call('post',f"/tasks/{t['id']}/comments",{'body':'Manter comentário'},201)
        self.call('delete',f"/formats/{f['id']}",expected=401,client=m.app.test_client())
        self.call('delete',f"/formats/{f['id']}")
        state=self.state();self.assertEqual(state['formats'],[]);self.assertEqual(len(state['tasks']),1)
        self.assertIsNone(state['tasks'][0]['format_id']);self.assertIsNone(state['tasks'][0]['slot'])
        self.assertEqual(state['tasks'][0]['channel_ids'],[ch])
        self.assertEqual(len(self.call('get',f"/tasks/{t['id']}/comments")['comments']),1)
        self.call('patch',f"/tasks/{t['id']}",{'version':1,'status':'Postado'},409)
        nextweek=m.today()+timedelta(days=7)
        self.assertEqual(self.call('get',f'/state?start={nextweek}&end={nextweek}')['tasks'],[])
        self.call('post','/formats',body,201)
        self.assertEqual(len(self.state()['tasks']),2)

if __name__=='__main__':unittest.main()
