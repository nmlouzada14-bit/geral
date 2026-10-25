import os, sqlite3, secrets, json, re, hashlib, time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from functools import wraps
from urllib.parse import urlsplit
from flask import Flask, request, jsonify, session, send_file, abort
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
STATES = ['Pendente', 'Em andamento', 'Revisão', 'Finalizado', 'Agendado', 'Postado', 'Atrasado']

def db():
    c = sqlite3.connect(DATA / 'contentos.sqlite', timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def today():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).date()

def init():
    with db() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, role TEXT NOT NULL, password TEXT NOT NULL, must_change INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS channels(id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL, color TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS formats(id INTEGER PRIMARY KEY, name TEXT NOT NULL, channel_id INTEGER NOT NULL REFERENCES channels(id), responsible_id INTEGER REFERENCES users(id), color TEXT NOT NULL, frequency TEXT NOT NULL, active_from TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', deadline TEXT NOT NULL, responsible_id INTEGER REFERENCES users(id), channel_id INTEGER REFERENCES channels(id), format_id INTEGER REFERENCES formats(id), status TEXT NOT NULL, frequency TEXT NOT NULL DEFAULT '{}', batch TEXT, slot TEXT UNIQUE, version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS attachments(id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id), name TEXT NOT NULL, disk TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS login_attempts(key TEXT PRIMARY KEY, count INTEGER NOT NULL, reset_at REAL NOT NULL);
        ''')
        if not c.execute('SELECT id FROM users WHERE email=?', (ADMIN,)).fetchone():
            pw = os.environ.get('INITIAL_PASSWORD')
            if not pw or len(pw) < 7:
                raise RuntimeError('Defina INITIAL_PASSWORD (mínimo 7 caracteres) para criar o administrador.')
            c.execute('INSERT INTO users(name,email,role,password) VALUES(?,?,?,?)', ('Nícolas Louzada',ADMIN,'Administrador',generate_password_hash(pw)))

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
            if admin and u['email'] != ADMIN: abort(403, 'Apenas o administrador pode gerenciar a equipe.')
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
    return {k:u[k] for k in ('id','name','email','role','must_change')}

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
        c.execute('INSERT INTO users(name,email,role,password) VALUES(?,?,?,?)',(text(d,'name'),email,text(d,'role'),generate_password_hash(pw)))
    return {'ok':True},201

@app.post('/api/channels')
@auth()
def channels():
    d=request.get_json(); url=text(d,'url',2000)
    if urlsplit(url).scheme not in ('http','https') or not urlsplit(url).hostname: abort(400,'Informe um link http ou https.')
    with db() as c: c.execute('INSERT INTO channels(name,url,color) VALUES(?,?,?)',(text(d,'name'),url,color(d['color'])))
    return {'ok':True},201

@app.route('/api/formats', methods=['POST'])
@auth()
def formats():
    d=request.get_json(); freq=frequency(d['frequency'])
    if not freq: abort(400,'Escolha pelo menos um dia e quantidade.')
    with db() as c:
        c.execute('INSERT INTO formats(name,channel_id,responsible_id,color,frequency,active_from) VALUES(?,?,?,?,?,?)',
            (text(d,'name'),ref(c,'channels',d.get('channel_id'),True),ref(c,'users',d.get('responsible_id'),True),color(d['color']),json.dumps(freq),iso(d['active_from'])))
    return {'ok':True},201

@app.patch('/api/formats/<int:id>')
@auth()
def pause(id):
    d=request.get_json()
    if type(d.get('active')) is not bool: abort(400,'Estado inválido.')
    with db() as c:
        if not c.execute('UPDATE formats SET active=? WHERE id=?',(int(d['active']),id)).rowcount: abort(404)
    return {'ok':True}

def generate(c,start,end):
    for f in c.execute('SELECT * FROM formats WHERE active=1').fetchall():
        freq=json.loads(f['frequency']); day=max(start,date.fromisoformat(f['active_from']))
        while day<=end:
            for n in range(freq.get(str(day.weekday()),0)):
                slot=f"{f['id']}:{day}:{n}"
                c.execute('INSERT OR IGNORE INTO tasks(title,deadline,responsible_id,channel_id,format_id,status,frequency,slot) VALUES(?,?,?,?,?,?,?,?)',
                    (f"{f['name']} · {n+1}",str(day),f['responsible_id'],f['channel_id'],f['id'],'Pendente',f['frequency'],slot))
            day+=timedelta(days=1)

@app.get('/api/state')
@auth()
def state():
    start=date.fromisoformat(request.args.get('start',str(today())))
    end=date.fromisoformat(request.args.get('end',str(start+timedelta(days=6))))
    if not 0<=(end-start).days<=92: abort(400,'Escolha um intervalo de até 93 dias.')
    if start<today()-timedelta(days=730) or end>today()+timedelta(days=730): abort(400,'Escolha um período dentro de dois anos.')
    with db() as c:
        generate(c,start,end)
        tasks=[dict(r) for r in c.execute('SELECT * FROM tasks WHERE deadline BETWEEN ? AND ? ORDER BY deadline,id',(str(start),str(end)))]
        attachments={}
        for a in c.execute('SELECT a.id,a.task_id,a.name FROM attachments a JOIN tasks t ON t.id=a.task_id WHERE t.deadline BETWEEN ? AND ?',(str(start),str(end))):
            attachments.setdefault(a['task_id'],[]).append(dict(a))
        for t in tasks:
            t['attachments']=attachments.get(t['id'],[])
            t['overdue']=t['deadline']<str(today()) and t['status'] not in ('Postado','Agendado')
        return {'tasks':tasks,'users':[public_user(u) for u in c.execute('SELECT * FROM users ORDER BY name')],
            'channels':[dict(r) for r in c.execute('SELECT * FROM channels ORDER BY name')],
            'formats':[dict(r) for r in c.execute('SELECT * FROM formats ORDER BY name')], 'today':str(today())}

@app.post('/api/tasks')
@auth()
def create_task():
    d=request.get_json(); count=int(d.get('quantity',1)); freq=frequency(d.get('frequency',{}))
    if not 1<=count<=100: abort(400,'Use uma quantidade entre 1 e 100.')
    with db() as c:
        fields=task_fields(c,d); batch=secrets.token_hex(12); day=date.fromisoformat(fields['deadline']); deadlines=[]
        if freq:
            while len(deadlines)<count:
                deadlines.extend([str(day)]*min(freq.get(str(day.weekday()),0),count-len(deadlines)))
                day+=timedelta(days=1)
        else: deadlines=[str(day)]*count
        ids=[]
        for i,deadline in enumerate(deadlines):
            f={**fields,'deadline':deadline,'title':fields['title']+(f' · {i+1}' if count>1 else '')}
            cur=c.execute('INSERT INTO tasks(title,description,deadline,responsible_id,channel_id,format_id,status,frequency,batch) VALUES(:title,:description,:deadline,:responsible_id,:channel_id,:format_id,:status,:frequency,:batch)',{**f,'frequency':json.dumps(freq),'batch':batch})
            ids.append(cur.lastrowid)
    return {'ids':ids},201

def task_fields(c,d):
    status=d.get('status','Pendente')
    if status not in STATES: abort(400,'Status inválido.')
    channel=ref(c,'channels',d.get('channel_id')); fmt=ref(c,'formats',d.get('format_id'))
    if fmt:
        expected=c.execute('SELECT channel_id FROM formats WHERE id=?',(fmt,)).fetchone()[0]
        if channel!=expected: abort(400,'O formato deve pertencer ao canal selecionado.')
    return dict(title=text(d,'title'),description=text(d,'description',20000,False),deadline=iso(d['deadline']),
        responsible_id=ref(c,'users',d.get('responsible_id')),channel_id=channel,format_id=fmt,status=status)

@app.patch('/api/tasks/<int:id>')
@auth()
def update_task(id):
    d=request.get_json()
    with db() as c:
        old=c.execute('SELECT * FROM tasks WHERE id=?',(id,)).fetchone()
        if not old: abort(404)
        if d.get('version')!=old['version']: abort(409,'Esta tarefa foi atualizada por outra pessoa. Feche e abra novamente para carregar a versão atual.')
        f=task_fields(c,{**dict(old),**d}); freq=frequency(d.get('frequency',json.loads(old['frequency'])))
        changed=c.execute('UPDATE tasks SET title=:title,description=:description,deadline=:deadline,responsible_id=:responsible_id,channel_id=:channel_id,format_id=:format_id,status=:status,frequency=:frequency,version=version+1 WHERE id=:id AND version=:version', {**f,'frequency':json.dumps(freq),'id':id,'version':old['version']}).rowcount
        if not changed: abort(409,'Esta tarefa foi atualizada por outra pessoa. Reabra a tarefa.')
    return {'ok':True}

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
