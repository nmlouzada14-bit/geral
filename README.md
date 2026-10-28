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

## Publicar na VPS com EasyPanel (recomendado para a VPS existente)

O EasyPanel e seu Traefik já gerenciam as portas 80/443. Crie um projeto/serviço separado; não altere os serviços n8n, Evolution API ou o proxy.

1. No EasyPanel, crie o projeto `contentos` e um serviço do tipo **App**, chamado `web`.
2. Configure a origem GitHub: `https://github.com/nmlouzada14-bit/geral`, branch `main`, contexto `/`. Se o repositório for privado, use a integração GitHub/chave de deploy do painel; não coloque tokens na URL.
3. Escolha o método de build **Dockerfile**, caminho `Dockerfile`. O comando de início já está definido na imagem.
4. Configure as variáveis de ambiente no painel: `INITIAL_PASSWORD` com a senha inicial escolhida (sem aspas no campo), `DATA_DIR=/data`, `PORT=8000`, `COOKIE_SECURE=1`.
5. Em armazenamento/mounts, adicione um **volume nomeado** `contentos-data` com destino `/data`, antes do primeiro deploy. Mantenha uma réplica. Use volume Docker, não um diretório do host sem configuração de permissões: a imagem roda com UID/GID 10001 e prepara `/data` para esse usuário.
6. Em domínios, use o domínio HTTPS gerado pelo painel ou um subdomínio próprio, encaminhando para HTTP na porta interna `8000`. Não exponha uma nova porta pública 80/443/8000: use o Traefik existente. Para domínio próprio, configure previamente o DNS para o IP da VPS.
7. Faça o deploy. Valide `/healthz` (HTTP 200 e `ok: true`), o login inicial e a troca de senha. Cadastre um integrante e uma tarefa; confira em outro navegador. Reinicie somente o serviço `contentos/web` e confirme que tarefa, acesso e anexo continuam presentes.

A imagem não contém `.env`, dados locais, chave de sessão ou credenciais StayCloud. O volume guarda o SQLite, os anexos e a chave de sessão. Não remova esse volume ao atualizar o serviço.

## Publicar na StayCloud

O projeto pode ser conectado com a CLI oficial `@staysdev/setup`. O token de acesso fica em `.staycloud/credentials.json` (ignorado pelo Git e com permissão 600). Nunca versione ou envie esse arquivo.

O build Python foi aceito pela StayCloud. O `Procfile` define Gunicorn em `0.0.0.0` e usa a porta `PORT` fornecida pela hospedagem, com fallback 8000. A publicação só está pronta após validar `/healthz`, login e persistência.

No painel do projeto configure:

- `INITIAL_PASSWORD`: senha inicial escolhida, em campo seguro; não incluir no código.
- `COOKIE_SECURE=1` para HTTPS.
- `DATA_DIR`: caminho de um volume persistente realmente montado, por exemplo `/data/contentos`. Definir só a variável não cria um volume.
- Uma única instância com esse volume; o SQLite e os anexos não podem depender do disco temporário do container.

A CLI de conexão/deploy utilizada não expõe configuração de variáveis e volumes. Se o painel não disponibilizar essas opções, é necessário configurar o serviço na VPS ou usar uma hospedagem que ofereça essas capacidades antes de operar com dados reais. Não substituir o banco compartilhado por dados locais do navegador.

## Regras de uso

