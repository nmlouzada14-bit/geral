"""Run against a fresh isolated instance, never production."""
import os
from playwright.sync_api import sync_playwright, expect
URL=os.environ.get('TEST_URL','http://127.0.0.1:8009')
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
    page.locator('.nav [data-page=insights]').click()
    expect(page.locator('.status-donut')).to_be_visible()
    expect(page.locator('tr[data-task]')).to_have_count(0)
    state=req('/state');today=state['today']
    for status in ['Pendente','Em andamento','Revisão','Criado','Postado']:
        req('/tasks',{'title':'Detalhe que não deve aparecer no relatório','deadline':today,'status':status,'quantity':2})
    page.reload()
    page.locator('.nav [data-page=insights]').click()
    expect(page.locator('.status-donut strong')).to_have_text('10')
    expect(page.locator('.insight-chart')).to_have_count(5)
    expect(page.locator('body')).not_to_contain_text('Detalhe que não deve aparecer')
    expect(page.locator('body')).not_to_contain_text('Agendado')
    with page.expect_download() as info:
        page.get_by_role('button',name='Exportar PDF',exact=False).click()
    assert info.value.failure() is None
    page.screenshot(path='/tmp/contentos-insights-desktop.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path='/tmp/contentos-insights-mobile.png',full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
    page.set_viewport_size({'width':1280,'height':900})
    page.locator('.nav [data-page=tasks]').click()
    page.get_by_role('button',name='Criar tarefa',exact=False).first.click()
    options=page.locator('#f-status option').all_text_contents()
    assert 'Criado' in options and 'Agendado' not in options and 'Finalizado' not in options
    page.get_by_role('button',name='Cancelar',exact=True).click()
    assert not errors,errors
    browser.close()
print('PASS: visual Insights, empty state, mobile layout, PDF, no task details, new statuses.')
