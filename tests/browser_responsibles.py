"""Run against a fresh isolated instance, never production."""
import os
from playwright.sync_api import sync_playwright, expect
URL=os.environ.get('TEST_URL','http://127.0.0.1:8008')
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
    req('/channels',{'name':'Canal','url':'https://example.com','color':'#123456'})
    req('/users',{'name':'Parceiro Teste','email':'partner@example.com','role':'Editor'})
    state=req('/state');today=state['today'];ch=state['channels'][0]['id']
    uid=next(u['id'] for u in state['users'] if u['email']=='partner@example.com')
    from datetime import date
    req('/formats',{'name':'Formato original','channel_ids':[ch],'responsible_ids':[1],'frequency':{str(date.fromisoformat(today).weekday()):1},'active_from':today})
    page.locator('.nav [data-page=editorial]').click()
    page.locator('[data-edit-format]').click()
    page.get_by_role('checkbox',name='Parceiro Teste',exact=True).check()
    page.get_by_label('Nome do formato').fill('Formato atualizado')
    page.get_by_role('button',name='Salvar formato',exact=True).click()
    expect(page.locator('#modal')).not_to_be_visible()
    page.locator('.nav [data-page=tasks]').click()
    expect(page.locator('tr[data-task]')).to_have_count(1)
    expect(page.locator('tr[data-task]')).to_contain_text('Formato atualizado')
    expect(page.locator('tr[data-task] .person')).to_have_count(2)
    page.locator('#filter-person').select_option(str(uid))
    expect(page.locator('tr[data-task]')).to_have_count(1)
    page.locator('tr[data-task]').click()
    expect(page.get_by_role('checkbox',name='Parceiro Teste',exact=True)).to_be_checked()
    expect(page.locator('[name=responsibles]:checked')).to_have_count(2)
    page.get_by_role('button',name='Cancelar',exact=True).click()
    page.get_by_role('button',name='Criar tarefa',exact=False).first.click()
    page.get_by_label('Título',exact=True).fill('Compartilhada manual')
    page.locator('[name=responsibles]').first.check()
    page.locator('[name=responsibles]').last.check()
    page.get_by_role('button',name='Criar tarefa(s)',exact=True).click()
    expect(page.locator('tr[data-task]')).to_have_count(2)
    assert all(len(t['responsible_ids'])==2 for t in req('/state')['tasks'])
    page.locator('.nav [data-page=insights]').click()
    expect(page.get_by_role('heading',name='Insights',exact=True)).to_be_visible()
    expect(page.locator('body')).to_contain_text('Parceiro Teste')
    with page.expect_download() as info:
        page.get_by_role('button',name='Exportar PDF',exact=False).click()
    assert info.value.failure() is None
    assert not errors,errors
    browser.close()
print('PASS: format synchronizes existing task, multiple assignees, filters, manual creation and PDF.')
