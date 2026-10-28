import os, sqlite3, secrets, json, re, hashlib, time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from functools import wraps
from urllib.parse import urlsplit
from flask import Flask, request, jsonify, session, send_file, abort, has_request_context
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

ROOT = Path(__file__).parent
DATA = Path(os.environ.get('DATA_DIR', ROOT / 'data'))
DATA.mkdir(parents=True, exist_ok=True)
secret_file = DATA / 'session.key'
if not secret_file.exists():
    try:
        with secret_file.open('x') as f:
            os.chmod(secret_file, 0o600)
            f.write(secrets.token_hex(32))
    except FileExistsError:
        pass
app = Flask(__name__, static_folder='static')
app.config.update(SECRET_KEY=secret_file.read_text(), MAX_CONTENT_LENGTH=20*1024*1024,
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE') == '1',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12))
ADMIN = 'nmlouzada14@gmail.com'
DONE = ('Criado', 'Postado')
STATES = ['Pendente', 'Em andamento', 'Revisão', 'Criado', 'Postado', 'Atrasado']

def db():
    c = sqlite3.connect(DATA / 'contentos.sqlite', timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def today():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).date()

def init():
    # Preserve a consistent pre-migration snapshot, including WAL contents.
    with db() as source:
        old = source.execute("SELECT 1 FROM sqlite_master WHERE name='tasks'").fetchone()
        version = source.execute('PRAGMA user_version').fetchone()[0]
        if old and version < 6:
            backup = DATA / 'backups' / ('before-v2.sqlite' if version < 2 else 'before-v3.sqlite' if version < 3 else 'before-v4.sqlite' if version < 4 else 'before-v5.sqlite' if version < 5 else 'before-v6.sqlite')
            backup.parent.mkdir(exist_ok=True)
            if not backup.exists():
                with sqlite3.connect(backup) as target:
                    source.backup(target)
                os.chmod(backup, 0o600)
    with db() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, role TEXT NOT NULL, password TEXT NOT NULL, must_change INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS channels(id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL, color TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS formats(id INTEGER PRIMARY KEY, name TEXT NOT NULL, channel_id INTEGER NOT NULL REFERENCES channels(id), responsible_id INTEGER REFERENCES users(id), color TEXT NOT NULL, frequency TEXT NOT NULL, active_from TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', deadline TEXT NOT NULL, responsible_id INTEGER REFERENCES users(id), channel_id INTEGER REFERENCES channels(id), format_id INTEGER REFERENCES formats(id), status TEXT NOT NULL, frequency TEXT NOT NULL DEFAULT '{}', batch TEXT, slot TEXT UNIQUE, version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS attachments(id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id), name TEXT NOT NULL, disk TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS task_requests(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, request_id TEXT NOT NULL, payload_hash TEXT NOT NULL, task_ids TEXT NOT NULL, PRIMARY KEY(user_id,request_id));
        CREATE TABLE IF NOT EXISTS task_id_sequence(id INTEGER PRIMARY KEY AUTOINCREMENT);
        CREATE TABLE IF NOT EXISTS suppressed_slots(slot TEXT PRIMARY KEY, format_id INTEGER NOT NULL REFERENCES formats(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS login_attempts(key TEXT PRIMARY KEY, count INTEGER NOT NULL, reset_at REAL NOT NULL);
        ''')
        c.execute('BEGIN IMMEDIATE')
        if 'deleted' not in {r['name'] for r in c.execute('PRAGMA table_info(channels)')}:
            c.execute('ALTER TABLE channels ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0')
        c.execute('INSERT OR IGNORE INTO task_id_sequence(id) SELECT MAX(id) FROM tasks HAVING MAX(id) IS NOT NULL')
        if c.execute('PRAGMA user_version').fetchone()[0] < 2:
            columns = {r['name'] for r in c.execute('PRAGMA table_info(tasks)')}
            if 'completed_at' not in columns:
                c.execute('ALTER TABLE tasks ADD COLUMN completed_at TEXT')
            c.execute('CREATE TABLE IF NOT EXISTS task_channels(task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE, channel_id INTEGER NOT NULL REFERENCES channels(id), PRIMARY KEY(task_id,channel_id))')
            c.execute('CREATE TABLE IF NOT EXISTS format_channels(format_id INTEGER NOT NULL REFERENCES formats(id) ON DELETE CASCADE, channel_id INTEGER NOT NULL REFERENCES channels(id), PRIMARY KEY(format_id,channel_id))')
            c.execute('INSERT OR IGNORE INTO task_channels SELECT id,channel_id FROM tasks WHERE channel_id IS NOT NULL')
            c.execute('INSERT OR IGNORE INTO format_channels SELECT id,channel_id FROM formats WHERE channel_id IS NOT NULL')
            c.execute('CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE, author_id INTEGER NOT NULL REFERENCES users(id), body TEXT NOT NULL, created_at TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS comment_mentions(comment_id INTEGER NOT NULL REFERENCES comments(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id), read_at TEXT, PRIMARY KEY(comment_id,user_id))')
            c.execute('CREATE INDEX IF NOT EXISTS tasks_deadline ON tasks(deadline)')
            c.execute('CREATE INDEX IF NOT EXISTS comments_task ON comments(task_id,id)')
            c.execute('PRAGMA user_version=2')
        if c.execute('PRAGMA user_version').fetchone()[0] < 3:
            for kind, table in [('task','tasks'),('format','formats')]:
                c.execute(f'CREATE TABLE {kind}_responsibles({kind}_id INTEGER NOT NULL REFERENCES {table}(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id), PRIMARY KEY({kind}_id,user_id))')
                c.execute(f'INSERT INTO {kind}_responsibles SELECT id,responsible_id FROM {table} WHERE responsible_id IS NOT NULL')
            c.execute('PRAGMA user_version=3')
        if c.execute('PRAGMA user_version').fetchone()[0] < 4:
            c.execute("UPDATE tasks SET status=CASE status WHEN 'Finalizado' THEN 'Criado' ELSE 'Postado' END,version=version+1 WHERE status IN ('Finalizado','Agendado')")
            c.execute('PRAGMA user_version=4')
        if c.execute('PRAGMA user_version').fetchone()[0] < 5:
            if 'whatsapp' not in {r['name'] for r in c.execute('PRAGMA table_info(users)')}:
                c.execute("ALTER TABLE users ADD COLUMN whatsapp TEXT NOT NULL DEFAULT ''")
            if 'overdue_episode' not in {r['name'] for r in c.execute('PRAGMA table_info(tasks)')}:
                c.execute('ALTER TABLE tasks ADD COLUMN overdue_episode INTEGER NOT NULL DEFAULT 0')
            c.execute("CREATE TABLE IF NOT EXISTS overdue_notifications(id INTEGER PRIMARY KEY,task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,episode INTEGER NOT NULL,state TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,next_attempt REAL NOT NULL DEFAULT 0,claimed_at REAL,delivered_at TEXT,error TEXT,message_id TEXT,UNIQUE(task_id,user_id,episode))")
            c.execute("CREATE TRIGGER IF NOT EXISTS overdue_insert AFTER INSERT ON tasks WHEN NEW.status='Atrasado' BEGIN UPDATE tasks SET overdue_episode=1 WHERE id=NEW.id; END")
            c.execute("CREATE TRIGGER IF NOT EXISTS overdue_transition AFTER UPDATE OF status ON tasks WHEN NEW.status='Atrasado' AND OLD.status!='Atrasado' BEGIN UPDATE tasks SET overdue_episode=overdue_episode+1 WHERE id=NEW.id; END")
            c.execute('PRAGMA user_version=5')
        if c.execute('PRAGMA user_version').fetchone()[0] < 6:
            if 'is_admin' not in {r['name'] for r in c.execute('PRAGMA table_info(users)')}:
                c.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0')
                c.execute('UPDATE users SET is_admin=1 WHERE email=?',(ADMIN,))
            c.execute("CREATE TABLE IF NOT EXISTS digest_runs(run_key TEXT PRIMARY KEY,day TEXT NOT NULL,kind TEXT NOT NULL,created_at TEXT NOT NULL)")
            c.execute("CREATE TABLE IF NOT EXISTS digest_messages(id INTEGER PRIMARY KEY,run_key TEXT NOT NULL REFERENCES digest_runs(run_key) ON DELETE CASCADE,part INTEGER NOT NULL,recipient TEXT NOT NULL,body TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,next_attempt REAL NOT NULL DEFAULT 0,claimed_at REAL,error TEXT,message_id TEXT,UNIQUE(run_key,part))")
            c.execute('PRAGMA user_version=6')
        if not c.execute('SELECT id FROM users WHERE is_admin=1').fetchone():
            pw = os.environ.get('INITIAL_PASSWORD')
            if not pw or len(pw) < 7:
                raise RuntimeError('Defina INITIAL_PASSWORD (mínimo 7 caracteres) para criar o administrador.')
            c.execute('INSERT INTO users(name,email,role,password,is_admin) VALUES(?,?,?,?,1)', ('Nícolas Louzada',ADMIN,'Administrador',generate_password_hash(pw)))

init()

def auth(admin=False):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            with db() as c:
                u = c.execute('SELECT * FROM users WHERE id=?', (session.get('uid'),)).fetchone()
            if not u: abort(401, 'Entre para continuar.')
            if u['must_change'] and request.path not in ['/api/me','/api/password','/api/logout']:
                abort(403, 'Troque a senha inicial para continuar.')
            if admin and not u['is_admin']: abort(403, 'Apenas o administrador pode gerenciar a equipe.')
            with db() as c:
                c.execute("UPDATE tasks SET status='Atrasado',version=version+1 WHERE deadline<? AND status NOT IN ('Criado','Postado','Atrasado')",(str(today()),))
            return fn(*args, **kwargs)
        return wrapped
    return decorator

@app.before_request
def guard():
    if request.method not in ('GET','HEAD','OPTIONS') and request.path.startswith('/api/'):
        if request.headers.get('X-ContentOS') != '1': abort(403, 'Origem inválida.')
        origin = request.headers.get('Origin')
        if origin and urlsplit(origin).netloc != request.host: abort(403, 'Origem inválida.')

@app.after_request
def headers(r):
    r.headers['X-Content-Type-Options']='nosniff'
    r.headers['X-Frame-Options']='DENY'
    r.headers['Referrer-Policy']='same-origin'
    r.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    if request.path.startswith('/api/'): r.headers['Cache-Control']='no-store'
    return r

@app.errorhandler(Exception)
def errors(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException): return jsonify(error=e.description), e.code
    if isinstance(e, (ValueError, TypeError, KeyError, sqlite3.IntegrityError)):
        return jsonify(error='Dados inválidos. Verifique os campos e vínculos.'), 400
    app.logger.exception('Erro inesperado')
    return jsonify(error='Falha interna. Tente novamente.'), 500

def text(d, key, limit=200, required=True):
    value = str(d.get(key,'')).strip()
    if (required and not value) or len(value)>limit: abort(400, f'Confira o campo {key}.')
    return value

def iso(v):
    return date.fromisoformat(str(v)).isoformat()

def color(v):
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', str(v)): abort(400,'Cor inválida.')
    return v

def frequency(value):
    if not isinstance(value, dict): abort(400, 'Frequência inválida.')
    out={}
    for k,v in value.items():
        if str(k) not in list('0123456') or type(v) is not int or not 0<=v<=30: abort(400,'Use de 0 a 30 entregas por dia.')
        if v: out[str(k)]=v
    return out

def ref(c, table, value, required=False):
    if value in (None,''):
        if required: abort(400,'Selecione um vínculo obrigatório.')
        return None
    value=int(value)
    if not c.execute(f'SELECT id FROM {table} WHERE id=?',(value,)).fetchone(): abort(400,'Vínculo inexistente.')
    return value

def public_user(u):
    result={k:u[k] for k in ('id','name','email','role','must_change','is_admin')}
    if has_request_context() and session.get('uid'):
        with db() as c:
            admin=c.execute('SELECT is_admin FROM users WHERE id=?',(session['uid'],)).fetchone()
        if admin and admin['is_admin']: result['whatsapp']=u['whatsapp']
    return result

@app.get('/')
def index(): return send_file(ROOT/'static/index.html')

@app.get('/healthz')
def health():
    with db() as c: c.execute('SELECT 1').fetchone()
    return {'ok':True}

@app.post('/api/login')
def login():
    d=request.get_json(); email=str(d.get('email','')).lower().strip()
    key=hashlib.sha256(email.encode()).hexdigest(); now=time.time()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        attempt=c.execute('SELECT * FROM login_attempts WHERE key=?',(key,)).fetchone()
        if attempt and attempt['reset_at']>now and attempt['count']>=10: abort(429,'Muitas tentativas. Aguarde 15 minutos.')
        u=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
        valid=u and check_password_hash(u['password'],str(d.get('password','')))
        if not valid:
            count=attempt['count']+1 if attempt and attempt['reset_at']>now else 1
            reset=attempt['reset_at'] if attempt and attempt['reset_at']>now else now+900
            c.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)',(key,count,reset))
        else: c.execute('DELETE FROM login_attempts WHERE key=?',(key,))
    if not valid: abort(401,'E-mail ou senha incorretos.')
    session.clear(); session['uid']=u['id']; session.permanent=True
    return public_user(u)

@app.get('/api/me')
@auth()
def me():
    with db() as c: return public_user(c.execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone())

@app.post('/api/logout')
def logout(): session.clear(); return {'ok':True}

@app.post('/api/password')
@auth()
def password():
    d=request.get_json(); pw=text(d,'password',200)
    if len(pw)<10: abort(400,'Escolha uma senha de pelo menos 10 caracteres.')
    with db() as c:
        u=c.execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone()
        if not check_password_hash(u['password'],str(d.get('current',''))): abort(400,'Senha atual incorreta.')
        if check_password_hash(u['password'],pw): abort(400,'Escolha uma senha diferente da inicial.')
        c.execute('UPDATE users SET password=?, must_change=0 WHERE id=?',(generate_password_hash(pw),u['id']))
    session.clear(); session['uid']=u['id']; session.permanent=True
    return {'ok':True}

@app.post('/api/users')
@auth(admin=True)
def users():
    d=request.get_json(); email=text(d,'email').lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): abort(400,'E-mail inválido.')
    pw=os.environ.get('INITIAL_PASSWORD')
    if not pw: abort(503,'Configure INITIAL_PASSWORD na hospedagem.')
    with db() as c:
        if c.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone(): abort(409,'Este e-mail já está na equipe.')
        c.execute('INSERT INTO users(name,email,role,password,whatsapp) VALUES(?,?,?,?,?)',(text(d,'name'),email,text(d,'role'),generate_password_hash(pw),phone(d.get('whatsapp',''))))
    return {'ok':True},201

def phone(value):
    if not isinstance(value,str): abort(400,'WhatsApp inválido.')
    number=re.sub(r'[ +().-]','',value)
    if number and not re.fullmatch(r'[1-9][0-9]{9,14}',number): abort(400,'Use o número com código do país e DDD, por exemplo 5511999999999.')
    return number


@app.patch('/api/users/<int:id>/whatsapp')
@auth(admin=True)
def update_whatsapp(id):
    number=phone(request.get_json().get('whatsapp',''))
    with db() as c:
        if not c.execute('UPDATE users SET whatsapp=? WHERE id=?',(number,id)).rowcount: abort(404)
    return {'ok':True}


@app.patch('/api/users/<int:id>')
@auth(admin=True)
def update_member(id):
    d=request.get_json();name=text(d,'name');email=text(d,'email').lower();role=text(d,'role');number=phone(d.get('whatsapp',''))
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): abort(400,'E-mail inválido.')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT id FROM users WHERE id=?',(id,)).fetchone(): abort(404)
        if c.execute('SELECT id FROM users WHERE email=? AND id!=?',(email,id)).fetchone(): abort(409,'Este e-mail já está na equipe.')
        c.execute('UPDATE users SET name=?,email=?,role=?,whatsapp=? WHERE id=?',(name,email,role,number,id))
    return {'ok':True}


@app.post('/api/integrations/whatsapp/daily')
@auth(admin=True)
def dispatch_daily():
    from notifications import configuration,queue_daily
    config=configuration()
    if not config['enabled'] or not config['ready']: abort(503,'Ative e configure a integração antes de enviar.')
    token=request.get_json().get('request_id')
    if not isinstance(token,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{16,100}',token): abort(400,'Identificador de envio inválido.')
    return queue_daily(today(), 'manual:'+token, 'manual',config),202


@app.get('/api/integrations/whatsapp')
@auth(admin=True)
def whatsapp_status():
    from notifications import configuration
    config=configuration()
    with db() as c:
        counts={r['state']:r['n'] for r in c.execute('SELECT state,count(*) AS n FROM overdue_notifications GROUP BY state')}
        group_counts={r['state']:r['n'] for r in c.execute('SELECT state,count(*) AS n FROM digest_messages GROUP BY state')}
    return {'enabled':config['enabled'],'configured':config['ready'],'instance':config['instance'],'counts':counts,'group_counts':group_counts}


@app.post('/api/channels')
@auth()
def channels():
    d=request.get_json(); url=text(d,'url',2000)
    if urlsplit(url).scheme not in ('http','https') or not urlsplit(url).hostname: abort(400,'Informe um link http ou https.')
    with db() as c: c.execute('INSERT INTO channels(name,url,color) VALUES(?,?,?)',(text(d,'name'),url,color(d['color'])))
    return {'ok':True},201

@app.patch('/api/channels/<int:id>')
@auth()
def update_channel(id):
    d=request.get_json(); url=text(d,'url',2000)
    if urlsplit(url).scheme not in ('http','https') or not urlsplit(url).hostname: abort(400,'Informe um link http ou https.')
    name=text(d,'name'); shade=color(d['color'])
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('UPDATE channels SET name=?,url=?,color=? WHERE id=? AND deleted=0',(name,url,shade,id)).rowcount: abort(404,'Canal não encontrado.')
        c.execute('UPDATE formats SET color=? WHERE channel_id=?',(shade,id))
    return {'ok':True}


@app.delete('/api/channels/<int:id>')
@auth()
def delete_channel(id):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('UPDATE channels SET deleted=1 WHERE id=? AND deleted=0',(id,)).rowcount: abort(404,'Canal não encontrado.')
        affected=[r[0] for r in c.execute('SELECT format_id FROM format_channels WHERE channel_id=?',(id,))]
        c.execute('DELETE FROM format_channels WHERE channel_id=?',(id,))
        paused=0
        for fid in affected:
            remaining=linked_channels(c,'format',fid)
            if remaining:
                shade=c.execute('SELECT color FROM channels WHERE id=?',(remaining[0],)).fetchone()[0]
                c.execute('UPDATE formats SET channel_id=?,color=? WHERE id=?',(remaining[0],shade,fid))
            else:
                c.execute('UPDATE formats SET active=0 WHERE id=?',(fid,));paused+=1
        # Historical task links remain valid, but the channel cannot be selected for new work.
    return {'ok':True,'paused_formats':paused}


def channel_ids(c, d, required=False, allowed_deleted=()):
    values = d.get('channel_ids') if 'channel_ids' in d else ([d['channel_id']] if d.get('channel_id') else [])
    if not isinstance(values, list) or len(values) > 50: abort(400, 'Selecione até 50 canais.')
    ids = sorted({ref(c, 'channels', v, True) for v in values})
    for id in ids:
        if c.execute('SELECT deleted FROM channels WHERE id=?',(id,)).fetchone()[0] and id not in allowed_deleted:
            abort(400,'Um dos canais foi excluído. Atualize a tela e escolha outro canal.')
    if required and not ids: abort(400, 'Selecione pelo menos um canal.')
    return ids


def linked_channels(c, kind, id):
    return [r[0] for r in c.execute(f'SELECT channel_id FROM {kind}_channels WHERE {kind}_id=? ORDER BY channel_id', (id,))]


def set_channels(c, kind, id, ids):
    c.execute(f'DELETE FROM {kind}_channels WHERE {kind}_id=?', (id,))
    c.executemany(f'INSERT INTO {kind}_channels({kind}_id,channel_id) VALUES(?,?)', [(id, ch) for ch in ids])


def responsible_ids(c,d,required=False):
    values=d.get('responsible_ids') if 'responsible_ids' in d else ([int(d['responsible_id'])] if d.get('responsible_id') else [])
    if not isinstance(values,list) or len(values)>100 or any(type(v) is not int or v<=0 for v in values): abort(400,'Selecione até 100 responsáveis.')
    ids=sorted({ref(c,'users',v,True) for v in values})
    if required and not ids: abort(400,'Selecione pelo menos um responsável.')
    return ids


def linked_responsibles(c,kind,id):
    return [r[0] for r in c.execute(f'SELECT user_id FROM {kind}_responsibles WHERE {kind}_id=? ORDER BY user_id',(id,))]


def set_responsibles(c,kind,id,ids):
    c.execute(f'DELETE FROM {kind}_responsibles WHERE {kind}_id=?',(id,))
    c.executemany(f'INSERT INTO {kind}_responsibles VALUES(?,?)',[(id,uid) for uid in ids])


def now():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(timespec='seconds')


@app.post('/api/formats')
@auth()
def formats():
    d=request.get_json(); freq=frequency(d['frequency'])
    if not freq: abort(400,'Escolha pelo menos um dia e quantidade.')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        ids=channel_ids(c,d,True)
        people=responsible_ids(c,d,True)
        inherited=c.execute('SELECT color FROM channels WHERE id=?',(ids[0],)).fetchone()[0]
        cur=c.execute('INSERT INTO formats(name,channel_id,responsible_id,color,frequency,active_from) VALUES(?,?,?,?,?,?)',
            (text(d,'name'),ids[0],people[0],inherited,json.dumps(freq),iso(d['active_from'])))
        set_channels(c,'format',cur.lastrowid,ids)
        set_responsibles(c,'format',cur.lastrowid,people)
    return {'ok':True},201


@app.patch('/api/formats/<int:id>')
@auth()
def update_format(id):
    d=request.get_json()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM formats WHERE id=?',(id,)).fetchone()
        if not old: abort(404)
        if set(d)=={'active'}:
            if type(d['active']) is not bool: abort(400,'Estado inválido.')
            if d['active'] and not linked_channels(c,'format',id): abort(400,'Edite o formato e selecione um canal antes de retomar.')
            c.execute('UPDATE formats SET active=? WHERE id=?',(int(d['active']),id))
        else:
            ids=channel_ids(c,d,True); freq=frequency(d['frequency']); people=responsible_ids(c,d,True)
            if not freq: abort(400,'Escolha pelo menos um dia.')
            inherited=c.execute('SELECT color FROM channels WHERE id=?',(ids[0],)).fetchone()[0]
            old_channels=linked_channels(c,'format',id); old_people=linked_responsibles(c,'format',id)
            c.execute('UPDATE formats SET name=?,channel_id=?,responsible_id=?,color=?,frequency=?,active_from=? WHERE id=?',
                (text(d,'name'),ids[0],people[0],inherited,json.dumps(freq),iso(d['active_from']),id))
            set_channels(c,'format',id,ids)
            set_responsibles(c,'format',id,people)
            # Propagate only changed shared fields, preserving task-specific work and deadlines.
            for task in c.execute('SELECT * FROM tasks WHERE format_id=?',(id,)).fetchall():
                updates={}
                if old_people!=people:
                    updates['responsible_id']=people[0]
                    set_responsibles(c,'task',task['id'],people)
                if old_channels!=ids:
                    updates['channel_id']=ids[0]
                    set_channels(c,'task',task['id'],ids)
                if json.loads(old['frequency'])!=freq: updates['frequency']=json.dumps(freq)
                if old['name']!=text(d,'name'):
                    # Keep custom briefs/titles; rename titles inherited from this format.
                    suffix=task['title'][len(old['name']):] if task['title'].startswith(old['name']) else None
                    if suffix=='' or (suffix is not None and re.fullmatch(r' · \d+',suffix)):
                        updates['title']=text(d,'name')+suffix
                if updates:
                    assignments=','.join(key+'=?' for key in updates)
                    c.execute(f'UPDATE tasks SET {assignments},version=version+1 WHERE id=?',(*updates.values(),task['id']))
    return {'ok':True}


@app.delete('/api/formats/<int:id>')
@auth()
def delete_format(id):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT id FROM formats WHERE id=?',(id,)).fetchone(): abort(404,'Formato não encontrado.')
        # Slots contain format IDs. Clear them so a future reused ID cannot collide.
        changed=c.execute('UPDATE tasks SET format_id=NULL,slot=NULL,version=version+1 WHERE format_id=?',(id,)).rowcount
        c.execute('DELETE FROM formats WHERE id=?',(id,))
    return {'ok':True,'preserved_tasks':changed}


def generate(c,start,end):
    for f in c.execute('SELECT * FROM formats WHERE active=1').fetchall():
        freq=json.loads(f['frequency']); day=max(start,date.fromisoformat(f['active_from']))
        ids=linked_channels(c,'format',f['id'])
        if not ids: continue
        suppressed={r[0] for r in c.execute('SELECT slot FROM suppressed_slots WHERE format_id=?',(f['id'],))}
        while day<=end:
            for n in range(freq.get(str(day.weekday()),0)):
                slot=f"{f['id']}:{day}:{n}"
                if slot in suppressed or c.execute('SELECT id FROM tasks WHERE slot=?',(slot,)).fetchone(): continue
                task_id=c.execute('INSERT INTO task_id_sequence DEFAULT VALUES').lastrowid
                cur=c.execute('INSERT OR IGNORE INTO tasks(id,title,deadline,responsible_id,channel_id,format_id,status,frequency,slot) VALUES(?,?,?,?,?,?,?,?,?)',
                    (task_id,f"{f['name']} · {n+1}",str(day),f['responsible_id'],ids[0] if ids else None,f['id'],'Atrasado' if day<today() else 'Pendente',f['frequency'],slot))
                if cur.rowcount:
                    set_channels(c,'task',cur.lastrowid,ids)
                    set_responsibles(c,'task',cur.lastrowid,linked_responsibles(c,'format',f['id']))
            day+=timedelta(days=1)


def date_range():
    start=date.fromisoformat(request.args.get('start',str(today())))
    end=date.fromisoformat(request.args.get('end',str(start+timedelta(days=6))))
    if not 0<=(end-start).days<=92: abort(400,'Escolha um intervalo de até 93 dias.')
    if start<today()-timedelta(days=730) or end>today()+timedelta(days=730): abort(400,'Escolha um período dentro de dois anos.')
    return start,end


def enrich_tasks(c, tasks):
    if not tasks: return tasks
    ids={t['id'] for t in tasks}
    links={}; attachments={}; people={}
    for r in c.execute('SELECT task_id,user_id FROM task_responsibles ORDER BY user_id'):
        if r['task_id'] in ids: people.setdefault(r['task_id'],[]).append(r['user_id'])
    for r in c.execute('SELECT task_id,channel_id FROM task_channels ORDER BY channel_id'):
        if r['task_id'] in ids: links.setdefault(r['task_id'],[]).append(r['channel_id'])
    for r in c.execute('SELECT id,task_id,name FROM attachments'):
        if r['task_id'] in ids: attachments.setdefault(r['task_id'],[]).append(dict(r))
    for t in tasks:
        t['channel_ids']=links.get(t['id'],[])
        t['responsible_ids']=people.get(t['id'],[])
        t['attachments']=attachments.get(t['id'],[])
        t['archived']=t['status']=='Postado'
        t['overdue']=t['deadline']<str(today()) and t['status'] not in DONE
    return tasks


def period_tasks(c,start,end):
    if not c.in_transaction: c.execute('BEGIN IMMEDIATE')
    generate(c,start,end)
    return enrich_tasks(c,[dict(r) for r in c.execute('SELECT * FROM tasks WHERE deadline BETWEEN ? AND ? ORDER BY deadline,id',(str(start),str(end)))])


@app.get('/api/state')
@auth()
def state():
    start,end=date_range()
    with db() as c:
        tasks=period_tasks(c,start,end)
        formats=[{**dict(f),'channel_ids':linked_channels(c,'format',f['id']),'responsible_ids':linked_responsibles(c,'format',f['id'])} for f in c.execute('SELECT * FROM formats ORDER BY name')]
        mentions=[dict(r) for r in c.execute('SELECT m.comment_id,c.task_id,c.created_at,t.title,u.name AS author FROM comment_mentions m JOIN comments c ON c.id=m.comment_id JOIN tasks t ON t.id=c.task_id JOIN users u ON u.id=c.author_id WHERE m.user_id=? AND m.read_at IS NULL ORDER BY c.id DESC',(session['uid'],))]
        return {'tasks':tasks,'users':[public_user(u) for u in c.execute('SELECT * FROM users ORDER BY name')],
            'channels':[dict(r) for r in c.execute('SELECT * FROM channels ORDER BY name')],
            'formats':formats,'mentions':mentions,'today':str(today())}


@app.get('/api/tasks/<int:id>')
@auth()
def get_task(id):
    with db() as c:
        row=c.execute('SELECT * FROM tasks WHERE id=?',(id,)).fetchone()
        if not row: abort(404)
        return enrich_tasks(c,[dict(row)])[0]


@app.get('/api/tasks/<int:id>/comments')
@auth()
def get_comments(id):
    with db() as c:
        if not c.execute('SELECT id FROM tasks WHERE id=?',(id,)).fetchone(): abort(404)
        comments=[dict(r) for r in c.execute('SELECT c.*,u.name AS author FROM comments c JOIN users u ON u.id=c.author_id WHERE task_id=? ORDER BY c.id',(id,))]
        for comment in comments:
            comment['mentions']=[dict(r) for r in c.execute('SELECT u.id,u.name FROM comment_mentions m JOIN users u ON u.id=m.user_id WHERE m.comment_id=?',(comment['id'],))]
        return {'comments':comments}


@app.get('/api/mentions')
@auth()
def mentions_inbox():
    with db() as c:
        rows=[dict(r) for r in c.execute('SELECT m.comment_id,c.task_id,c.created_at,t.title,u.name AS author FROM comment_mentions m JOIN comments c ON c.id=m.comment_id JOIN tasks t ON t.id=c.task_id JOIN users u ON u.id=c.author_id WHERE m.user_id=? AND m.read_at IS NULL ORDER BY c.id DESC',(session['uid'],))]
    return {'mentions':rows}


@app.post('/api/tasks/<int:id>/comments')
@auth()
def add_comment(id):
    d=request.get_json(); body=text(d,'body',5000)
    values=d.get('mentions',[])
    if not isinstance(values,list) or len(values)>50: abort(400,'Menções inválidas.')
    with db() as c:
        if not c.execute('SELECT id FROM tasks WHERE id=?',(id,)).fetchone(): abort(404)
        ids=sorted({ref(c,'users',v,True) for v in values})
        for uid in ids:
            name=c.execute('SELECT name FROM users WHERE id=?',(uid,)).fetchone()[0]
            if '@'+name not in body: abort(400,'Selecione a pessoa mencionada no comentário.')
        # Recognize full typed names as well as selections; ambiguous names require a selection.
        people=c.execute('SELECT id,name FROM users').fetchall()
        for person in people:
            if sum(p['name'].casefold()==person['name'].casefold() for p in people)==1 and re.search(r'(?<!\w)@'+re.escape(person['name'])+r'(?!\w)',body,re.IGNORECASE):
                ids.append(person['id'])
        ids=sorted(set(ids))
        if len(ids)>50: abort(400,'Use até 50 menções por comentário.')
        cur=c.execute('INSERT INTO comments(task_id,author_id,body,created_at) VALUES(?,?,?,?)',(id,session['uid'],body,now()))
        c.executemany('INSERT INTO comment_mentions(comment_id,user_id,read_at) VALUES(?,?,?)',[(cur.lastrowid,uid,None) for uid in ids])
    return {'ok':True},201


@app.post('/api/tasks/<int:id>/mentions/read')
@auth()
def read_mentions(id):
    with db() as c:
        c.execute('UPDATE comment_mentions SET read_at=? WHERE user_id=? AND comment_id IN (SELECT id FROM comments WHERE task_id=?)',(now(),session['uid'],id))
    return {'ok':True}


def report_data():
    from reports import summarize
    start,end=date_range()
    with db() as c:
        tasks=period_tasks(c,start,end)
        users=[public_user(u) for u in c.execute('SELECT * FROM users ORDER BY name')]
        channels=[dict(ch) for ch in c.execute('SELECT * FROM channels ORDER BY name')]
    return summarize(tasks,users,channels,start,end),tasks,users,channels


@app.get('/api/insights')
@auth()
def insights():
    report,tasks,users,channels=report_data()
    return {'report':report,'tasks':tasks}


@app.get('/api/insights.pdf')
@auth()
def insights_pdf():
    from reports import make_pdf
    report,tasks,users,channels=report_data()
    pdf=make_pdf(report,tasks,users,channels,now())
    return send_file(pdf,mimetype='application/pdf',as_attachment=True,
        download_name=f"contentos-{report['start']}-{report['end']}.pdf")


@app.post('/api/tasks')
@auth()
def create_task():
    d=request.get_json(); count=int(d.get('quantity',1)); freq=frequency(d.get('frequency',{}))
    if not 1<=count<=100: abort(400,'Use uma quantidade entre 1 e 100.')
    request_id=d.get('request_id')
    if request_id is not None and (not isinstance(request_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{16,100}',request_id)):
        abort(400,'Identificador da solicitação inválido.')
    payload_hash=hashlib.sha256(json.dumps({k:v for k,v in d.items() if k!='request_id'},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if request_id:
            previous=c.execute('SELECT * FROM task_requests WHERE user_id=? AND request_id=?',(session['uid'],request_id)).fetchone()
            if previous:
                if previous['payload_hash']!=payload_hash: abort(409,'Esta solicitação já foi salva. Feche o formulário e confira as tarefas antes de criar outra.')
                previous_ids=json.loads(previous['task_ids'])
                if any(not c.execute('SELECT id FROM tasks WHERE id=?',(tid,)).fetchone() for tid in previous_ids): abort(410,'As tarefas desta solicitação foram excluídas. Abra um novo formulário se quiser criar outras.')
                return {'ids':previous_ids,'replayed':True},200
        ids_channels=channel_ids(c,d); fields=task_fields(c,d); batch=secrets.token_hex(12); day=date.fromisoformat(fields['deadline']); deadlines=[]
        if freq:
            while len(deadlines)<count:
                deadlines.extend([str(day)]*min(freq.get(str(day.weekday()),0),count-len(deadlines)))
                day+=timedelta(days=1)
        else: deadlines=[str(day)]*count
        ids=[]
        for i,deadline in enumerate(deadlines):
            f={**fields,'deadline':deadline,'status':('Atrasado' if deadline<str(today()) and d.get('status','Pendente') not in DONE else d.get('status','Pendente')),'title':fields['title']+(f' · {i+1}' if count>1 else '')}
            task_id=c.execute('INSERT INTO task_id_sequence DEFAULT VALUES').lastrowid
            cur=c.execute('INSERT INTO tasks(id,title,description,deadline,responsible_id,channel_id,format_id,status,frequency,batch) VALUES(:id,:title,:description,:deadline,:responsible_id,:channel_id,:format_id,:status,:frequency,:batch)',{**f,'id':task_id,'frequency':json.dumps(freq),'batch':batch})
            set_channels(c,'task',cur.lastrowid,ids_channels)
            set_responsibles(c,'task',cur.lastrowid,responsible_ids(c,d))
            if f['status'] in DONE: c.execute('UPDATE tasks SET completed_at=? WHERE id=?',(now(),cur.lastrowid))
            ids.append(cur.lastrowid)
        if request_id:
            c.execute('INSERT INTO task_requests VALUES(?,?,?,?)',(session['uid'],request_id,payload_hash,json.dumps(ids)))
    return {'ids':ids},201

def task_fields(c,d,allowed_deleted=()):
    status=d.get('status','Pendente')
    if status not in STATES: abort(400,'Status inválido.')
    ids=channel_ids(c,d,allowed_deleted=allowed_deleted); channel=ids[0] if ids else None; fmt=ref(c,'formats',d.get('format_id'))
    if iso(d['deadline'])<str(today()) and status not in DONE: status='Atrasado'
    return dict(title=text(d,'title'),description=text(d,'description',20000,False),deadline=iso(d['deadline']),
        responsible_id=next(iter(responsible_ids(c,d)),None),channel_id=channel,format_id=fmt,status=status)

@app.patch('/api/tasks/<int:id>')
@auth()
def update_task(id):
    d=request.get_json()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM tasks WHERE id=?',(id,)).fetchone()
        if not old: abort(404)
        if d.get('version')!=old['version']: abort(409,'Esta tarefa foi atualizada por outra pessoa. Feche e abra novamente para carregar a versão atual.')
        merged={**dict(old),'channel_ids':linked_channels(c,'task',id),'responsible_ids':linked_responsibles(c,'task',id),**d}
        if 'responsible_id' in d and 'responsible_ids' not in d: merged.pop('responsible_ids',None)
        if 'channel_id' in d and 'channel_ids' not in d: merged.pop('channel_ids',None)
        existing_channels=linked_channels(c,'task',id)
        ids_channels=channel_ids(c,merged,allowed_deleted=existing_channels)
        f=task_fields(c,merged,allowed_deleted=existing_channels); freq=frequency(d.get('frequency',json.loads(old['frequency'])))
        changed=c.execute('UPDATE tasks SET title=:title,description=:description,deadline=:deadline,responsible_id=:responsible_id,channel_id=:channel_id,format_id=:format_id,status=:status,frequency=:frequency,version=version+1 WHERE id=:id AND version=:version', {**f,'frequency':json.dumps(freq),'id':id,'version':old['version']}).rowcount
        if not changed: abort(409,'Esta tarefa foi atualizada por outra pessoa. Reabra a tarefa.')
        set_channels(c,'task',id,ids_channels)
        set_responsibles(c,'task',id,responsible_ids(c,merged))
        completed=(old['completed_at'] if old['status'] in DONE else now()) if f['status'] in DONE else None
        c.execute('UPDATE tasks SET completed_at=? WHERE id=?',(completed,id))
    return {'ok':True}

@app.post('/api/tasks/bulk-status')
@auth()
def bulk_status():
    d=request.get_json(); items=d.get('tasks');status=d.get('status')
    if status not in STATES: abort(400,'Status inválido.')
    if not isinstance(items,list) or not 1<=len(items)<=500: abort(400,'Selecione entre 1 e 500 tarefas.')
    if any(not isinstance(t,dict) or type(t.get('id')) is not int or t['id']<=0 or type(t.get('version')) is not int or t['version']<=0 for t in items):
        abort(400,'Seleção de tarefas inválida.')
    if len({t['id'] for t in items})!=len(items): abort(400,'Há tarefas repetidas na seleção.')
    adjusted=0;changed=0
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        rows=[]
        for item in items:
            row=c.execute('SELECT * FROM tasks WHERE id=?',(item['id'],)).fetchone()
            if not row or row['version']!=item['version']:
                abort(409,'Uma tarefa foi alterada ou excluída. Feche esta janela, atualize a lista e selecione novamente. Nenhuma alteração de status deste lote foi aplicada.')
            rows.append(row)
        timestamp=now()
        for row in rows:
            target='Atrasado' if row['deadline']<str(today()) and status not in DONE else status
            adjusted+=target!=status
            if row['status']==target: continue
            completed=(row['completed_at'] if row['status'] in DONE else timestamp) if target in DONE else None
            c.execute('UPDATE tasks SET status=?,completed_at=?,version=version+1 WHERE id=?',(target,completed,row['id']))
            changed+=1
    return {'ok':True,'updated':changed,'overdue':adjusted}


def remove_tasks(ids):
    if not isinstance(ids,list) or not ids or len(ids)>500 or any(type(id) is not int or id<=0 for id in ids):
        abort(400,'Selecione entre 1 e 500 tarefas válidas.')
    ids=sorted(set(ids));marks=','.join('?' for _ in ids)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        rows=c.execute(f'SELECT id,slot,format_id FROM tasks WHERE id IN ({marks})',ids).fetchall()
        if len(rows)!=len(ids): abort(409,'Uma das tarefas não existe mais. Atualize a lista antes de excluir.')
        for row in rows:
            if row['slot'] and row['format_id']:
                c.execute('INSERT OR IGNORE INTO suppressed_slots VALUES(?,?)',(row['slot'],row['format_id']))
        disks=[r[0] for r in c.execute(f'SELECT disk FROM attachments WHERE task_id IN ({marks})',ids)]
        c.execute(f'DELETE FROM attachments WHERE task_id IN ({marks})',ids)
        c.execute(f'DELETE FROM tasks WHERE id IN ({marks})',ids)
    for disk in disks:
        try: (DATA/'uploads'/disk).unlink(missing_ok=True)
        except OSError: app.logger.warning('Não foi possível remover um arquivo de anexo excluído.')
    return {'ok':True,'deleted':len(ids)}


@app.delete('/api/tasks/<int:id>')
@auth()
def delete_task(id):
    return remove_tasks([id])


@app.post('/api/tasks/bulk-delete')
@auth()
def bulk_delete_tasks():
    return remove_tasks(request.get_json().get('ids'))


@app.post('/api/tasks/<int:id>/attachments')
@auth()
def upload(id):
    f=request.files.get('file')
    if not f or not f.filename: abort(400,'Selecione um arquivo.')
    with db() as c:
        if not c.execute('SELECT id FROM tasks WHERE id=?',(id,)).fetchone(): abort(404)
        folder=DATA/'uploads'; folder.mkdir(exist_ok=True); disk=secrets.token_hex(20)
        f.save(folder/disk)
        try: c.execute('INSERT INTO attachments(task_id,name,disk) VALUES(?,?,?)',(id,secure_filename(f.filename) or 'anexo',disk))
        except Exception:
            (folder/disk).unlink(missing_ok=True)
            raise
    return {'ok':True},201

@app.get('/api/attachments/<int:id>')
@auth()
def download(id):
    with db() as c: a=c.execute('SELECT * FROM attachments WHERE id=?',(id,)).fetchone()
    if not a: abort(404)
    return send_file(DATA/'uploads'/a['disk'],as_attachment=True,download_name=a['name'],mimetype='application/octet-stream')

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT','8000')))