- Semana de segunda a domingo; deadlines sem horário, com atraso calculado pela data de São Paulo.
- Filtro por semana atual, anterior, próxima ou intervalo personalizado de até 93 dias.
- Status: Pendente, Em andamento, Revisão, Criado, Postado e Atrasado.
- A partir do dia seguinte à deadline (São Paulo), tarefas que não estão em Criado ou Postado mudam para Atrasado. A atualização é persistida nas requisições autenticadas, inclusive no refresh automático da interface; não depende de alguém editar a tarefa. Tarefas criadas para datas passadas já recebem Atrasado. A versão é incrementada para proteger formulários antigos.
- Formatos repetem a frequência semanal a partir da data de início. Ao abrir um período são geradas e persistidas as entregas faltantes, sem duplicar as existentes. Não há scheduler externo necessário para visualizar o calendário.
- Formatos e lotes são agrupados visualmente por semana na lista; cada entrega é uma tarefa independente, não uma entidade pai que soma duas vezes no dashboard.
- Pausar um formato interrompe a geração de novas entregas. Não apaga as já existentes.
- Tarefa manual: quantidade total de 1 a 100. Com frequência, distribui essa quantidade nos próximos dias selecionados; sem frequência, repete a mesma deadline. Editar uma entrega não altera as demais.
- As cores são herdadas dos canais. Formatos e tarefas aceitam múltiplos canais; as tags mostram cada canal e sua cor. Cada entrega é contada uma vez no total de produção.
- Atualizações de outros navegadores são buscadas a cada 20 segundos quando a tela está ativa, sem interromper formulários abertos. Conflitos de edição pedem recarregamento, sem sobrescrever silenciosamente.
- Anexos autenticados, até 20 MB por envio; downloads não executam HTML no domínio do app.
- A aba de equipe e o cadastro de usuários são restritos ao e-mail administrador também na API. Não há cadastro público.
- A publicação nas redes sociais é feita pela equipe; marcar Postado não envia conteúdo às plataformas.

## Atualização: Insights, múltiplos canais e colaboração

No EasyPanel, use **Implantar** no serviço existente para buscar a nova versão de `main`. Preserve o volume montado em `/data`, as variáveis e o domínio configurado; não é necessário criar outro serviço. A migração roda no início do aplicativo.

- **Migração v2:** adiciona vínculos de múltiplos canais, comentários, menções e data de conclusão. Preserva usuários, hashes de senhas, tarefas, formatos e anexos. Antes de modificar um banco v1, cria um backup consistente em `DATA_DIR/backups/before-v2.sqlite`. Não atribui datas fictícias às conclusões antigas. A migração é transacional e não se repete quando `user_version>=2`.
- **Múltiplos canais:** um único conteúdo por tarefa, com diversos destinos. Não há status independente por canal nesta versão. Escolher um formato no formulário preenche seus canais; os destinos podem ser ajustados na tarefa. Não mescla automaticamente tarefas antigas com títulos semelhantes, para não perder conteúdo, comentários ou deadlines distintos.
- **Excluir formato:** remove o formato e interrompe novas gerações; preserva as tarefas existentes, seus canais, comentários e anexos. As tarefas ficam avulsas. A interface pede confirmação e permite cancelar.
- **Criação sem duplicação por reenvio:** uma solicitação de criação recebe um identificador único por formulário. Reenvios idênticos recuperam os mesmos IDs; pedidos simultâneos são serializados. Alterar um pedido que já foi salvo exige reabrir o formulário. A quantidade é o total de conteúdos, não o número de canais.
- **Editar formato:** campos compartilhados alterados (responsáveis, canais e frequência) são sincronizados com todas as tarefas vinculadas, inclusive finalizadas e fora do período visível. Renomear o formato atualiza títulos automáticos, preservando títulos personalizados. Status, prazos, comentários, anexos e datas de conclusão são mantidos. A nova agenda vale para slots futuros ainda não gerados; não reprograma nem remove entregas existentes. Campos não alterados no formato preservam ajustes individuais das tarefas. A versão das tarefas sincronizadas é incrementada para impedir que um formulário antigo sobrescreva a atualização.
- **Listas de produção:** demandas em aberto no topo; Criado na seção sempre aberta “Criados — aguardando postagem”; somente Postado na seção recolhida “Postados”. As três respeitam período, busca e responsável, e permitem ações em lote. Alterar o status move a tarefa para a seção correspondente. As métricas de entrega e a regra de atraso continuam considerando Criado e Postado como concluídos na produção.
- **Insights:** métricas e PDF usam o intervalo de deadlines selecionado e o estado atual das tarefas. Planejadas = conteúdos únicos; entregues = Criado + Postado; em aberto = planejadas menos entregues. São indicadores de produção, não de performance social. Distribuições por canal podem somar mais do que o total, porque um conteúdo pode ter vários canais.
- **Prazos:** a data de conclusão passa a ser registrada ao entrar em uma etapa entregue. Mudanças entre Criado/Postado preservam essa data. Reabrir limpa a data do ciclo atual. Conclusões antigas sem data ficam separadas da taxa de pontualidade.
- **PDF:** gerado no servidor autenticado com números e gráficos de planejadas x entregues, status, produção por deadline, prazos, pessoas e canais. Não inclui títulos ou listagem de tarefas. Intervalos de até 14 dias usam dias individuais; os maiores usam blocos de sete dias a partir da data inicial. Geração via `/api/insights.pdf?start=YYYY-MM-DD&end=YYYY-MM-DD`; sem serviços externos.
- **Comentários:** salvos separadamente dos campos da tarefa. Digitar `@` ou escolher uma pessoa insere a menção. O destinatário vê um aviso em **Menções**, inclusive para tarefas fora do período atual. Abrir os comentários marca as menções dessa tarefa como lidas apenas para o usuário atual. Não envia e-mails, WhatsApp ou notificações externas.
- **Métricas sociais:** Instagram, YouTube e TikTok ainda não estão conectados. Uma integração futura requer apps e permissões oficiais, autorização das contas e associação dos posts aos conteúdos. Não existe coleta automática de visualizações nesta versão.

