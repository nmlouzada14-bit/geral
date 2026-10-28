"""Run against a fresh isolated instance, never production."""
import os
from playwright.sync_api import sync_playwright, expect
URL=os.environ.get('TEST_URL','http://127.0.0.1:8016')
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    context=browser.new_context();page=context.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(URL)
    page.get_by_label('Seu e-mail').fill('nmlouzada14@gmail.com')
    page.get_by_label('Senha',exact=True).fill('Initial-Test-2026!')
    page.get_by_role('button',name='Entrar no ContentOS').click()
    page.get_by_label('Senha inicial').fill('Initial-Test-2026!')
    page.get_by_label('Nova senha pessoal').fill('Personal-Test-2026!')
    page.get_by_role('button',name='Salvar senha e entrar').click()
    expect(page.get_by_role('heading',name='Sua produção, em um olhar.')).to_be_visible()
    def req(path,body=None):
        r=context.request.fetch(URL+'/api'+path,method='POST' if body is not None else 'GET',data=body,headers={'X-ContentOS':'1'})
        assert r.ok,r.text()
        return r.json()
    state=req('/state');today=state['today']
    req('/channels',{'name':'Instagram','url':'https://example.com','color':'#3b82f6'})
    req('/channels',{'name':'YouTube','url':'https://example.com','color':'#102b55'})
    req('/users',{'name':'Paloma Teste','email':'paloma@example.com','role':'Social media'})
    from datetime import date,timedelta
    day=date.fromisoformat(today)
    start=day-timedelta(days=day.weekday())
    for i in range(7):
        for status,n in [('Criado',2),('Postado',3),('Pendente',1)]:
            req('/tasks',{'title':'Conteúdo de teste','deadline':str(start+timedelta(days=i)),'status':status,'quantity':n,'channel_ids':[1,2] if i%2 else [1],'responsible_ids':[1,2] if i%2 else [2]})
    page.locator('.nav [data-page=insights]').click()
    expect(page.locator('.insight-hero')).to_be_visible()
    expect(page.locator('.insight-trend')).to_be_visible()
    expect(page.locator('body')).not_to_contain_text('Conteúdo de teste')
    with page.expect_download() as info:
        page.get_by_role('button',name='Exportar apresentação PDF',exact=False).click()
    info.value.save_as('/tmp/contentos-meeting.pdf')
    page.screenshot(path='/tmp/contentos-new-insights.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
    page.screenshot(path='/tmp/contentos-new-insights-mobile.png',full_page=True)
    page.set_viewport_size({'width':1280,'height':900})
    page.locator('.nav [data-page=tasks]').click()
    page.locator('tr[data-task]').first.click()
    page.get_by_label('Mencionar membro').select_option('1')
    page.get_by_label('Escreva um comentário').press_sequentially('conferir este conteúdo')
    page.get_by_role('button',name='Enviar comentário',exact=True).click()
    expect(page.locator('.comment')).to_have_count(1)
    expect(page.locator('.mentions-button .count')).to_have_text('1')
    page.get_by_role('button',name='Cancelar',exact=True).click()
    page.locator('.mentions-button').click()
    expect(page.locator('.mention-notice')).to_have_count(1)
    page.locator('.mention-notice').click()
    expect(page.get_by_role('heading',name='Detalhes da tarefa')).to_be_visible()
    expect(page.locator('.mentions-button .count')).to_have_count(0)
    page.get_by_label('Escreva um comentário').fill('@Nícolas Louzada outra menção sem usar seletor')
    page.get_by_role('button',name='Enviar comentário',exact=True).click()
    expect(page.locator('.mentions-button .count')).to_have_text('1')
    page.get_by_role('button',name='Cancelar',exact=True).click()
    page.reload()
    expect(page.locator('.mentions-button .count')).to_have_text('1')
    assert not errors,errors
    browser.close()
print('PASS: redesigned Insights/PDF, mobile and self/typed mention inbox with explicit read.')
