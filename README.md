# ContentOS · Zayed

Gestão semanal de conteúdo com dashboard, lista/Kanban, linha editorial, calendário e equipe. Interface em português, azul-marinho `#102B55` e azul `#3B82F6`.

## Rodar

Requer Python 3.12. Use o checkout existente; cada tarefa de nuvem já é isolada. Não crie worktrees sem solicitação.

```bash
cd /workspace/geral
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # apenas se .env ainda não existir
# Edite .env localmente e preencha INITIAL_PASSWORD; não versione esse arquivo.
set -a
. ./.env
set +a
.venv/bin/gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 120 app:app
```

O administrador inicial é `nmlouzada14@gmail.com`. A senha de primeiro acesso vem de `INITIAL_PASSWORD`; novos integrantes recebem essa mesma senha temporária e precisam criar uma senha pessoal de pelo menos 10 caracteres. A senha não é enviada por e-mail. Não inclua credenciais no código ou nas URLs.

Dados, hashes de senhas, chave de sessão e anexos são armazenados em `DATA_DIR` (padrão `./data`), fora do Git. O primeiro início cria um workspace vazio, sem exemplos de teste. `/healthz` verifica o servidor e o banco. Teste de login e uma tarefa confirmam o fluxo funcional.

## Publicar online pelo GitHub + Render

GitHub guarda o código. GitHub Pages sozinho não executa este backend nem mantém o banco compartilhado.

1. No Render, conecte sua conta do GitHub e escolha **New → Blueprint**.
2. Selecione `nmlouzada14-bit/geral`, branch `main`. O Render lê `render.yaml`.
3. Preencha `INITIAL_PASSWORD` no campo seguro do Render com a senha inicial escolhida. Não use aspas em volta do valor no painel.
4. Revise o plano e o disco persistente antes de contratar/publicar. O blueprint seleciona `starter` com disco de 1 GB; consulte os preços atuais no Render. O workspace não pode depender de disco temporário de um plano gratuito.
5. Faça o deploy. Acesse o endereço HTTPS fornecido pelo Render, entre com o administrador e troque a senha. Cadastre o time em Configurações.
6. Valide também com um segundo usuário/navegador: abrir tarefa, alterar status, observar a atualização no primeiro navegador em até 20 segundos e confirmar que Configurações não aparece para o segundo usuário.

O runtime nativo Python usa o mesmo comando Gunicorn validado localmente. `COOKIE_SECURE=1` exige HTTPS em produção. O disco mantém SQLite, uploads e chave de sessão entre reinicializações. Mantenha uma única instância com esse disco; esta versão não usa banco distribuído. Não ative múltiplas réplicas com bancos locais separados.

Faça backup consistente do SQLite usando a API de backup do SQLite, junto com `uploads/` e `session.key`, para armazenamento privado antes de operações de manutenção. Não copie apenas o arquivo `.sqlite` enquanto houver escritas/WAL. Regras de backup e recuperação da hospedagem precisam ser configuradas na conta do proprietário.

Nenhuma conta, contratação ou publicação no Render é realizada automaticamente por este repositório.

## Regras de uso

- Semana de segunda a domingo; deadlines sem horário, com atraso calculado pela data de São Paulo.
- Filtro por semana atual, anterior, próxima ou intervalo personalizado de até 93 dias.
- Status: Pendente, Em andamento, Revisão, Finalizado, Agendado, Postado e Atrasado.
- Atraso também é um alerta derivado da deadline, sem substituir o status de produção. Agendado e Postado ficam fora do alerta. O cartão de atrasados pode se sobrepor aos demais.
- Formatos repetem a frequência semanal a partir da data de início. Ao abrir um período são geradas e persistidas as entregas faltantes, sem duplicar as existentes. Não há scheduler externo necessário para visualizar o calendário.
- Formatos e lotes são agrupados visualmente por semana na lista; cada entrega é uma tarefa independente, não uma entidade pai que soma duas vezes no dashboard.
- Pausar um formato interrompe a geração de novas entregas. Não apaga as já existentes.
- Tarefa manual: quantidade total de 1 a 100. Com frequência, distribui essa quantidade nos próximos dias selecionados; sem frequência, repete a mesma deadline. Editar uma entrega não altera as demais.
- Cores dos formatos prevalecem sobre as dos canais nas tarefas e no calendário.
- Atualizações de outros navegadores são buscadas a cada 20 segundos quando a tela está ativa, sem interromper formulários abertos. Conflitos de edição pedem recarregamento, sem sobrescrever silenciosamente.
- Anexos autenticados, até 20 MB por envio; downloads não executam HTML no domínio do app.
- A aba de equipe e o cadastro de usuários são restritos ao e-mail administrador também na API. Não há cadastro público.
- A publicação nas redes sociais é feita pela equipe; marcar Agendado/Postado não envia conteúdo às plataformas.

## Validação

```bash
.venv/bin/python -m unittest discover -s tests -v
node --check static/app.js
```

Os testes usam banco temporário e cobrem autenticação, permissões, recorrência, pausa, quantidades, concorrência, compartilhamento, anexos, atrasos e persistência.

Teste de navegador em uma instância **isolada e vazia**, nunca em produção:

```bash
.venv/bin/pip install -r requirements-dev.txt
# Exige Chromium em /usr/bin/chromium.
# Defina DATA_DIR como diretório temporário vazio e INITIAL_PASSWORD como a senha
# de teste indicada em tests/browser_smoke.py. Inicie Gunicorn na porta 8001.
.venv/bin/python tests/browser_smoke.py
```

O roteiro testa o primeiro acesso, cadastro da equipe, canais/formatos, geração de tarefas, drag-and-drop, upload, calendário, filtros, mobile e duas sessões independentes. Capturas são gravadas em `/tmp/contentos-screenshots`, com dados explicitamente fictícios. Não mistura esses dados com o workspace real.
