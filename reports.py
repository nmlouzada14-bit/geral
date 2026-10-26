"""Production metrics: one content item per task, scoped by its deadline."""
from collections import Counter
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

DONE = ('Finalizado', 'Agendado', 'Postado')


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
    distribution=[row(c['name'],[t for t in tasks if c['id'] in t['channel_ids']]) for c in channels]
    return dict(start=str(start),end=str(end),**row('Total',tasks),statuses=dict(statuses),
        on_time=on_time,late_delivery=len(dated)-on_time,undated_delivery=len(delivered)-len(dated),
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
    story.extend([paragraph('Resumo da produção','Heading2'),paragraph('Filtro pela deadline. Cada conteúdo conta uma vez, independentemente do número de canais. Entregues = Finalizado + Agendado + Postado. O relatório mostra o estado atual desse conjunto de tarefas.'),Spacer(1,10)])
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
    story.append(paragraph('Etapas e prazos','Heading2'))
    table(['Etapa','Quantidade'],list(report['statuses'].items()) or [['Sem tarefas',0]],[370,161])
    story.append(paragraph(f"Entregues no prazo: {report['on_time']}. Entregues após o prazo: {report['late_delivery']}. Sem data histórica de conclusão: {report['undated_delivery']}. Datas de conclusão só estão disponíveis para transições registradas a partir desta versão; não estimamos datas antigas."))
    for key,title in [('people','Demandas por pessoa'),('channels','Distribuição por canal')]:
        story.extend([Spacer(1,12),paragraph(title,'Heading2')])
        if key=='people':story.append(paragraph('Uma tarefa compartilhada aparece para cada responsável. O total geral conta cada conteúdo uma única vez.'))
        if key=='channels':story.append(paragraph('Um conteúdo com vários canais aparece em cada canal. A soma por canal pode ultrapassar o total de conteúdos.'))
        table(['Pessoa' if key=='people' else 'Canal','Planejadas','Entregues','Em aberto','Atrasadas'],[[r['name'],r['planned'],r['delivered'],r['pending'],r['overdue']] for r in report[key]] or [['Sem demandas',0,0,0,0]],[211,80,80,80,80])
    names={u['id']:u['name'] for u in users};channel_names={c['id']:c['name'] for c in channels}
    for delivered,title in [(True,'Entregas concluídas'),(False,'Demandas em aberto')]:
        story.extend([Spacer(1,12),paragraph(title,'Heading2')])
        items=[t for t in tasks if (t['status'] in DONE)==delivered]
        rows=[[f"#{t['id']} · {t['title']}",display(t['deadline']),'\n'.join(names[uid] for uid in t['responsible_ids']) or 'Sem responsável','\n'.join(channel_names[x] for x in t['channel_ids']),t['status']] for t in items]
        if rows:table(['Conteúdo','Deadline','Responsável','Canais','Status'],rows,[175,67,92,107,90])
        else:story.append(paragraph('Nenhuma demanda neste grupo.'))
    story.extend([Spacer(1,12),paragraph('Métricas sociais: visualizações, alcance e engajamento não estão incluídos. As contas das redes sociais ainda não foram conectadas às APIs oficiais.')])
    def footer(canvas,doc):
        canvas.setFont('ContentOS',8);canvas.setFillColor(colors.HexColor('#78869b'))
        canvas.drawString(32,22,'ContentOS · Zayed | Relatório de produção')
        canvas.drawRightString(A4[0]-32,22,f'Página {doc.page}')
    doc.build(story,onFirstPage=footer,onLaterPages=footer);out.seek(0)
    return out
