"""Run against a fresh isolated instance, never production."""
import os
from playwright.sync_api import sync_playwright, expect
URL=os.environ.get('TEST_URL','http://127.0.0.1:8012')
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
    page.locator('.nav [data-page=settings]').click()
    expect(page.get_by_role('heading',name='Alertas pelo WhatsApp')).to_be_visible()
    expect(page.locator('body')).to_contain_text('Desativado')
    page.locator('[data-whatsapp]').click()
    page.get_by_label('WhatsApp com país e DDD').fill('+55 (11) 99999-9999')
    page.get_by_role('button',name='Salvar WhatsApp',exact=True).click()
    expect(page.locator('#modal')).not_to_be_visible()
    expect(page.locator('body')).to_contain_text('5511999999999')
    today=req('/state')['today']
    tid=req('/tasks',{'title':'Link de alerta','deadline':today})['ids'][0]
    page.goto(URL+'/?task='+str(tid))
    expect(page.get_by_role('heading',name='Detalhes da tarefa')).to_be_visible()
    expect(page.get_by_label('Título',exact=True)).to_have_value('Link de alerta')
    page.get_by_role('button',name='Cancelar',exact=True).click()
    # The link survives a login screen and opens after authentication.
    context.clear_cookies()
    page.goto(URL+'/?task='+str(tid))
    page.get_by_label('Seu e-mail').fill('nmlouzada14@gmail.com')
    page.get_by_label('Senha',exact=True).fill('Personal-Test-2026!')
    page.get_by_role('button',name='Entrar no ContentOS').click()
    expect(page.get_by_label('Título',exact=True)).to_have_value('Link de alerta')
    assert not errors,errors
    browser.close()
print('PASS: WhatsApp settings and direct task links before/after login; no messages sent.')
