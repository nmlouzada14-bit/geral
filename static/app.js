"use strict";
const $ = (s) => document.querySelector(s),
  $$ = (s) => [...document.querySelectorAll(s)];
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const doneStates = ["Finalizado", "Agendado", "Postado"];
const isDelivered = (t) => doneStates.includes(t.status);
let insightReport = null,
  archiveOpen = false;
const states = [
  "Pendente",
  "Em andamento",
  "Revisão",
  "Finalizado",
  "Agendado",
  "Postado",
  "Atrasado",
];
const colors = [
  "#94a3b8",
  "#3b82f6",
  "#a78bfa",
  "#34b9a0",
  "#e5aa42",
  "#6189c7",
  "#df6b77",
];
const labels = [
  "Pendentes",
  "Em andamento",
  "Revisão",
  "Finalizados",
  "Agendados",
  "Postados",
  "Atrasados",
];
const days = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
const ADMIN = "nmlouzada14@gmail.com";
const paths = {
  insights: "M4 20V10 M10 20V4 M16 20v-7 M22 20H2",
  dashboard: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  tasks: "M9 5h12 M9 12h12 M9 19h12 M2 5l2 2 3-4 M2 12l2 2 3-4 M2 19l2 2 3-4",
  editorial: "M4 4h6l2 3h8v13H4z M8 12h8 M8 16h5",
  calendar: "M4 5h16v16H4z M4 10h16 M8 3v4 M16 3v4",
  settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2",
  logout: "M9 3H4v18h5 M9 12h12 M17 8l4 4-4 4",
  arrow: "M9 5l7 7-7 7",
};
const icon = (name) =>
  `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.tasks}"/></svg>`;
const parse = (v) => new Date(v + "T12:00:00");
const iso = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const add = (s, n) => {
  const d = parse(s);
  d.setDate(d.getDate() + n);
  return iso(d);
};
const localToday = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
const monday = (s) => add(s, -((parse(s).getDay() + 6) % 7));
const fmt = (s, opts = { day: "2-digit", month: "short" }) =>
  parse(s).toLocaleDateString("pt-BR", opts);
let user = null,
  data = {
    tasks: [],
    users: [],
    channels: [],
    formats: [],
    today: localToday(),
  },
  page = "dashboard",
  view = "list",
  calView = "week",
  anchor = localToday();
let start = monday(anchor),
  end = add(start, 6),
  period = "0",
  search = "",
  filterStatus = "",
  filterPerson = "",
  group = true,
  requestSeq = 0;
