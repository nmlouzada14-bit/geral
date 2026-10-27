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
    return dict(url=url,public=public,instance=instance,key=key,enabled=enabled,ready=bool(valid and key and instance),group='120363426043140967@g.us')


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
            try:
                process_daily()
                process_once()
            except Exception: logging.getLogger('contentos.notifications').warning('Falha na verificação de notificações; nova tentativa em 60 segundos.')
            time.sleep(60)
    threading.Thread(target=loop,name='overdue-notifications',daemon=True).start()


def digest_text(c, day):
    """One line per format and identical responsibility set, independently per section."""
    from app import linked_responsibles
    from collections import OrderedDict
    names={r['id']:r['name'] for r in c.execute('SELECT id,name FROM users')}
    rows=c.execute("SELECT t.*,f.name AS format_name FROM tasks t LEFT JOIN formats f ON f.id=t.format_id WHERE t.deadline=? OR (t.status NOT IN ('Criado','Postado') AND (t.deadline<? OR t.status='Atrasado')) ORDER BY t.deadline,t.id",(str(day),str(day))).fetchall()
    def section(items):
        grouped=OrderedDict()
        for t in items:
            people=tuple(linked_responsibles(c,'task',t['id']))
            key=(('format',t['format_id']) if t['format_id'] else ('batch',t['batch']) if t['batch'] else ('task',t['id']),people)
            title=t['format_name'] if t['format_id'] else t['title']
            if not t['format_id'] and t['batch']:
                import re
                title=re.sub(r' · \d+$','',title)
            if key not in grouped: grouped[key]=[title,people,0]
            grouped[key][2]+=1
        clean=lambda value:' '.join(value.split()).replace('*','').replace('_','')
        return ['• '+clean(title)+(f' ({count}x)' if count>1 else '')+' - '+(', '.join(clean(names[uid]) for uid in people) if people else 'Sem responsável') for title,people,count in grouped.values()] or ['• Nenhuma tarefa.']
    current=section([t for t in rows if t['deadline']==str(day)])
    late=section([t for t in rows if t['deadline']!=str(day) and t['status'] not in ('Criado','Postado')])
    return '\n'.join(['✅ *TAREFAS DO DIA - '+day.strftime('%d/%m')+'*',*current,'','🚨 *ATRASADAS*',*late])


def queue_daily(day, run_key, kind, config):
    from app import db,generate,now
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM digest_runs WHERE run_key=?',(run_key,)).fetchone():
            return {'ok':True,'queued':False}
        generate(c,day,day)
        c.execute("UPDATE tasks SET status='Atrasado',version=version+1 WHERE deadline<? AND status NOT IN ('Criado','Postado','Atrasado')",(str(day),))
        body=digest_text(c,day)
        # Keep every line without exceeding practical WhatsApp message sizes.
        chunks=[];chunk=''
        for line in body.splitlines():
            while len(line)>3000:
                if chunk:chunks.append(chunk);chunk=''
                chunks.append(line[:3000]);line=line[3000:]
            if len(chunk)+len(line)+1>3000: chunks.append(chunk);chunk=''
            chunk+=('\n' if chunk else '')+line
        if chunk: chunks.append(chunk)
        c.execute('INSERT INTO digest_runs VALUES(?,?,?,?)',(run_key,str(day),kind,now()))
        for i,chunk in enumerate(chunks):
            prefix=f'[{i+1}/{len(chunks)}] ' if len(chunks)>1 else ''
            c.execute('INSERT INTO digest_messages(run_key,part,recipient,body) VALUES(?,?,?,?)',(run_key,i,config['group'],prefix+chunk))
    return {'ok':True,'queued':True,'parts':len(chunks)}


def process_daily(sender=send_message, moment=None):
    from app import db
    from datetime import datetime
    from zoneinfo import ZoneInfo
    config=configuration()
    if not config['enabled'] or not config['ready']: return
    moment=(moment or datetime.now(ZoneInfo('America/Sao_Paulo'))).astimezone(ZoneInfo('America/Sao_Paulo'))
    if moment.hour>=9:
        queue_daily(moment.date(),'scheduled:'+str(moment.date()),'scheduled',config)
    with db() as c:
        c.execute("UPDATE digest_messages SET state='uncertain',error='Processo interrompido; confira no grupo' WHERE state='sending' AND claimed_at<?",(time.time()-120,))
        c.execute("UPDATE digest_messages SET state='cancelled' WHERE state IN ('pending','retry') AND run_key IN (SELECT run_key FROM digest_runs WHERE day<?)",(str(moment.date()),))
    for _ in range(20):
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute("SELECT * FROM digest_messages m WHERE state IN ('pending','retry') AND next_attempt<=? AND NOT EXISTS (SELECT 1 FROM digest_messages p WHERE p.run_key=m.run_key AND p.part<m.part AND p.state!='sent') ORDER BY id LIMIT 1",(time.time(),)).fetchone()
            if not row:break
            c.execute("UPDATE digest_messages SET state='sending',attempts=attempts+1,claimed_at=? WHERE id=?",(time.time(),row['id']))
        try:state,detail=sender(config,row['recipient'],row['body'])
        except Exception:state,detail='uncertain','Envio sem confirmação; confira no grupo'
        if state=='retry' and row['attempts']>=4:state='failed'
        with db() as c:
            c.execute('UPDATE digest_messages SET state=?,message_id=?,error=?,next_attempt=? WHERE id=?',(state,detail if state=='sent' else None,None if state=='sent' else detail,time.time()+min(3600,60*2**row['attempts']),row['id']))
