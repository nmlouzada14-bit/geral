"""Run against a fresh isolated instance, never production."""
import os
from playwright.sync_api import sync_playwright, expect
URL=os.environ.get('TEST_URL','http://127.0.0.1:8013')
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
    for name,color in [('Canal A','#ff0000'),('Canal B','#3b82f6')]:
        req('/channels',{'name':name,'url':'https://example.com','color':color})
    state=req('/state');today=state['today'];channels=state['channels'];a=channels[0]['id'];b=channels[1]['id']
    req('/tasks',{'title':'Postado primeiro','deadline':today,'channel_ids':[a],'status':'Postado'})
    req('/tasks',{'title':'Aberto A','deadline':today,'channel_ids':[a]})
    req('/tasks',{'title':'Aberto B','deadline':today,'channel_ids':[b]})
    page.locator('.nav [data-page=calendar]').click()
    page.locator('#calendar-channel').select_option(str(a))
    expect(page.locator('.calendar-event')).to_have_count(2)
    expect(page.locator('.calendar-event').first).to_contain_text('Aberto A')
    expect(page.locator('.calendar-event').last).to_contain_text('Postado primeiro')
    assert page.locator('.calendar-event.posted').evaluate("el=>getComputedStyle(el).getPropertyValue('--accent').trim()")=='#16834a'
    for mode in ['day','month','week']:
        page.locator('[data-cal='+mode+']').click()
        page.locator('[data-action=today-calendar]').click()
        expect(page.locator('#calendar-channel')).to_have_value(str(a))
        expect(page.locator('.calendar-event')).to_have_count(2)
    page.locator('.nav [data-page=settings]').click()
    page.locator('[data-edit-member]').click()
    page.get_by_label('Nome',exact=True).fill('Admin editado')
    page.get_by_label('E-mail',exact=True).fill('admin-edited@example.com')
    page.get_by_label('Cargo',exact=True).fill('Direção')
    page.get_by_label('WhatsApp com país e DDD').fill('5511999999999')
    page.get_by_role('button',name='Salvar membro',exact=True).click()
    expect(page.locator('#modal')).not_to_be_visible()
    expect(page.locator('body')).to_contain_text('admin-edited@example.com')
    expect(page.locator('body')).not_to_contain_text('Uma mensagem por responsável a cada ocorrência')
    assert page.locator('.whatsapp-panel').evaluate("el=>parseFloat(getComputedStyle(el).marginTop)")>=24
    # Simulate configuration and dispatch response without sending any real message.
    def configured(route):
        response=route.fetch();body=response.json();body['enabled']=True;body['configured']=True
        route.fulfill(json=body)
    page.route('**/api/integrations/whatsapp',configured)
    page.route('**/api/integrations/whatsapp/daily',lambda route:route.fulfill(status=202,json={'ok':True,'queued':True}))
    page.reload()
    page.locator('.nav [data-page=settings]').click()
    page.get_by_role('button',name='Disparar mensagem',exact=True).click()
    expect(page.locator('#modal')).to_contain_text('tarefas do dia e as atrasadas')
    page.get_by_role('button',name='Enviar para o grupo',exact=True).click()
    expect(page.locator('#modal')).not_to_be_visible()
    page.set_viewport_size({'width':1280,'height':900})
    page.screenshot(path='/tmp/contentos-settings-daily.png',full_page=True)
    assert not errors,errors
    browser.close()
print('PASS: calendar channel filter, green posted sorting, edit member, panel spacing and manual dispatch UI.')
