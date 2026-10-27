"""Durable WhatsApp overdue notifications. Never log keys, bodies or phone numbers."""
import json
import os
import threading
import time
from urllib import request, error, parse


def configuration():
    url=os.environ.get('EVOLUTION_API_URL','https://evolution-api-evolution-api.2dxvsk.easypanel.host').rstrip('/')
    public=os.environ.get('CONTENTOS_PUBLIC_URL','https://contentos-web.2dxvsk.easypanel.host').rstrip('/')
    instance=os.environ.get('EVOLUTION_INSTANCE','zayedd')
    key=os.environ.get('EVOLUTION_API_KEY','').strip()
    enabled=os.environ.get('WHATSAPP_NOTIFICATIONS_ENABLED')=='1'
    valid=all(parse.urlsplit(u).scheme=='https' and parse.urlsplit(u).hostname and not parse.urlsplit(u).username and not parse.urlsplit(u).query and not parse.urlsplit(u).fragment for u in (url,public))
    return dict(url=url,public=public,instance=instance,key=key,enabled=enabled,ready=bool(valid and key and instance))


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def send_message(config, number, body):
    endpoint=config['url']+'/message/sendText/'+parse.quote(config['instance'],safe='')
    req=request.Request(endpoint,data=json.dumps({'number':number,'text':body,'linkPreview':False}).encode(),headers={'Content-Type':'application/json','apikey':config['key']},method='POST')
    try:
        with request.build_opener(NoRedirect).open(req,timeout=15) as response:
            result=json.loads(response.read(65536))
        message_id=result.get('key',{}).get('id')
        return ('sent',str(message_id)) if message_id else ('uncertain','Resposta sem confirmação de envio')
    except error.HTTPError as exc:
        if exc.code==429: return 'retry','Limite de envio (429)'
        if 400<=exc.code<500: return 'failed','Evolution recusou o envio (HTTP '+str(exc.code)+')'
        return 'uncertain','Resposta inconclusiva da Evolution'
    except Exception:
        # A timeout can occur after the provider accepted the message. Do not resend blindly.
        return 'uncertain','Envio sem confirmação; confira na Evolution'


def process_once(sender=send_message):
    from app import db,today,now
    config=configuration()
    if not config['enabled'] or not config['ready']: return
    clock=time.time()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute("UPDATE tasks SET status='Atrasado',version=version+1 WHERE deadline<? AND status NOT IN ('Criado','Postado','Atrasado')",(str(today()),))
        c.execute("UPDATE overdue_notifications SET state='uncertain',error='Processo interrompido durante envio; confira na Evolution' WHERE state='sending' AND claimed_at<?",(clock-120,))
        c.execute("INSERT OR IGNORE INTO overdue_notifications(task_id,user_id,episode) SELECT t.id,r.user_id,t.overdue_episode FROM tasks t JOIN task_responsibles r ON r.task_id=t.id JOIN users u ON u.id=r.user_id WHERE t.status='Atrasado' AND t.overdue_episode>0 AND u.whatsapp!=''")
        c.execute("UPDATE overdue_notifications SET state='cancelled' WHERE state IN ('pending','retry') AND NOT EXISTS (SELECT 1 FROM tasks t JOIN task_responsibles r ON r.task_id=t.id JOIN users u ON u.id=r.user_id WHERE t.id=overdue_notifications.task_id AND t.status='Atrasado' AND t.overdue_episode=overdue_notifications.episode AND r.user_id=overdue_notifications.user_id AND u.whatsapp!='')")
    for _ in range(20):
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute("SELECT n.*,t.title,t.deadline,u.whatsapp FROM overdue_notifications n JOIN tasks t ON t.id=n.task_id JOIN users u ON u.id=n.user_id JOIN task_responsibles r ON r.task_id=t.id AND r.user_id=u.id WHERE n.state IN ('pending','retry') AND n.next_attempt<=? AND t.status='Atrasado' AND t.overdue_episode=n.episode AND u.whatsapp!='' ORDER BY n.id LIMIT 1",(time.time(),)).fetchone()
            if not row: break
            c.execute("UPDATE overdue_notifications SET state='sending',claimed_at=?,attempts=attempts+1 WHERE id=?",(time.time(),row['id']))
        date=row['deadline'][8:10]+'/'+row['deadline'][5:7]+'/'+row['deadline'][:4]
        title=' '.join(row['title'].split())
        body=f"ContentOS · Tarefa atrasada\n\n{title}\nDeadline: {date}\n\nAbra a tarefa para atualizar o andamento:\n{config['public']}/?task={row['task_id']}"
        try: state,detail=sender(config,row['whatsapp'],body)
        except Exception: state,detail='uncertain','Envio interrompido; confira na Evolution'
        if state=='retry' and row['attempts']>=4: state='failed'
        with db() as c:
            c.execute('UPDATE overdue_notifications SET state=?,next_attempt=?,delivered_at=?,message_id=?,error=? WHERE id=?',(state,time.time()+min(3600,60*2**row['attempts']),now() if state=='sent' else None,detail if state=='sent' else None,None if state=='sent' else detail,row['id']))


def start_worker():
    config=configuration()
    if not config['enabled'] or not config['ready']: return
    def loop():
        import logging
        while True:
            try: process_once()
            except Exception: logging.getLogger('contentos.notifications').warning('Falha na verificação de notificações; nova tentativa em 60 segundos.')
            time.sleep(60)
    threading.Thread(target=loop,name='overdue-notifications',daemon=True).start()
