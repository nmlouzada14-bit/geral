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
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,LongTable,TableStyle
    fonts=Path(reportlab.__file__).parent/'fonts'
    if 'ContentOS' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('ContentOS',str(fonts/'Vera.ttf')))
    styles=getSampleStyleSheet()
    for name in ('Title','Heading1','Heading2','Normal','BodyText'):
        styles[name].fontName='ContentOS'
        styles[name].textColor=colors.HexColor('#102B55')
    cell=ParagraphStyle('cell',fontName='ContentOS',fontSize=8,leading=11,wordWrap='CJK',textColor=colors.HexColor('#243955'))
    out=BytesIO();doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=32,leftMargin=32,topMargin=36,bottomMargin=40,title='ContentOS · Relatório de produção',author='ContentOS')
    story=[]
    def paragraph(value,style='BodyText'):
        return Paragraph(escape(str(value)),styles[style])
    def table(headers,rows,widths=None):
        data=[[Paragraph(escape(str(v)),cell) for v in headers]]
        data += [[Paragraph(escape(str(v)).replace('\n','<br/>'),cell) for v in r] for r in rows]
        t=LongTable(data,colWidths=widths,repeatRows=1,hAlign='LEFT',splitInRow=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7effd')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f7f9fc')]),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor('#a9bfdf'))]))
        story.extend([t,Spacer(1,16)])
    def display(s):return date.fromisoformat(s).strftime('%d/%m/%Y')
    story.extend([paragraph('ContentOS · Insights','Title'),paragraph(f"Período: {display(report['start'])} a {display(report['end'])}"),paragraph('Gerado em '+datetime.fromisoformat(generated).strftime('%d/%m/%Y %H:%M')+' · São Paulo'),Spacer(1,16)])
    story.extend([paragraph('Resumo da produção','Heading2'),paragraph('Filtro pela deadline. Cada conteúdo conta uma vez, independentemente do número de canais. Entregues = Criado + Postado. O relatório mostra o estado atual desse conjunto de tarefas.'),Spacer(1,10)])
    table(['Planejadas','Entregues','Em aberto','Postadas','Atrasadas','Conclusão'],[[report[k] for k in ['planned','delivered','pending','posted','overdue']]+[str(report['rate'])+'%']],[89,89,89,89,89,86])
    story.append(paragraph('Planejadas x entregues','Heading2'))
    from reportlab.graphics.shapes import Drawing,Rect,String
    chart=Drawing(510,80)
    maximum=max(report['planned'],1)
    for y,label,value,fill in [(45,'Planejadas',report['planned'],'#b6cff8'),(10,'Entregues',report['delivered'],'#3b82f6')]:
        chart.add(String(0,y+6,label,fontName='ContentOS',fontSize=10))
        chart.add(Rect(100,y,350*value/maximum,22,fillColor=colors.HexColor(fill),strokeColor=None))
        chart.add(String(460,y+6,str(value),fontName='ContentOS',fontSize=10))
    story.extend([chart,Spacer(1,12)])
    def bars(title, rows, paired=False):
        story.extend([Spacer(1,12),paragraph(title,'Heading2')])
        if not rows:
            story.append(paragraph('Sem demandas no período.'))
            return
        maximum=max([v for _,a,b in rows for v in (a,b)]+[1])
        if paired: story.append(paragraph('Azul claro: planejadas · Azul: entregues (Criado + Postado).'))
        for offset in range(0,len(rows),10):
            chunk=rows[offset:offset+10];drawing=Drawing(530,len(chunk)*45+8)
            for index,(label,a,b) in enumerate(chunk):
                y=(len(chunk)-index-1)*45+8
                drawing.add(String(0,y+20,label[:30]+('…' if len(label)>30 else ''),fontName='ContentOS',fontSize=8))
                drawing.add(Rect(180,y+14,285*a/maximum,12,fillColor=colors.HexColor('#b6cff8' if paired else '#3b82f6'),strokeColor=None))
                drawing.add(String(480,y+16,str(a),fontName='ContentOS',fontSize=9))
                if paired:
                    drawing.add(Rect(180,y,285*b/maximum,10,fillColor=colors.HexColor('#3b82f6'),strokeColor=None))
                    drawing.add(String(480,y+1,str(b),fontName='ContentOS',fontSize=9))
            story.append(drawing)
    bars('Distribuição por status',[(name,n,0) for name,n in report['statuses'].items()])
    bars('Produção por deadline',[(r['name'],r['planned'],r['delivered']) for r in report['daily']],True)
    bars('Prazos das entregas',[('No prazo',report['on_time'],0),('Após o prazo',report['late_delivery'],0),('Sem data histórica',report['undated_delivery'],0)])
    story.append(paragraph('Datas de conclusão ausentes não são estimadas. A produção por dia/semana agrupa pela deadline, não pela data da conclusão.'))
    for key,title in [('people','Demandas por pessoa'),('channels','Distribuição por canal')]:
        bars(title,[(r['name'],r['planned'],r['delivered']) for r in report[key]],True)
        story.append(paragraph('Conteúdos compartilhados aparecem em cada pessoa/canal associado. O total geral conta cada conteúdo uma vez.'))
    story.extend([Spacer(1,12),paragraph('Métricas sociais: visualizações, alcance e engajamento não estão incluídos. As contas das redes sociais ainda não foram conectadas às APIs oficiais.')])
    def footer(canvas,doc):
        canvas.setFont('ContentOS',8);canvas.setFillColor(colors.HexColor('#78869b'))
        canvas.drawString(32,22,'ContentOS · Zayed | Relatório de produção')
        canvas.drawRightString(A4[0]-32,22,f'Página {doc.page}')
    doc.build(story,onFirstPage=footer,onLaterPages=footer);out.seek(0)
    return out