function toast(s) {
  $("#toast").textContent = s;
  $("#toast").classList.add("toast-show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(
    () => $("#toast").classList.remove("toast-show"),
    5000,
  );
}
async function api(path, method = "GET", body) {
  const options = { method, headers: { "X-ContentOS": "1" } };
  if (body instanceof FormData) options.body = body;
  else if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const r = await fetch("/api" + path, options);
  const d = await r.json();
  if (!r.ok) {
    if (r.status === 401 && path != "/login") {
      user = null;
      renderLogin();
    }
    throw new Error(d.error || "Não foi possível concluir.");
  }
  return d;
}
const person = (id) => data.users.find((x) => x.id === Number(id));
const channel = (id) => data.channels.find((x) => x.id === Number(id));
const format = (id) => data.formats.find((x) => x.id === Number(id));
const initials = (n) =>
  (n || "?")
    .split(" ")
    .map((x) => x[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
const avatar = (u) => `<span class="avatar">${esc(initials(u?.name))}</span>`;
const badge = (s) => {
  const i = states.indexOf(s);
  return `<span class="badge" style="--ink:${colors[i]};--tint:${colors[i]}15"><span class="dot" style="--accent:${colors[i]}"></span>${esc(s)}</span>`;
};
const taskChannels = (t) =>
  (t.channel_ids || (t.channel_id ? [t.channel_id] : []))
    .map(channel)
    .filter(Boolean);
const taskColor = (t) => taskChannels(t)[0]?.color || "#3b82f6";
const channelTag = (t) =>
  `<span class="channel-tags">${
    taskChannels(t).length
      ? taskChannels(t)
          .map(
            (c) =>
              `<span class="channel-tag" style="--accent:${c.color};background:${c.color}14;color:${c.color}"><span class="dot"></span>${esc(c.name)}</span>`,
          )
          .join("")
      : '<span class="muted">Sem canal</span>'
  }</span>`;
const assigned = (id) => {
  const u = person(id);
  return u
    ? `<span class="person">${avatar(u)}${esc(u.name.split(" ")[0])}</span>`
    : "<small>Sem responsável</small>";
};
const empty = (title, desc, action = "") =>
  `<div class="empty"><strong>${title}</strong>${desc}${action}</div>`;
async function refresh() {
  const seq = ++requestSeq;
  try {
    const query = `?start=${start}&end=${end}`;
    const [d, insights] = await Promise.all([
      api("/state" + query),
      page === "insights" ? api("/insights" + query) : Promise.resolve(null),
    ]);
    if (seq !== requestSeq) return;
    data = d;
    insightReport = insights?.report || null;
    render();
  } catch (e) {
    toast(e.message);
  }
}
function renderLogin(change = false) {
  $("#app").innerHTML =
    `<div class="login-screen"><aside class="login-aside"><div class="brand"><span class="brand-icon">c</span>content<em>OS</em></div><div><div class="eyebrow">ZAYED COMPANY · SOCIAL MEDIA</div><h1>Menos complexidade.<br>Mais conteúdo<br>no ar.</h1><p>Uma visão clara da semana. Do primeiro briefing ao próximo post, todo mundo na mesma página.</p><div class="login-art"><div><b>01</b>Planeje a semana</div><div><b>02</b>Organize a produção</div><div><b>03</b>Coloque no ar</div></div></div><small>Seu conteúdo. Seu time. Um só lugar.</small></aside><main class="login-main"><form class="login-form" id="login-form"><div class="eyebrow">SEU ESPAÇO DE PRODUÇÃO</div><h1>${change ? "Sua primeira entrada" : "Bom ter você por aqui."}</h1><p>${change ? "Crie sua senha pessoal para começar. Cada pessoa da equipe terá o próprio acesso." : "Entre para acompanhar a produção e organizar a próxima semana com o time."}</p>${change ? `<div class="field"><label for="current">Senha inicial</label><input id="current" name="current" type="password" autocomplete="current-password" required></div><div class="field"><label for="password">Nova senha pessoal</label><input id="password" name="password" type="password" autocomplete="new-password" minlength="10" required placeholder="Pelo menos 10 caracteres"></div>` : `<div class="field"><label for="email">Seu e-mail</label><input id="email" name="email" type="email" autocomplete="username" placeholder="voce@empresa.com" required></div><div class="field"><label for="password">Senha</label><input id="password" name="password" type="password" autocomplete="current-password" required placeholder="Sua senha"></div>`}<div class="error" role="alert"></div><button class="primary">${change ? "Salvar senha e entrar" : "Entrar no ContentOS →"}</button><div class="login-footer">Acesso exclusivo para pessoas cadastradas na equipe.</div></form></main></div>`;
  $("#login-form").onsubmit = async (e) => {
    e.preventDefault();
    const b = e.target.querySelector("button");
    b.disabled = true;
    try {
      const d = Object.fromEntries(new FormData(e.target));
      if (change) {
        await api("/password", "POST", d);
        user = await api("/me");
      } else user = await api("/login", "POST", d);
      if (user.must_change) renderLogin(true);
      else await refresh();
    } catch (err) {
      e.target.querySelector(".error").textContent = err.message;
    } finally {
      b.disabled = false;
    }
  };
}
function render() {
  if (!user) return;
  const titles = {
    dashboard: "Dashboard",
    tasks: "Tarefas",
    insights: "Insights",
    editorial: "Linha editorial",
    calendar: "Calendário editorial",
    settings: "Configurações",
  };
  $("#app").innerHTML =
    `<div class="layout"><aside class="sidebar"><div class="brand"><span class="brand-icon">c</span>content<em>OS</em></div><div class="workspace"><span class="workspace-mark">Z</span><div>Zayed Company<small>WORKSPACE DE CONTEÚDO</small></div></div><div class="nav-label">Seu workspace</div><nav class="nav" aria-label="Principal">${Object.entries(
      titles,
    )
      .filter(([k]) => k !== "settings" || user.email === ADMIN)
      .map(
        ([k, v]) =>
          `<button data-page="${k}" class="${page === k ? "active" : ""}">${icon(k)}${v}</button>`,
      )
      .join(
        "",
      )}</nav><div class="sidebar-bottom"><div class="weekly-note"><strong>Uma semana de cada vez.</strong>Planeje, acompanhe e publique.<br>O resto pode ser simples.</div><div class="profile">${avatar(user)}<div>${esc(user.name.split(" ")[0])}<br><small>${esc(user.role)}</small></div><button class="ghost" data-action="logout" aria-label="Sair">${icon("logout")}</button></div></div></aside><main class="main"><header class="topbar"><span>Workspace <span style="margin:0 10px;color:#c6ced9">/</span> <b>${titles[page]}</b></span><button class="ghost mentions-button" data-action="mentions">@ Menções${data.mentions?.length ? ` <span class="count">${data.mentions.length}</span>` : ""}</button><div class="live">Atualizado ${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })} · atualização a cada 20s</div><button class="ghost mobile-brand" data-action="logout">Sair</button></header><div class="content">${page === "dashboard" ? dashboard() : page === "tasks" ? tasksPage() : page === "editorial" ? editorial() : page === "calendar" ? calendar() : page === "insights" ? insightsPage() : settings()}</div></main></div>`;
  bind();
}
function heading(title, subtitle, button = "", eyebrow = "VISÃO DA SEMANA") {
  return `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p class="subtitle">${subtitle}</p></div>${button}</div>`;
}
const newTask = () =>
  '<button class="primary" data-action="new-task">＋ Criar tarefa</button>';
function periodControl() {
  return `<div class="toolbar"><div class="period"><button data-action="prev-period" aria-label="Semana anterior">‹</button><select id="period" aria-label="Período"><option value="0" ${period === "0" ? "selected" : ""}>Esta semana</option><option value="1" ${period === "1" ? "selected" : ""}>Próxima semana</option><option value="-1" ${period === "-1" ? "selected" : ""}>Semana passada</option><option value="custom" ${period === "custom" ? "selected" : ""}>Personalizado</option></select><button data-action="next-period" aria-label="Próxima semana">›</button>${period === "custom" ? `<input type="date" id="start" aria-label="Data inicial" value="${start}"><span>—</span><input type="date" id="end" aria-label="Data final" value="${end}">` : ""}</div><span class="range-label">${fmt(start, { day: "2-digit", month: "long" })} — ${fmt(end, { day: "2-digit", month: "long", year: "numeric" })}</span></div>`;
}
function filtered() {
  return data.tasks.filter(
    (t) =>
      (!search ||
        `${t.title} ${t.description}`
          .toLowerCase()
          .includes(search.toLowerCase())) &&
      (!filterStatus ||
        (filterStatus === "Atrasado"
          ? t.overdue || t.status === "Atrasado"
          : t.status === filterStatus)) &&
      (!filterPerson || String(t.responsible_id) === filterPerson),
  );
}
function table(tasks, grouped = false) {
  if (!tasks.length)
    return empty(
      "Tudo começa com uma boa pauta.",
      "Crie uma tarefa ou configure os formatos na linha editorial.",
      newTask(),
    );
  let rows = "";
  let groups = grouped
    ? tasks.reduce((m, t) => {
        const k = `${t.format_id ? "f" + t.format_id : t.batch || t.id}:${monday(t.deadline)}`;
        if (!m.has(k)) m.set(k, []);
        m.get(k).push(t);
        return m;
      }, new Map())
    : new Map([["all", tasks]]);
  for (const [key, items] of groups) {
    if (grouped && items.length > 1)
      rows += `<tr class="group-row"><td colspan="5">▾ &nbsp; ${esc(format(items[0].format_id)?.name || "Lote de tarefas")} <span class="muted">· ${items.length} entregas · semana de ${fmt(monday(items[0].deadline))}</span></td></tr>`;
    rows += items
      .map(
        (t) =>
          `<tr data-task="${t.id}" tabindex="0" role="button" aria-label="Abrir ${esc(t.title)}"><td><div class="task-title"><span class="dot" style="--accent:${taskColor(t)}"></span>${esc(t.title)}</div></td><td>${channelTag(t)}</td><td>${assigned(t.responsible_id)}</td><td>${fmt(t.deadline)}${t.overdue ? '<span class="late">Atrasada</span>' : ""}</td><td>${badge(t.status)}</td></tr>`,
      )
      .join("");
  }
  return `<div class="table-wrap"><table><thead><tr><th>Tarefa</th><th>Canal</th><th>Responsável</th><th>Deadline</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
function dashboard() {
  const counts = states.map(
    (s) =>
      data.tasks.filter((t) =>
        s === "Atrasado"
          ? t.overdue || t.status === "Atrasado"
          : t.status === s,
      ).length,
  );
  const total = data.tasks.length;
  const posted = counts[5];
  let dates = [];
  for (let d = start; d <= end; d = add(d, 1)) dates.push(d);
  let chartDays =
    dates.length <= 14 ? dates : dates.filter((d, i) => i % 7 === 0);
  const amounts = chartDays.map(
    (d) =>
      data.tasks.filter((t) =>
        dates.length <= 14
          ? t.deadline === d
          : t.deadline >= d && t.deadline <= add(d, 6),
      ).length,
  );
  const max = Math.max(...amounts, 1);
  const people = [
    ...data.users.map((u) => ({
      u,
      n: data.tasks.filter((t) => t.responsible_id === u.id).length,
    })),
    {
      u: { name: "Sem responsável" },
      n: data.tasks.filter((t) => !t.responsible_id).length,
    },
  ]
    .filter((x) => x.n)
    .sort((a, b) => b.n - a.n);
  const priorities = [...data.tasks]
    .filter((t) => !isDelivered(t))
    .sort((a, b) => a.deadline.localeCompare(b.deadline))
    .slice(0, 6);
  return (
    heading(
      "Sua produção, em um olhar.",
      "O que precisa acontecer, quem está fazendo e o que já está no ar.",
      newTask(),
    ) +
    periodControl() +
    `<div class="cards">${counts.map((n, i) => `<button class="stat" data-status="${states[i]}"><div class="stat-top">${labels[i]}<span class="dot" style="--accent:${colors[i]}"></span></div><div class="stat-num">${n}</div><div class="stat-foot">${i === 6 ? "Precisam de atenção" : total ? Math.round((n / total) * 100) + "% das entregas" : "Nenhuma entrega ainda"}</div></button>`).join("")}</div><div class="summary-band"><span><strong>${total ? `${posted} de ${total} entregas publicadas` : "Sua semana está pronta para ser planejada."}</strong>${total ? ` &nbsp; · &nbsp; ${counts[6] ? counts[6] + " entregas precisam de atenção." : "Tudo dentro do prazo por aqui."}` : " Configure sua linha editorial para gerar as tarefas."}</span><button data-page="${total ? "tasks" : "editorial"}">${total ? "Ver produção" : "Planejar conteúdo"} →</button></div><div class="dashboard-charts"><section class="panel"><div class="panel-head"><div><h2>${dates.length <= 14 ? "Entregas por dia" : "Entregas por semana"}</h2><p>Volume de conteúdo no período selecionado</p></div><span class="badge">${total} entregas</span></div><div class="panel-body"><div class="chart">${chartDays.map((d, i) => `<div class="chart-day"><span class="value">${amounts[i]}</span><div class="bar ${d === data.today ? "today" : ""}" style="height:${Math.max((amounts[i] / max) * 120, 3)}px"></div><small>${dates.length === 7 ? days[i] : fmt(d, { day: "2-digit", month: "2-digit" })}</small></div>`).join("")}</div></div></section><section class="panel"><div class="panel-head"><div><h2>Demandas por pessoa</h2><p>Uma visão da distribuição do time</p></div><span class="muted">${icon("tasks")}</span></div><div class="panel-body">${
      people.length
        ? people
            .slice(0, 6)
            .map(
              ({ u, n }) =>
                `<div class="people-row">${avatar(u)}<div class="people-meta"><div class="people-name"><span>${esc(u.name)}</span><small>${n} ${n === 1 ? "entrega" : "entregas"}</small></div><div class="track"><div style="width:${(n / Math.max(...people.map((x) => x.n))) * 100}%"></div></div></div></div>`,
            )
            .join("")
        : empty(
            "A equipe aparece aqui.",
            "As demandas serão distribuídas conforme os responsáveis.",
          )
    }</div></section>${deliveryPanel()}</div><section class="panel"><div class="panel-head"><div><h2>Próximas entregas</h2><p>As prioridades para tirar do caminho</p></div><button class="ghost" data-page="tasks">Ver todas →</button></div>${table(priorities)}</section><p class="subtitle">Atrasados considera a deadline e pode incluir tarefas de outras etapas. Finalizados, agendados e postados não entram nesse alerta.</p>`
  );
}
function tasksPage() {
  const tasks = filtered();
  const active = tasks.filter((t) => !isDelivered(t)),
    archived = tasks.filter(isDelivered);
  return (
    heading(
      "Tarefas",
      "Da ideia ao post. Acompanhe cada etapa da produção.",
      newTask(),
    ) +
    periodControl() +
    `<div class="task-tools"><div class="segmented"><button data-view="list" class="${view === "list" ? "selected" : ""}">☷ Lista</button><button data-view="kanban" class="${view === "kanban" ? "selected" : ""}">▥ Kanban</button></div><div class="filters"><input id="search" aria-label="Buscar tarefas" placeholder="Buscar tarefa…" value="${esc(search)}"><select id="filter-status" aria-label="Filtrar status"><option value="">Todos os status</option>${states.map((s) => `<option ${filterStatus === s ? "selected" : ""}>${s}</option>`).join("")}</select><select id="filter-person" aria-label="Filtrar responsável"><option value="">Toda a equipe</option>${data.users.map((u) => `<option value="${u.id}" ${filterPerson === String(u.id) ? "selected" : ""}>${esc(u.name)}</option>`).join("")}</select></div></div>${
      view === "list"
        ? `<div class="toolbar"><small>${tasks.length} entregas no período</small><label class="checkbox"><input id="group" type="checkbox" ${group ? "checked" : ""}>Agrupar por formato e semana</label></div><section class="panel">${active.length ? table(active, group) : empty("Nenhuma demanda em aberto neste filtro.", "As entregas concluídas ficam no quadro abaixo.")}</section><details class="archive-box panel" id="archive-box" ${archiveOpen || doneStates.includes(filterStatus) ? "open" : ""}><summary>Finalizadas / arquivadas <span class="badge">${archived.length}</span><small>Finalizados, agendados e postados · período selecionado</small></summary>${archived.length ? table(archived, group) : empty("Nenhuma entrega arquivada neste filtro.", "Ao finalizar uma tarefa, ela aparecerá aqui.")}</details>`
        : `<div class="kanban">${states
            .map((s, i) => {
              const items = tasks.filter((t) => t.status === s);
              return `<section class="column" data-drop="${s}"><div class="column-title"><span class="dot" style="--accent:${colors[i]}"></span>${s}<span class="count">${items.length}</span></div>${items.map((t) => `<article class="task-card" draggable="true" data-task="${t.id}" tabindex="0" role="button" aria-label="Abrir ${esc(t.title)}">${channelTag(t)}<h3>${esc(t.title)}</h3><div class="card-foot"><span>${fmt(t.deadline)}${t.overdue ? '<span class="late">Atrasada</span>' : ""}</span>${avatar(person(t.responsible_id))}</div></article>`).join("")}${!items.length ? '<div class="empty">Arraste uma tarefa para cá</div>' : ""}</section>`;
            })
            .join(
              "",
            )}</div><small>Arraste os cartões para atualizar a etapa. No celular, abra a tarefa e altere o status.</small>`
    }`
  );
}
function freqSummary(f) {
  const v = typeof f === "string" ? JSON.parse(f) : f;
  return Object.entries(v)
    .map(([d, n]) => `<span class="day-pill">${days[Number(d)]} · ${n}×</span>`)
    .join("");
}
function editorial() {
  return (
    heading(
      "Linha editorial",
      "Defina a frequência uma vez. A semana se organiza a partir daqui.",
      "",
      "PLANEJAMENTO",
    ) +
    `<div class="notice">Cada formato gera entregas automaticamente nos dias escolhidos. As tarefas são criadas ao abrir o período, sem duplicações, e aparecem na lista e no calendário.</div><div class="section-heading"><h2>Canais <small>· ${data.channels.length}</small></h2><button data-action="new-channel">＋ Criar canal</button></div>${data.channels.length ? `<div class="editorial-grid">${data.channels.map((c) => `<article class="channel-card" style="--accent:${c.color}"><span class="badge" style="--ink:${c.color};--tint:${c.color}12">CANAL</span><h3>${esc(c.name)}</h3><a href="${esc(c.url)}" target="_blank" rel="noopener noreferrer">${esc(c.url)} ↗</a><p class="subtitle">${data.formats.filter((f) => (f.channel_ids || [f.channel_id]).includes(c.id)).length} formatos cadastrados</p></article>`).join("")}</div>` : `<div class="panel">${empty("Onde seu conteúdo vai aparecer?", "Cadastre os perfis e canais usados pelo time.")}</div>`}<div class="section-heading"><h2>Formatos <small>· ${data.formats.length}</small></h2><button class="primary" data-action="new-format">＋ Criar formato</button></div><section class="panel">${data.formats.length ? data.formats.map((f) => `<div class="format-row"><span class="dot" style="--accent:${taskColor(f)}"></span><div class="format-info"><h3>${esc(f.name)} ${!f.active ? '<span class="badge">Pausado</span>' : ""}</h3><p>${channelTag(f)} · ${esc(person(f.responsible_id)?.name)} · A partir de ${fmt(f.active_from)}</p><div class="frequency-summary">${freqSummary(f.frequency)}</div></div><button data-edit-format="${f.id}">Editar</button><button data-toggle-format="${f.id}">${f.active ? "Pausar" : "Retomar"}</button></div>`).join("") : empty("Qual é o ritmo da sua produção?", "Selecione os dias, as quantidades e a pessoa responsável por cada formato.")} </section><p class="subtitle">Pausar impede novas gerações. As tarefas que já foram criadas permanecem disponíveis.</p>`
  );
}
function calendarRange() {
  if (calView === "day") {
    start = anchor;
    end = anchor;
  } else if (calView === "week") {
    start = monday(anchor);
    end = add(start, 6);
  } else {
    const d = parse(anchor);
    const first = iso(new Date(d.getFullYear(), d.getMonth(), 1, 12));
    const last = iso(new Date(d.getFullYear(), d.getMonth() + 1, 0, 12));
    start = monday(first);
    end = add(monday(last), 6);
  }
}
function calendar() {
  let dates = [];
  for (let d = start; d <= end; d = add(d, 1)) dates.push(d);
  return (
    heading(
      "Calendário editorial",
      "O que vai ao ar, no dia certo. Clique em uma entrega para atualizar.",
      newTask(),
    ) +
    `<div class="toolbar"><div class="period"><button data-action="prev-calendar" aria-label="Período anterior">‹</button><button data-action="today-calendar">Hoje</button><button data-action="next-calendar" aria-label="Próximo período">›</button><h2 style="margin-left:10px">${calView === "month" ? fmt(anchor, { month: "long", year: "numeric" }) : calView === "day" ? fmt(anchor, { day: "2-digit", month: "long" }) : fmt(start) + " — " + fmt(end)}</h2></div><div class="segmented">${[
      ["day", "Dia"],
      ["week", "Semana"],
      ["month", "Mês"],
    ]
      .map(
        ([v, l]) =>
          `<button data-cal="${v}" class="${calView === v ? "selected" : ""}">${l}</button>`,
      )
      .join(
        "",
      )}</div></div><div class="calendar ${calView}"><div class="calendar-head">${(calView === "day" ? [fmt(anchor, { weekday: "long" })] : days).map((d) => `<div>${d}</div>`).join("")}</div><div class="calendar-grid">${dates
      .map(
        (d) =>
          `<div class="calendar-day ${calView === "month" && d.slice(0, 7) !== anchor.slice(0, 7) ? "outside" : ""}"><span class="calendar-date ${d === data.today ? "today" : ""}">${parse(d).getDate()}</span>${data.tasks
            .filter((t) => t.deadline === d)
            .map(
              (t) =>
                `<button class="calendar-event" style="--accent:${taskColor(t)};--event-bg:${taskColor(t)}12" data-task="${t.id}">${esc(t.title)}${channelTag(t)}<small>${esc(t.status)}${t.overdue ? " · Atrasada" : ""}</small></button>`,
            )
            .join("")}</div>`,
      )
      .join(
        "",
      )}</div></div><div class="legend">${data.channels.map((c) => `<span><span class="dot" style="--accent:${c.color}"></span>${esc(c.name)}</span>`).join("")}</div>`
  );
}
function settings() {
  return (
    heading(
      "Seu time, no mesmo lugar.",
      "Gerencie quem pode acessar e atualizar a produção.",
      '<button class="primary" data-action="new-user">＋ Adicionar pessoa</button>',
      "CONFIGURAÇÕES",
    ) +
    `<div class="notice">Apenas ${ADMIN} tem acesso a esta área. A senha inicial configurada na hospedagem é usada para novos acessos; cada pessoa cria uma senha pessoal ao entrar.</div><section class="panel"><div class="panel-head"><h2>Equipe</h2><small>${data.users.length} pessoas</small></div><div class="table-wrap"><table><thead><tr><th>Pessoa</th><th>E-mail</th><th>Cargo</th><th>Acesso</th></tr></thead><tbody>${data.users.map((u) => `<tr><td><span class="person">${avatar(u)}${esc(u.name)}</span></td><td>${esc(u.email)}</td><td>${esc(u.role)}</td><td><span class="badge">${u.must_change ? "Primeiro acesso pendente" : "Ativo"}</span></td></tr>`).join("")}</tbody></table></div></section>`
  );
}
function field(label, name, type = "text", value = "", extra = "") {
  return `<div class="field"><label for="f-${name}">${label}</label><input id="f-${name}" name="${name}" type="${type}" value="${esc(value)}" ${extra}></div>`;
}
function selectField(label, name, items, value = "", required = false) {
  return `<div class="field"><label for="f-${name}">${label}</label><select id="f-${name}" name="${name}" ${required ? "required" : ""}><option value="">Selecionar</option>${items.map((x) => `<option value="${x.id}" ${String(value) === String(x.id) ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></div>`;
}
function frequencyInputs(freq = {}) {
  return `<div class="full field"><label>Frequência · quantidade por dia</label><div class="frequency">${days.map((d, i) => `<div><label for="freq-${i}">${d}</label><input id="freq-${i}" name="freq-${i}" type="number" min="0" max="30" value="${freq[i] || 0}" aria-label="Quantidade ${d}"></div>`).join("")}</div><small>Zero = sem entrega nesse dia.</small></div>`;
}
function modal(title, body, onSubmit, submit = "Salvar") {
  const el = $("#modal");
  el.innerHTML = `<div class="modal-head"><h2>${title}</h2><button class="ghost" data-close aria-label="Fechar">✕</button></div><form id="modal-form" class="modal-body">${body}<div class="error" role="alert"></div><div class="modal-foot"><button type="button" data-close>Cancelar</button><button class="primary" type="submit">${submit}</button></div></form>`;
  el.querySelectorAll("[data-close]").forEach(
    (b) => (b.onclick = () => el.close()),
  );
  el.showModal();
  el.querySelector("form").onsubmit = async (e) => {
    e.preventDefault();
    const button = e.target.querySelector("[type=submit]");
    button.disabled = true;
    try {
      await onSubmit(Object.fromEntries(new FormData(e.target)));
      el.close();
      await refresh();
    } catch (err) {
      e.target.querySelector(".error").textContent = err.message;
    } finally {
      button.disabled = false;
    }
  };
}
function getFreq(d) {
  const f = {};
  for (let i = 0; i < 7; i++) {
    if (Number(d["freq-" + i])) f[i] = Number(d["freq-" + i]);
    delete d["freq-" + i];
  }
  return f;
}
async function openTask(id) {
  let t;
  if (id) {
    try {
      t = await api("/tasks/" + id);
    } catch (e) {
      toast(e.message);
      return;
    }
  }
  const editing = !!t;
  const channels = data.channels;
  let taskIds = null,
    saved = false;
  const freq = t ? JSON.parse(t.frequency) : {};
  modal(
    editing ? "Detalhes da tarefa" : "Criar tarefa",
    `<div class="form-grid"><div class="full">${field("Título", "title", "text", t?.title || "", 'required maxlength="200" placeholder="O que vamos produzir?"')}</div><div class="full field"><label for="f-description">Descrição e links</label><textarea id="f-description" name="description" maxlength="20000" placeholder="Briefing, referências e links para a produção…">${esc(t?.description || "")}</textarea>${t ? `<div class="link-preview">${(t.description.match(/https?:\/\/[^\s<>"']+/g) || []).map((url, i) => `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">Referência ${i + 1} ↗</a>`).join("")}</div>` : ""}</div>${field("Deadline", "deadline", "date", t?.deadline || data.today, "required")}${selectField("Responsável", "responsible_id", data.users, t?.responsible_id)}${channelsPicker(t?.channel_ids || [])}${selectField(
      "Formato",
      "format_id",
      data.formats,
      t?.format_id,
    )}${selectField(
      "Status",
      "status",
      states.map((s) => ({ id: s, name: s })),
      t?.status || "Pendente",
      true,
    )}${editing ? `<div class="field"><label>Identificação</label><div class="notice" style="margin:0">Tarefa #${t.id}${t.slot ? " · Linha editorial" : ""}</div></div>` : field("Quantidade total de tarefas", "quantity", "number", 1, 'min="1" max="100" required')}${frequencyInputs(freq)}<div class="full"><p class="subtitle">${editing ? "Esta edição altera somente esta entrega. A frequência original fica registrada para consulta." : "Com frequência, a quantidade total é distribuída nos próximos dias selecionados, a partir da deadline. Sem frequência, todas recebem a mesma deadline."}</p></div><div class="full field" style="margin-top:20px"><label for="file">Anexos · até 20 MB por arquivo</label><input id="file" type="file" multiple>${editing ? `<div class="attachments">${t.attachments.map((a) => `<a href="/api/attachments/${a.id}" target="_blank" rel="noopener">↗ ${esc(a.name)}</a>`).join("")}</div>` : ""}<small>${editing ? "Arquivos disponíveis para todo o time." : "Anexos serão adicionados a cada tarefa criada."}</small></div></div>`,
    async (d) => {
      d.frequency = getFreq(d);
      d.channel_ids = selectedChannels();
      if (!saved) {
        if (editing) {
          await api("/tasks/" + id, "PATCH", { ...d, version: t.version });
          taskIds = [id];
        } else
          taskIds = (
            await api("/tasks", "POST", { ...d, quantity: Number(d.quantity) })
          ).ids;
        saved = true;
      }
      const files = [...$("#file").files];
      for (const tid of taskIds) {
        for (const file of files) {
          const key =
            tid + ":" + file.name + ":" + file.size + ":" + file.lastModified;
          if (openTask.uploaded.has(key)) continue;
          const form = new FormData();
          form.append("file", file);
          try {
            await api("/tasks/" + tid + "/attachments", "POST", form);
            openTask.uploaded.add(key);
          } catch (e) {
            throw new Error(
              "Tarefa salva, mas o anexo falhou: " +
                e.message +
                " Clique em salvar para tentar o anexo novamente.",
            );
          }
        }
      }
      toast(
        editing
          ? "Tarefa atualizada."
          : taskIds.length + " tarefa(s) criada(s).",
      );
    },
    editing ? "Salvar alterações" : "Criar tarefa(s)",
  );
  openTask.uploaded = new Set();
  $("#f-format_id").onchange = (e) => {
    const f = format(e.target.value);
    if (f)
      $$('#modal [name="channels"]').forEach((input) => {
        input.checked = f.channel_ids.includes(Number(input.value));
      });
  };
  if (editing) attachComments(id);
}

function openChannel() {
  modal(
    "Criar canal",
    field(
      "Nome do canal",
      "name",
      "text",
      "",
      'required placeholder="Instagram Claudio Zayed" maxlength="200"',
    ) +
      field(
        "Link do canal",
        "url",
        "url",
        "",
        'required placeholder="https://instagram.com/..."',
      ) +
      field("Cor do canal", "color", "color", "#3b82f6"),
    async (d) => {
      await api("/channels", "POST", d);
      toast("Canal criado.");
    },
    "Criar canal",
  );
}
function openFormat(id) {
  if (!data.channels.length) {
    toast("Cadastre um canal antes de criar o formato.");
    openChannel();
    return;
  }
  const f = format(id);
  modal(
    f ? "Editar formato" : "Criar formato",
    `<div class="form-grid"><div class="full">${field("Nome do formato", "name", "text", f?.name || "", 'required maxlength="200"')}</div>${channelsPicker(f?.channel_ids || [])}${selectField("Responsável", "responsible_id", data.users, f?.responsible_id || "", true)}${field("Começar em", "active_from", "date", f?.active_from || data.today, "required")}${frequencyInputs(f ? JSON.parse(f.frequency) : {})}<div class="full notice">As cores vêm dos canais. Um conteúdo com vários canais gera uma única tarefa por entrega. ${f ? "Alterações valem para novas entregas; as existentes são preservadas e podem ser editadas individualmente." : "A frequência se repete semanalmente."}</div></div>`,
    async (d) => {
      d.frequency = getFreq(d);
      d.channel_ids = selectedChannels();
      if (!d.channel_ids.length)
        throw new Error("Selecione pelo menos um canal.");
      await api("/formats" + (f ? "/" + id : ""), f ? "PATCH" : "POST", d);
      toast(
        f
          ? "Formato atualizado. As entregas existentes foram preservadas."
          : "Formato criado, sem duplicar conteúdo por canal.",
      );
    },
    f ? "Salvar formato" : "Criar formato e entregas",
  );
}
function openUser() {
  modal(
    "Adicionar pessoa",
    field("Nome", "name", "text", "", 'required maxlength="200"') +
      field("E-mail", "email", "email", "", "required") +
      field(
        "Cargo",
        "role",
        "text",
        "",
        'required placeholder="Social media, editor, designer…"',
      ) +
      '<div class="notice">A pessoa entrará com a senha inicial definida e deverá trocá-la no primeiro acesso. O cadastro não envia e-mail automaticamente.</div>',
    async (d) => {
      await api("/users", "POST", d);
      toast("Pessoa adicionada à equipe.");
    },
    "Adicionar pessoa",
  );
}
function navigate(p) {
  page = p;
  search = "";
  filterStatus = "";
  if (p === "calendar") {
    anchor = start;
    calendarRange();
  } else if (p === "dashboard" || p === "tasks" || p === "insights") {
    start = monday(anchor);
    end = add(start, 6);
    period = start === monday(data.today) ? "0" : "custom";
  }
  refresh();
}
function bind() {
  if ($("#archive-box"))
    $("#archive-box").ontoggle = (e) => {
      archiveOpen = e.target.open;
    };
  $$("[data-edit-format]").forEach(
    (b) => (b.onclick = () => openFormat(Number(b.dataset.editFormat))),
  );

  document
    .querySelectorAll("[data-page]")
    .forEach((b) => (b.onclick = () => navigate(b.dataset.page)));
  $$("[data-task]").forEach((b) => {
    b.onclick = () => openTask(Number(b.dataset.task));
    b.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openTask(Number(b.dataset.task));
      }
    };
    b.ondragstart = (e) => {
      e.dataTransfer.setData("text/plain", b.dataset.task);
      e.dataTransfer.effectAllowed = "move";
    };
  });
  $$("[data-status]").forEach(
    (b) =>
      (b.onclick = () => {
        page = "tasks";
        filterStatus = b.dataset.status;
        render();
      }),
  );
  $$("[data-view]").forEach(
    (b) =>
      (b.onclick = () => {
        view = b.dataset.view;
        render();
      }),
  );
  $$("[data-cal]").forEach(
    (b) =>
      (b.onclick = () => {
        calView = b.dataset.cal;
        calendarRange();
        refresh();
      }),
  );
  $$("[data-toggle-format]").forEach(
    (b) =>
      (b.onclick = async () => {
        const f = format(b.dataset.toggleFormat);
        try {
          await api("/formats/" + f.id, "PATCH", { active: !f.active });
          await refresh();
          toast(
            f.active
              ? "Formato pausado. Entregas existentes preservadas."
              : "Formato retomado.",
          );
        } catch (e) {
          toast(e.message);
        }
      }),
  );
  $$("[data-drop]").forEach((col) => {
    col.ondragover = (e) => {
      e.preventDefault();
      col.classList.add("drag-over");
    };
    col.ondragleave = () => col.classList.remove("drag-over");
    col.ondrop = async (e) => {
      e.preventDefault();
      col.classList.remove("drag-over");
      const t = data.tasks.find(
        (x) => x.id === Number(e.dataTransfer.getData("text/plain")),
      );
      if (!t) return;
      try {
        await api("/tasks/" + t.id, "PATCH", {
          status: col.dataset.drop,
          version: t.version,
        });
        toast("Status atualizado.");
        await refresh();
      } catch (err) {
        toast(err.message);
        await refresh();
      }
    };
  });
  $$("[data-action]").forEach(
    (b) =>
      (b.onclick = async () => {
        const a = b.dataset.action;
        if (a === "export-pdf") await downloadReport(b);
        if (a === "mentions") openMentions();
        if (a === "new-task") openTask();
        if (a === "new-channel") openChannel();
        if (a === "new-format") openFormat();
        if (a === "new-user") openUser();
        if (a === "logout") {
          await api("/logout", "POST");
          user = null;
          renderLogin();
        }
        if (a === "prev-period" || a === "next-period") {
          const n = a === "prev-period" ? -7 : 7;
          start = add(start, n);
          end = add(end, n);
          anchor = start;
          period = "custom";
          await refresh();
        }
        if (a.endsWith("calendar")) {
          if (a === "today-calendar") anchor = data.today;
          else {
            const n = a === "prev-calendar" ? -1 : 1;
            if (calView === "month") {
              const d = parse(anchor);
              anchor = iso(new Date(d.getFullYear(), d.getMonth() + n, 1, 12));
            } else anchor = add(anchor, n * (calView === "week" ? 7 : 1));
          }
          calendarRange();
          await refresh();
        }
      }),
  );
  if ($("#period"))
    $("#period").onchange = (e) => {
      period = e.target.value;
      if (period !== "custom") {
        start = add(monday(data.today), Number(period) * 7);
        end = add(start, 6);
        anchor = start;
        refresh();
      } else render();
    };
  for (const id of ["start", "end"])
    if ($("#" + id))
      $("#" + id).onchange = (e) => {
        const value = e.target.value;
        if (!value) return;
        const a = id === "start" ? value : start,
          b = id === "end" ? value : end;
        if (a > b || (parse(b) - parse(a)) / 86400000 > 92) {
          toast("Selecione um intervalo válido de até 93 dias.");
          render();
          return;
        }
        start = a;
        end = b;
        anchor = start;
        refresh();
      };
  if ($("#search"))
    $("#search").onchange = (e) => {
      search = e.target.value;
      render();
    };
  if ($("#filter-status"))
    $("#filter-status").onchange = (e) => {
      filterStatus = e.target.value;
      render();
    };
  if ($("#filter-person"))
    $("#filter-person").onchange = (e) => {
      filterPerson = e.target.value;
      render();
    };
  if ($("#group"))
    $("#group").onchange = (e) => {
      group = e.target.checked;
      render();
    };
}
(async () => {
  $("#app").innerHTML = '<div class="loading">Carregando seu workspace…</div>';
  try {
    user = await api("/me");
    if (user.must_change) renderLogin(true);
    else await refresh();
  } catch {
    renderLogin();
  }
})();
setInterval(() => {
  if (
    user &&
    !user.must_change &&
    !$("#modal").open &&
    !document.hidden &&
    !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)
  )
    refresh();
}, 20000);

function channelsPicker(selected = []) {
  return `<fieldset class="full channel-picker"><legend>Canais de publicação</legend>${data.channels.length ? data.channels.map((c) => `<label class="channel-choice"><input type="checkbox" name="channels" value="${c.id}" ${selected.includes(c.id) ? "checked" : ""}><span class="dot" style="--accent:${c.color}"></span>${esc(c.name)}</label>`).join("") : "<small>Cadastre os canais na Linha editorial.</small>"}<small>Selecione todos os canais que usarão este mesmo conteúdo.</small></fieldset>`;
}
function selectedChannels() {
  return $$('#modal [name="channels"]:checked').map((x) => Number(x.value));
}
function deliveryPanel() {
  const planned = data.tasks.length,
    delivered = data.tasks.filter(isDelivered).length;
  return `<section class="panel delivery-panel"><div class="panel-head"><div><h2>Planejadas x entregues</h2><p>Conteúdos únicos no período</p></div></div><div class="panel-body"><div class="delivery-total"><strong>${planned ? Math.round((delivered / planned) * 100) : 0}%</strong><span>de conclusão</span></div><div class="comparison-row"><span>Planejadas <b>${planned}</b></span><div class="track"><div style="width:${planned ? 100 : 0}%;background:#b6cff8"></div></div></div><div class="comparison-row"><span>Entregues <b>${delivered}</b></span><div class="track"><div style="width:${planned ? (delivered / planned) * 100 : 0}%;background:#3b82f6"></div></div></div><small>Entregues = Finalizados + Agendados + Postados. Filtro pela deadline.</small></div></section>`;
}
function insightsPage() {
  const r = insightReport;
  if (!r) return empty("Carregando relatório…", "");
  const metrics = [
    ["Planejadas", r.planned],
    ["Entregues", r.delivered],
    ["Em aberto", r.pending],
    ["Postadas", r.posted],
    ["Atrasadas", r.overdue],
    ["Conclusão", r.rate + "%"],
  ];
  const breakdown = (rows, first) =>
    `<div class="table-wrap"><table><thead><tr><th>${first}</th><th>Planejadas</th><th>Entregues</th><th>Em aberto</th><th>Atrasadas</th></tr></thead><tbody>${rows.length ? rows.map((x) => `<tr><td>${esc(x.name)}</td><td>${x.planned}</td><td>${x.delivered}</td><td>${x.pending}</td><td>${x.overdue}</td></tr>`).join("") : '<tr><td colspan="5">Sem demandas neste período.</td></tr>'}</tbody></table></div>`;
  return (
    heading(
      "Insights",
      "Um relatório claro da produção, pronto para levar à reunião.",
      '<button class="primary" data-action="export-pdf">↓ Exportar PDF</button>',
      "RELATÓRIO DE PRODUÇÃO",
    ) +
    periodControl() +
    `<div class="notice">Período filtrado pela deadline. Cada conteúdo conta uma vez, mesmo com vários canais. Entregues = Finalizados + Agendados + Postados. Os números refletem o status atual das tarefas.</div><div class="insight-stats">${metrics.map(([label, n]) => `<div class="stat"><div class="stat-top">${label}</div><div class="stat-num">${n}</div></div>`).join("")}</div><div class="grid-two">${deliveryPanel()}<section class="panel"><div class="panel-head"><h2>Prazos das entregas</h2></div><div class="panel-body"><div class="deadline-metrics"><p><strong>${r.on_time}</strong> no prazo</p><p><strong>${r.late_delivery}</strong> após o prazo</p><p><strong>${r.undated_delivery}</strong> sem data histórica</p></div><p class="subtitle">${r.on_time_rate === null ? "Sem datas de conclusão suficientes." : r.on_time_rate + "% das entregas com data registrada foram concluídas no prazo."} Entregas anteriores à atualização não recebem datas estimadas.</p></div></section></div><div class="grid-two"><section class="panel"><div class="panel-head"><h2>Por pessoa</h2></div>${breakdown(r.people, "Pessoa")}</section><section class="panel"><div class="panel-head"><div><h2>Por canal</h2><p>Um conteúdo pode aparecer em mais de um canal.</p></div></div>${breakdown(r.channels, "Canal")}</section></div><section class="panel report-section"><div class="panel-head"><h2>Entregas concluídas · ${r.delivered}</h2></div>${data.tasks.some(isDelivered) ? table(data.tasks.filter(isDelivered)) : empty("Nenhuma entrega concluída neste período.", "")}</section><section class="panel report-section"><div class="panel-head"><h2>Demandas em aberto · ${r.pending}</h2></div>${data.tasks.some((t) => !isDelivered(t)) ? table(data.tasks.filter((t) => !isDelivered(t))) : empty("Nenhuma demanda em aberto neste período.", "")}</section><div class="notice"><strong>Métricas das redes sociais</strong><br>Instagram, YouTube e TikTok ainda não estão conectados às APIs oficiais. Visualizações, alcance e engajamento não fazem parte deste relatório de produção.</div>`
  );
}
async function downloadReport(button) {
  button.disabled = true;
  try {
    const r = await fetch(`/api/insights.pdf?start=${start}&end=${end}`, {
      headers: { "X-ContentOS": "1" },
    });
    if (!r.ok) {
      const error = await r.json();
      throw new Error(error.error || "Não foi possível gerar o PDF.");
    }
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = `contentos-${start}-${end}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    toast("Relatório PDF gerado.");
  } catch (e) {
    toast(e.message);
  } finally {
    button.disabled = false;
  }
}
function commentBody(c) {
  let parts = [{ text: c.body, mention: false }];
  for (const u of [...c.mentions].sort(
    (a, b) => b.name.length - a.name.length,
  )) {
    const token = "@" + u.name;
    parts = parts.flatMap((p) =>
      p.mention
        ? [p]
        : p.text.split(token).flatMap((text, i) =>
            i
              ? [
                  { text: token, mention: true },
                  { text, mention: false },
                ]
              : [{ text, mention: false }],
          ),
    );
  }
  return parts
    .map((p) => (p.mention ? `<mark>${esc(p.text)}</mark>` : esc(p.text)))
    .join("");
}
function attachComments(id) {
  const section = document.createElement("section");
  section.className = "task-comments modal-body";
  section.innerHTML = `<h2>Comentários</h2><div class="comments-list" aria-live="polite">Carregando…</div><label for="comment-body">Escreva um comentário</label><textarea id="comment-body" maxlength="5000" placeholder="Compartilhe uma atualização ou digite @ para mencionar…"></textarea><div class="mention-suggestions" role="listbox" hidden></div><div class="comment-actions"><select id="mention-picker" aria-label="Mencionar membro"><option value="">@ Mencionar alguém</option>${data.users.map((u) => `<option value="${u.id}">${esc(u.name)}</option>`).join("")}</select><button type="button" class="primary" id="post-comment">Enviar comentário</button></div><div class="error" role="alert"></div><small>Comentários são enviados separadamente das alterações da tarefa. Menções geram avisos dentro do ContentOS.</small>`;
  $("#modal").appendChild(section);
  const input = section.querySelector("textarea");
  const selected = new Set();
  const suggestions = section.querySelector(".mention-suggestions");
  const pick = (uid) => {
    const u = person(uid);
    if (!u) return;
    const before = input.value.slice(0, input.selectionStart);
    const at = before.lastIndexOf("@");
    const from =
      at >= 0 && !before.slice(at).includes("\n") ? at : input.selectionStart;
    input.setRangeText("@" + u.name + " ", from, input.selectionEnd, "end");
    selected.add(u.id);
    suggestions.hidden = true;
    input.focus();
  };
  section.querySelector("select").onchange = (e) => {
    pick(Number(e.target.value));
    e.target.value = "";
  };
  input.oninput = () => {
    const before = input.value.slice(0, input.selectionStart),
      at = before.lastIndexOf("@");
    const term = at < 0 ? null : before.slice(at + 1);
    const users =
      term !== null && !term.includes("\n")
        ? data.users
            .filter((u) => u.name.toLowerCase().includes(term.toLowerCase()))
            .slice(0, 8)
        : [];
    suggestions.hidden = !users.length;
    suggestions.innerHTML = users
      .map(
        (u) =>
          `<button type="button" role="option" data-mention="${u.id}">${esc(u.name)}</button>`,
      )
      .join("");
    suggestions
      .querySelectorAll("button")
      .forEach((b) => (b.onclick = () => pick(Number(b.dataset.mention))));
  };
  const load = async () => {
    try {
      const result = await api(`/tasks/${id}/comments`);
      if (!section.isConnected) return;
      section.querySelector(".comments-list").innerHTML = result.comments.length
        ? result.comments
            .map(
              (c) =>
                `<article class="comment"><div class="comment-meta">${avatar({ name: c.author })}<strong>${esc(c.author)}</strong><time>${new Date(c.created_at).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", dateStyle: "short", timeStyle: "short" })}</time></div><p>${commentBody(c)}</p></article>`,
            )
            .join("")
        : '<p class="muted">Ainda não há comentários. Comece a conversa.</p>';
      await api(`/tasks/${id}/mentions/read`, "POST");
    } catch (e) {
      if (section.isConnected)
        section.querySelector(".error").textContent = e.message;
    }
  };
  section.querySelector("#post-comment").onclick = async (e) => {
    const body = input.value.trim();
    if (!body) {
      section.querySelector(".error").textContent =
        "Escreva um comentário antes de enviar.";
      return;
    }
    e.target.disabled = true;
    section.querySelector(".error").textContent = "";
    try {
      const mentions = [...selected].filter((uid) =>
        body.includes("@" + person(uid).name),
      );
      await api(`/tasks/${id}/comments`, "POST", { body, mentions });
      input.value = "";
      selected.clear();
      suggestions.hidden = true;
      await load();
      toast("Comentário enviado.");
    } catch (err) {
      section.querySelector(".error").textContent = err.message;
    } finally {
      e.target.disabled = false;
    }
  };
  load();
}
function openMentions() {
  const mentions = data.mentions || [];
  modal(
    "Menções para você",
    mentions.length
      ? mentions
          .map(
            (m) =>
              `<button type="button" class="mention-notice" data-mention-task="${m.task_id}"><strong>${esc(m.author)}</strong> mencionou você em <b>${esc(m.title)}</b><small>${new Date(m.created_at).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" })}</small></button>`,
          )
          .join("")
      : empty(
          "Nenhuma menção pendente.",
          "Você verá aqui os comentários que mencionarem seu nome.",
        ),
    async () => {},
    "Fechar",
  );
  $$("#modal [data-mention-task]").forEach(
    (b) =>
      (b.onclick = () => {
        $("#modal").close();
        openTask(Number(b.dataset.mentionTask));
      }),
  );
}
