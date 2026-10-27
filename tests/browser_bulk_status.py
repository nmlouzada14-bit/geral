"""Run against a fresh isolated instance, never production."""
import os
from playwright.sync_api import sync_playwright, expect
URL=os.environ.get('TEST_URL','http://127.0.0.1:8010')
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
    today=req('/state')['today']
    req('/tasks',{'title':'Lote de teste','deadline':today,'quantity':3})
    page.locator('.nav [data-page=tasks]').click()
    page.locator('[data-select-task]').nth(0).check()
    page.locator('[data-select-task]').nth(1).check()
    context.grant_permissions(['clipboard-read','clipboard-write'])
    page.locator('#copy-selected').click()
    from datetime import date
    expected='\n'.join('Lote de teste · '+str(i)+' - '+date.fromisoformat(today).strftime('%d/%m') for i in [1,2])
    assert page.evaluate('navigator.clipboard.readText()')==expected
    expect(page.locator('.task-origin')).to_have_count(0)
    page.locator('tr[data-task]').first.click()
    expect(page.locator('#modal')).not_to_contain_text('Identificação')
    page.get_by_role('button',name='Cancelar',exact=True).click()
    page.locator('#status-selected').click()
    expect(page.locator('.delete-preview li')).to_have_count(2)
    page.get_by_label('Novo status',exact=True).select_option('Criado')
    page.get_by_role('button',name='Cancelar',exact=True).click()
    assert all(t['status']=='Pendente' for t in req('/state')['tasks'])
    page.locator('#status-selected').click()
    page.get_by_label('Novo status',exact=True).select_option('Criado')
    page.get_by_role('button',name='Aplicar status',exact=True).click()
    expect(page.locator('#modal')).not_to_be_visible()
    assert [t['status'] for t in req('/state')['tasks']].count('Criado')==2
    expect(page.locator('#status-selected')).to_be_disabled()
    page.locator('#archive-box summary').click()
    expect(page.locator('#archive-box tr[data-task]')).to_have_count(2)
    page.locator('#archive-box [data-select-table]').check()
    page.locator('#status-selected').click()
    page.get_by_label('Novo status',exact=True).select_option('Revisão')
    page.get_by_role('button',name='Aplicar status',exact=True).click()
    expect(page.locator('#modal')).not_to_be_visible()
    expect(page.locator('#archive-box tr[data-task]')).to_have_count(0)
    assert [t['status'] for t in req('/state')['tasks']].count('Revisão')==2
    page.locator('[data-select-task]').first.check()
    page.evaluate("Object.defineProperty(navigator, 'clipboard', {value:{writeText:()=>Promise.reject(new Error('denied'))}, configurable:true})")
    page.locator('#copy-selected').click()
    expect(page.get_by_label('Tarefas para copiar')).to_contain_text('Lote de teste')
    page.get_by_role('button',name='Fechar',exact=True).last.click()
    assert not errors,errors
    browser.close()
print('PASS: select two tasks, cancel, bulk status update, archive and reopen.')
