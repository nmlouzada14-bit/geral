"""Production metrics: one content item per task, scoped by its deadline."""
from collections import Counter
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

DONE = ('Criado', 'Postado')


def summarize(tasks, users, channels, start, end):
    delivered=[t for t in tasks if t['status'] in DONE]
    dated=[t for t in delivered if t.get('completed_at')]
    on_time=sum(t['completed_at'][:10] <= t['deadline'] for t in dated)
    statuses=Counter(t['status'] for t in tasks)
    def row(name, items):
        n=len(items);done=sum(t['status'] in DONE for t in items)
        return dict(name=name,planned=n,delivered=done,pending=n-done,posted=sum(t['status']=='Postado' for t in items),overdue=sum(t['overdue'] or t['status']=='Atrasado' for t in items),rate=round(done/n*100,1) if n else 0)
    people=[row(u['name'],[t for t in tasks if u['id'] in t['responsible_ids']]) for u in users]
    people.append(row('Sem responsável',[t for t in tasks if not t['responsible_ids']]))
    daily=[]
    step=7 if (end-start).days>=14 else 1
    day=start
    while day<=end:
        last=min(day+timedelta(days=step-1),end)
        daily.append({**row(day.strftime('%d/%m')+(('–'+last.strftime('%d/%m')) if step>1 else ''),[t for t in tasks if str(day)<=t['deadline']<=str(last)]),'start':str(day),'end':str(last)})
        day=last+timedelta(days=1)
    distribution=[row(c['name'],[t for t in tasks if c['id'] in t['channel_ids']]) for c in channels]
    return dict(start=str(start),end=str(end),**row('Total',tasks),statuses=dict(statuses),
        daily=daily,on_time=on_time,late_delivery=len(dated)-on_time,undated_delivery=len(delivered)-len(dated),
        on_time_rate=round(on_time/len(dated)*100,1) if dated else None,
        people=[p for p in people if p['planned']],channels=[ch for ch in distribution if ch['planned']])