Validação de atualização: abra Insights e exporte um PDF; confira uma tarefa com dois canais contando uma vez; finalize/reabra uma tarefa; envie uma menção a outro integrante e confira em um segundo navegador. Mantenha uma cópia externa do volume para recuperação além do backup de migração do banco.

## Validação

```bash
.venv/bin/pip install -r requirements-dev.txt
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

O roteiro `tests/browser_upgrade.py` testa Insights, PDF por intervalo, múltiplos canais, arquivamento, cores herdadas, tags no calendário, comentários e menções entre sessões. Requer uma instância isolada e vazia na porta 8004 (ou `TEST_URL`).

O roteiro `tests/browser_formats.py` valida uma tarefa em dois canais, simula perda de resposta após criação (retry sem duplicação), e testa cancelamento/exclusão de formato com preservação das entregas. Use uma instância isolada vazia na porta 8006, ou `TEST_URL`.

Canais podem ser editados ou excluídos na Linha editorial. A exclusão retira o canal das opções para novos conteúdos e dos formatos, mantendo os vínculos históricos das tarefas. Formatos que perdem todos os canais são pausados; edite e escolha outro canal antes de retomá-los.

Tarefas podem ser excluídas pelo modal de detalhes ou pelas caixas de seleção na visualização Lista (até 500 por operação, inclusive arquivadas). A confirmação mostra os itens selecionados. A exclusão é permanente e remove comentários, menções e anexos. Uma ocorrência automática excluída não é recriada pela recorrência; as próximas ocorrências continuam sendo geradas. IDs de tarefas excluídas não são reutilizados.

O roteiro `tests/browser_deletion.py` valida edição/exclusão de canais e exclusão individual/em lote com cancelamento. Requer uma instância isolada vazia na porta 8007 (ou `TEST_URL`). Os testes de API também verificam preservação de histórico, pausa de formatos sem canal, limpeza dos anexos, atomicidade do lote e supressão de recorrências após reinicialização.

- **Múltiplos responsáveis:** tarefas e formatos aceitam várias pessoas. Formatos exigem ao menos uma; tarefas podem ficar sem responsável. A seleção de várias pessoas não multiplica tarefas. Lista, Kanban, filtros, dashboard, Insights e PDF consideram todos os responsáveis. Cada tarefa conta uma vez no total geral e uma vez para cada pessoa vinculada na distribuição por pessoa.
- **Migração v3:** converte responsáveis únicos existentes em vínculos de equipe, preservando os campos legados para compatibilidade. Cria backup `DATA_DIR/backups/before-v3.sqlite` antes de atualizar bancos v2. A migração acontece uma única vez e não restaura responsáveis removidos depois.

`tests/browser_responsibles.py` valida sincronização de formato, seleção de várias pessoas, filtros e PDF em uma instância isolada vazia na porta 8008 (ou `TEST_URL`).

- **Migração v4:** converte Finalizado → Criado e Agendado → Postado, preservando IDs, vínculos e datas de conclusão. Antes de atualizar um banco v3, salva `DATA_DIR/backups/before-v4.sqlite`. Status antigos deixam de ser aceitos em novas edições.
- **Insights visuais:** gráficos de distribuição por status, planejadas x entregues, produção por deadline, prazos, pessoas e canais. Tela e PDF exibem agregados, sem detalhamento de tarefas. A série por deadline representa o estado atual das entregas daquele dia/semana, não uma série histórica de conclusões.

`tests/browser_insights.py` verifica estado vazio, gráficos, exportação PDF, nomes de status e layout mobile em instância isolada vazia na porta 8009 (ou `TEST_URL`).

- **Status em lote:** na Lista, selecione até 500 tarefas e clique em Alterar status. A confirmação mostra as tarefas e permite escolher o novo status. O lote é validado antes de ser aplicado: se uma tarefa foi alterada ou excluída, atualize a seleção. Mantém a regra de atraso e as datas de conclusão (Criado/Postado); reabrir limpa a data de conclusão. Também funciona com tarefas arquivadas.
- **Copiar tarefas:** botão discreto ao lado de Excluir selecionadas. Copia apenas a seleção atual, na ordem da lista, uma tarefa por linha no formato `Título - DD/MM`, usando a deadline. Se o navegador bloquear a área de transferência, apresenta o texto selecionado para cópia manual. A identificação numérica não aparece mais na lista ou no modal da tarefa.

`tests/browser_bulk_status.py` valida seleção, cópia, cancelamento, status em lote e reabertura de arquivadas em instância isolada vazia (porta 8010 ou `TEST_URL`).

### WhatsApp via Evolution API

Integração direta com a Evolution v2; não depende de n8n. O Docker inicia o Gunicorn com `gunicorn.conf.py`, cujo hook inicia o verificador em segundo plano quando a integração está habilitada e configurada. Verifica tarefas existentes aproximadamente a cada minuto, mesmo sem navegador aberto. O resumo diário também gera as ocorrências do dia atual, mesmo se ninguém abrir o calendário. Abrir outros períodos continua gerando suas respectivas ocorrências.

1. Implante a versão e cadastre os números em **Configurações → Equipe → Editar membro**. Use código do país + DDD + número, como `5511999999999`. Apenas o administrador pode consultar/editar números. Deixar vazio desativa alertas daquela pessoa.
2. No EasyPanel, **contentos / web → Ambiente**, acrescente as linhas abaixo às variáveis existentes. Substitua o valor de `EVOLUTION_API_KEY` pela chave válida da Evolution diretamente no painel, sem publicar no Git/chat:

```dotenv
EVOLUTION_API_URL=https://evolution-api-evolution-api.2dxvsk.easypanel.host
EVOLUTION_INSTANCE=zayedd
CONTENTOS_PUBLIC_URL=https://contentos-web.2dxvsk.easypanel.host
EVOLUTION_API_KEY=SUBSTITUA_PELA_CHAVE_NO_PAINEL
WHATSAPP_NOTIFICATIONS_ENABLED=1
```

3. Salve e implante novamente. Mantenha a instância `zayedd` conectada ao WhatsApp. A URL da API é a raiz, **sem `/manager/`**. O protocolo usa `POST /message/sendText/zayedd`, cabeçalho `apikey` e JSON `{number,text,linkPreview:false}`. HTTPS é obrigatório e redirecionamentos não são seguidos.
4. Configurações mostra se a integração está habilitada/configurada e os totais enviados à Evolution, pendentes, falhos e sem confirmação. “Enviado” significa aceito pela API com ID de mensagem, não confirmação de leitura/entrega pelo destinatário. Para conferir ao vivo, use uma tarefa atribuída a um número seu cadastrado e altere para Atrasado; esse passo envia uma mensagem real.

A mensagem inclui título, deadline e link `/?task=ID`, que abre o detalhe após login. Cada responsável com número cadastrado recebe uma mensagem por ocorrência de atraso. Se a tarefa sair de Atrasado e voltar, é uma nova ocorrência. Não se repetem notificações por refresh ou reinício. Destinatários são os responsáveis atuais na verificação; cadastrar número/atribuir uma pessoa a uma ocorrência ainda atrasada pode gerar seu alerta.

A fila fica no mesmo SQLite persistente, com chave única por tarefa, pessoa e ocorrência e reserva transacional entre workers. Antes de enviar, revalida status, ocorrência e responsável; pendências de tarefas resolvidas/desatribuídas são canceladas. Erro 429 tem até cinco tentativas com espera crescente. Falhas definitivas ficam registradas. Timeout, erro 5xx, resposta sem ID ou reinício durante envio são marcados como **sem confirmação** e não são reenviados automaticamente, pois a API pode já ter aceitado a mensagem. Confira esses casos no manager da Evolution. Não há garantia externa de entrega exatamente uma vez.

A migração v5 preserva dados e cria `DATA_DIR/backups/before-v5.sqlite` para bancos v4. Tarefas que já estavam em Atrasado antes da migração não recebem alertas acumulados; novas ocorrências são notificadas. Para interromper todos os envios, defina `WHATSAPP_NOTIFICATIONS_ENABLED=0` e implante. Nenhuma chave ou corpo de resposta da API é exibido nos logs/interface.

Testes automatizados usam remetentes simulados, sem enviar WhatsApp real. Cobrem payload, erros, duplicação, reinício, concorrência, permissões e cancelamento. `tests/browser_whatsapp.py` valida cadastro de números e links diretos após login numa instância isolada vazia na porta 8012 (ou `TEST_URL`), com notificações desativadas.

### Resumo diário no grupo e calendário

- O calendário permite filtrar por canal em Dia, Semana e Mês. Em cada dia, Postado aparece em verde e depois das demais tarefas. A cor original do canal é preservada fora do calendário.
- O grupo `120363426043140967@g.us` recebe diariamente às **9h de America/Sao_Paulo** o resumo `TAREFAS DO DIA - DD/MM` e `ATRASADAS`. O worker consulta o relógio a cada minuto; a chave persistente por data impede duplicação após reinício ou entre workers. Se o serviço iniciar depois das 9h sem ter gerado o resumo daquele dia, envia o resumo atual; não dispara resumos de dias anteriores.
- Tarefas do dia incluem todos os status conforme a deadline de hoje. A seção Atrasadas inclui tarefas de outros dias ainda abertas com prazo vencido ou status Atrasado. Criado/Postado não aparecem como atrasadas. Uma tarefa de hoje aparece apenas na primeira seção. As atrasadas voltam no resumo de cada dia enquanto continuarem abertas, sem repetir o alerta individual da mesma ocorrência.
- Conteúdos são agrupados pelo formato **e conjunto de responsáveis**. Lotes manuais sem formato usam o lote como agrupador. O formato `(3x)` indica três tarefas, nunca quantidade de canais. Todas as pessoas responsáveis são listadas; tarefas sem responsável mostram “Sem responsável”. Mensagens muito grandes são divididas em partes numeradas sem omitir tarefas; as partes são enviadas em ordem. Atrasos individuais mantêm a fila e a regra de envio único por ocorrência.
- Em Configurações, **Disparar mensagem** confirma e enfileira um resumo atualizado para o grupo, adicional ao automático. É processado pelo worker em cerca de um minuto. Repetir uma requisição do mesmo clique não duplica a fila; confirmar outro envio cria um novo resumo. O botão exige integração ativa e chave configurada. As métricas separam mensagens do grupo e alertas individuais. Mantém a política de não repetir automaticamente respostas ambíguas da Evolution.
- A edição de membro inclui nome, e-mail, cargo e WhatsApp, preservando senha, tarefas e permissões. O administrador pode trocar seu próprio e-mail sem perder acesso; o campo Cargo é descritivo e não concede administração. A migração v6 mantém a identidade administradora e cria a fila de resumos, com backup `before-v6.sqlite` para bancos v5.
- A instância Evolution precisa participar do grupo e poder enviar mensagens nele. As variáveis existentes da integração continuam válidas; nenhum n8n ou novo segredo é necessário.

`tests/browser_daily.py` valida filtro, ordenação/cor do calendário, edição de membro, espaçamento e fluxo do disparo manual em instância vazia na porta 8013 (ou `TEST_URL`). Respostas de envio são simuladas; os testes não enviam mensagens reais ao grupo.

`tests/browser_created.py` valida as três listas, transições Criado/Postado, filtros e persistência após recarregar, em instância isolada vazia na porta 8015 (ou `TEST_URL`).
