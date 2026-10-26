"""Run on a fresh isolated instance; exercises a lost response after task creation."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright,expect
URL=os.environ.get('TEST_URL','http://127.0.0.1:8006')
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    context=browser.new_context();page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(URL);page.get_by_label('Seu e-mail').fill('nmlouzada14@gmail.com');page.get_by_label('Senha',exact=True).fill('Initial-Test-2026!');page.get_by_role('button',name='Entrar no ContentOS').click()
    page.get_by_label('Senha inicial').fill('Initial-Test-2026!');page.get_by_label('Nova senha pessoal').fill('Personal-Test-2026!');page.get_by_role('button',name='Salvar senha e entrar').click()
    expect(page.get_by_role('heading',name='Sua produção, em um olhar.')).to_be_visible()
    def req(path,body=None):
        r=context.request.fetch(URL+'/api'+path,method='POST' if body is not None else 'GET',data=body,headers={'X-ContentOS':'1'})
        assert r.ok,r.text()
        return r.json()
    for name in ['Canal A','Canal B']:
        req('/channels',{'name':name,'url':'https://example.com','color':'#3b82f6'})
    page.locator('.nav [data-page=tasks]').click();page.get_by_role('button',name='Criar tarefa',exact=False).first.click()
    page.get_by_label('Título',exact=True).fill('Um conteúdo em dois canais')
    page.get_by_role('checkbox',name='Canal A').check();page.get_by_role('checkbox',name='Canal B').check()
    expect(page.locator('#creation-summary')).to_contain_text('1 tarefa(s), cada uma com 2 canal(is)')
    def lose_response(route):
        r=route.fetch();assert r.status==201
        route.abort()
    page.route('**/api/tasks',lose_response,times=1)
    page.get_by_role('button',name='Criar tarefa(s)').click()
    expect(page.locator('#modal-form .error')).not_to_be_empty()
    page.get_by_role('button',name='Criar tarefa(s)').click()
    expect(page.locator('#modal')).not_to_be_visible()
    expect(page.locator('tr[data-task]')).to_have_count(1)
    expect(page.locator('tr[data-task] .channel-tag')).to_have_count(2)
    today=datetime.now(ZoneInfo('America/Sao_Paulo')).date()
    req('/formats',{'name':'Formato excluível','channel_ids':[1,2],'responsible_id':1,'frequency':{str(today.weekday()):1},'active_from':str(today)})
    page.locator('.nav [data-page=editorial]').click()
    page.locator('[data-delete-format]').click()
    expect(page.get_by_role('heading',name='Excluir formato')).to_be_visible()
    expect(page.locator('#modal')).to_contain_text('Todas as tarefas já criadas serão mantidas')
    page.get_by_role('button',name='Cancelar',exact=True).click()
    expect(page.locator('[data-delete-format]')).to_have_count(1)
    page.locator('[data-delete-format]').click();page.get_by_role('button',name='Excluir formato',exact=True).click()
    expect(page.locator('#modal')).not_to_be_visible()
    expect(page.locator('[data-delete-format]')).to_have_count(0)
    page.locator('.nav [data-page=tasks]').click()
    expect(page.locator('tr[data-task]')).to_have_count(2)
    state=req('/state?start='+str(today)+'&end='+str(today))
    assert len(state['tasks'])==2 and not state['formats']
    assert all(t['channel_ids']==[1,2] for t in state['tasks'])
    assert not errors,errors
    browser.close()
print('PASS: one task/two channels, lost-response retry without duplication, deletion confirmation/cancel and preservation of deliveries.')