def make_pdf(report,tasks,users,channels,generated):
    """Landscape meeting deck with vector charts; no task-level data in the export."""
    import math
    import reportlab
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.colors import HexColor
    from reportlab.lib.utils import simpleSplit
    fonts=Path(reportlab.__file__).parent/'fonts'
    for name,file in [('ContentOS','Vera.ttf'),('ContentOSBold','VeraBd.ttf')]:
        if name not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(name,str(fonts/file)))
    out=BytesIO();W,H=960,600;c=canvas.Canvas(out,pagesize=(W,H))
    c.setTitle('ContentOS · Insights');c.setAuthor('Zayed Company')
    navy='#102B55';blue='#3B82F6';muted='#74839b';green='#18aa82';red='#e16b7e'
    palette=['#a9b9d0',blue,'#9b8beb',green,'#4f72b8',red]
    statuses=['Pendente','Em andamento','Revisão','Criado','Postado','Atrasado']
    r=report;page=0
    period=date.fromisoformat(r['start']).strftime('%d/%m/%Y')+' — '+date.fromisoformat(r['end']).strftime('%d/%m/%Y')
    def rect(x,y,w,h,fill,radius=14):
        c.setFillColor(HexColor(fill));c.roundRect(x,H-y-h,w,h,radius,stroke=0,fill=1)
    def text(x,y,value,size=11,color=navy,bold=False):
        c.setFillColor(HexColor(color));c.setFont('ContentOSBold' if bold else 'ContentOS',size);c.drawString(x,H-y-size,str(value))
    def wrap(x,y,value,width,size=10,color=muted,maxlines=None):
        lines=simpleSplit(str(value),'ContentOS',size,width)
        if maxlines and len(lines)>maxlines:
            lines=lines[:maxlines];lines[-1]=lines[-1].rstrip()+'…'
        for i,line in enumerate(lines):text(x,y+i*(size+4),line,size,color)
    def frame(title,subtitle):
        nonlocal page
        page+=1;rect(0,0,W,H,'#f3f6fc',0)
        text(36,20,'content OS',15,navy,True);text(762,25,'ZAYED COMPANY',9,muted,True)
        text(36,64,title,26,navy,True);text(36,103,subtitle,10,muted)
        text(36,555,'Entregues = Criado + Postado. Contagem por deadline; pessoas/canais podem compartilhar conteúdos. Sem métricas de audiência.',7,muted)
        text(36,570,period+'  ·  Gerado em '+datetime.fromisoformat(generated).strftime('%d/%m/%Y %H:%M')+' (São Paulo)',8,muted)
        text(842,570,f'INSIGHTS / {page:02d}',8,muted)
    def donut(cx,cy,radius,values,colors,center,label,background='#ffffff'):
        c.setFillColor(HexColor('#e8eef7'));c.circle(cx,H-cy,radius,stroke=0,fill=1)
        total=sum(values);angle=0
        if total:
            for value,color in zip(values,colors):
                sweep=360*value/total
                if sweep:
                    c.setFillColor(HexColor(color));c.wedge(cx-radius,H-cy-radius,cx+radius,H-cy+radius,90-angle,-sweep,stroke=0,fill=1)
                angle+=sweep
        c.setFillColor(HexColor(background));c.circle(cx,H-cy,radius*.73,stroke=0,fill=1)
        size=min(26,26*radius*1.25/max(pdfmetrics.stringWidth(str(center),'ContentOSBold',26),1))
        width=pdfmetrics.stringWidth(str(center),'ContentOSBold',size)
        text(cx-width/2,cy-size/2-3,center,size,navy,True)
        width=pdfmetrics.stringWidth(label,'ContentOS',8);text(cx-width/2,cy+13,label,8,muted)
    frame('A produção em perspectiva', 'Resumo executivo · '+period)
    rect(36,135,888,127,navy)
    text(60,155,'RITMO DE ENTREGA',9,'#a9c9fc',True)
    text(60,179,str(r['rate'])+'%',40,'#ffffff',True)
    text(215,186,f"{r['delivered']} de {r['planned']} conteúdos entregues",19,'#ffffff',True)
    wrap(215,220,'Entregues = Criado + Postado. Contagem única por conteúdo.',630,10,'#bfd2ee')
    stats=[('PLANEJADAS',r['planned']),('CRIADAS / A POSTAR',r['statuses'].get('Criado',0)),('POSTADAS',r['posted']),('EM ABERTO',r['pending']),('ATRASADAS',r['overdue'])]
    for i,(label,value) in enumerate(stats):
        x=36+i*180;rect(x,278,168,82,'#ffffff');text(x+14,292,label,8,muted,True);text(x+14,313,value,29,red if i==4 and value else navy,True)
    rect(36,376,430,175,'#ffffff');text(54,391,'Distribuição por status',13,navy,True)
    donut(131,483,57,[r['statuses'].get(s,0) for s in statuses],palette,r['planned'],'conteúdos')
    for i,status in enumerate(statuses):
        y=426+i*18;rect(218,y+3,7,7,palette[i],3);text(233,y,status,9);text(424,y,r['statuses'].get(status,0),9,navy,True)
    rect(482,376,442,175,'#ffffff');text(502,391,'Da criação à publicação',13,navy,True)
    for i,(name,value,color) in enumerate([('Em produção',r['pending'],blue),('Prontos para postar',r['statuses'].get('Criado',0),green),('Publicados',r['posted'],'#4f72b8')]):
        x=502+i*138;rect(x,427,124,66,'#f3f6fc');text(x+10,435,value,25,color,True);text(x+10,473,name,8,muted)
    wrap(502,511,f"{r['statuses'].get('Criado',0)} conteúdos criados aguardam postagem. {r['overdue']} demandas precisam de atenção ao prazo.",398,10)
    c.showPage()
    frame('Ritmo, capacidade e prazos','Produção por deadline · Retrato atual do período selecionado')
    rect(36,135,888,228,'#ffffff');text(56,151,'Produção por deadline',13,navy,True)
    text(650,155,'Planejadas',9,muted);rect(630,158,10,5,'#b4ccf6',2);text(782,155,'Entregues',9,blue);rect(763,158,10,5,blue,2)
    daily=r['daily'];maxv=max([d['planned'] for d in daily]+[1]);left=74;top=196;cw=808;ch=120
    c.setLineWidth(.5)
    for fraction in [0,.5,1]:
        y=top+ch*(1-fraction);c.setStrokeColor(HexColor('#e9eef6'));c.line(left,H-y,left+cw,H-y);text(48,y-5,round(maxv*fraction,1),8,muted)
    for metric,color in [('planned','#b4ccf6'),('delivered',blue)]:
        pts=[(left+(cw*i/max(len(daily)-1,1) if len(daily)>1 else cw/2),top+ch-ch*d[metric]/maxv) for i,d in enumerate(daily)]
        if len(pts)>1:
            path=c.beginPath();path.moveTo(pts[0][0],H-(top+ch))
            for x,y in pts:path.lineTo(x,H-y)
            path.lineTo(pts[-1][0],H-(top+ch));path.close()
            c.saveState();c.setFillColor(HexColor(color));c.setFillAlpha(.12);c.drawPath(path,stroke=0,fill=1);c.restoreState()
            path=c.beginPath();path.moveTo(pts[0][0],H-pts[0][1])
            for x,y in pts[1:]:path.lineTo(x,H-y)
            c.setStrokeColor(HexColor(color));c.setLineWidth(2);c.drawPath(path)
        for x,y in pts:c.setFillColor(HexColor(color));c.circle(x,H-y,3,stroke=0,fill=1)
    for i,d in enumerate(daily):
        if i%max(1,math.ceil(len(daily)/7))==0 or i==len(daily)-1:
            x=left+cw*i/max(len(daily)-1,1);text(min(x,842),331,d['name'],7,muted)
    cards=[('Pontualidade',r['on_time'],r['late_delivery'],str(r['on_time_rate'])+'%' if r['on_time_rate'] is not None else '—',green,'no prazo / com data'),('Publicação',r['posted'],r['planned']-r['posted'],str(round(r['posted']/r['planned']*100))+'%' if r['planned'] else '—',blue,'publicados / planejados'),('Atenção aos prazos',r['overdue'],r['planned']-r['overdue'],str(r['overdue']),red,'demandas atrasadas')]
    for i,(title,a,b,value,color,label) in enumerate(cards):
        x=36+300*i;rect(x,380,288,171,'#ffffff');text(x+18,394,title,12,navy,True);donut(x+77,482,48,[a,b],[color,'#e8eef7'],value,'')
        wrap(x+142,443,label,128,10);wrap(x+142,482,f"{r['undated_delivery']} sem data histórica" if i==0 else f'{a} de {r["planned"]} conteúdos',125,9)
    c.showPage()
    people=r['people'];channels_data=r['channels'];pages=max(1,math.ceil(max(len(people),len(channels_data))/5))
    for batch in range(pages):
        frame('O time e os canais' if batch==0 else 'O time e os canais · continuação','Distribuição de trabalho e conclusão por frente de publicação')
        for col,(title,items) in enumerate([('Demandas por pessoa',people),('Distribuição por canal',channels_data)]):
            x=36+452*col;rect(x,135,436,416,'#ffffff');text(x+20,152,title,14,navy,True)
            chunk=items[batch*5:(batch+1)*5]
            if not chunk:wrap(x+20,210,'Sem demandas neste período.',390,12)
            for i,item in enumerate(chunk):
                y=190+i*67;rect(x+16,y,404,60,'#f5f8fd')
                wrap(x+28,y+8,item['name'],267,10,navy,2)
                text(x+340,y+8,str(item['rate'])+'%',14,blue,True)
                text(x+28,y+38,f"{item['planned']} planejadas  ·  {item['delivered']} entregues  ·  {item['overdue']} atrasadas",8,muted)
                rect(x+28,y+54,360,3,'#e2eaf7',1)
                if item['rate']:rect(x+28,y+54,360*item['rate']/100,3,blue,1)
        c.showPage()
    # Keep the export searchable, with no task-level details.
    c.setSubject('Contagem por deadline; Criado + Postado = entregue. Pessoas/canais podem compartilhar conteúdos. Métricas sociais não incluídas. Gerado em '+generated)
    c.save();out.seek(0);return out
