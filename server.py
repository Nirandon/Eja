"""Cash Me Crying: local-only finance application, Python standard library."""
import json, os, re, sqlite3, urllib.request, urllib.error, html, base64, binascii
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).parent
DB = Path(os.environ.get('CMC_DATABASE', ROOT / 'data' / 'cash.db'))
CATEGORIES = ['Food','Drinks','Shopping','Transportation','Entertainment','Bills','Education','Health','Other']
def today(): return datetime.now(ZoneInfo('Asia/Bangkok')).date()
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c
def init():
    with connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS workspaces(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL)')
        c.execute("INSERT OR IGNORE INTO workspaces(id,name) VALUES(1,'Personal')")
        old=c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'").fetchone()
        migrate=bool(old and 'workspace_id' not in {r[1] for r in c.execute('PRAGMA table_info(accounts)')})
        if migrate:
            c.execute('ALTER TABLE transactions RENAME TO transactions_legacy')
            c.execute('ALTER TABLE accounts RENAME TO accounts_legacy')
        c.execute('CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY,name TEXT NOT NULL,opening INTEGER NOT NULL DEFAULT 0,workspace_id INTEGER NOT NULL REFERENCES workspaces(id),UNIQUE(workspace_id,name))')
        c.execute('CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY,date TEXT NOT NULL,description TEXT NOT NULL,amount INTEGER NOT NULL CHECK(amount>0),category TEXT NOT NULL,type TEXT NOT NULL,account_id INTEGER NOT NULL REFERENCES accounts(id),destination_id INTEGER REFERENCES accounts(id),workspace_id INTEGER NOT NULL REFERENCES workspaces(id))')
        if migrate:
            c.execute('INSERT INTO accounts(id,name,opening,workspace_id) SELECT id,name,opening,1 FROM accounts_legacy')
            c.execute('INSERT INTO transactions(id,date,description,amount,category,type,account_id,destination_id,workspace_id) SELECT id,date,description,amount,category,type,account_id,destination_id,1 FROM transactions_legacy')
        if 'theme' not in {r[1] for r in c.execute('PRAGMA table_info(workspaces)')}:
            c.execute("ALTER TABLE workspaces ADD COLUMN theme TEXT NOT NULL DEFAULT '#287867'")
        c.execute('CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY,workspace_id INTEGER NOT NULL REFERENCES workspaces(id),name TEXT NOT NULL,UNIQUE(workspace_id,name))')
        c.execute("CREATE TABLE IF NOT EXISTS plans(workspace_id INTEGER NOT NULL REFERENCES workspaces(id),month TEXT NOT NULL,total INTEGER,notes TEXT NOT NULL DEFAULT '',details TEXT NOT NULL DEFAULT '{}',PRIMARY KEY(workspace_id,month))")
        c.execute('CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY,workspace_id INTEGER NOT NULL REFERENCES workspaces(id),text TEXT NOT NULL,due TEXT,done INTEGER NOT NULL DEFAULT 0)')
        if 'cover_image' not in {r[1] for r in c.execute('PRAGMA table_info(workspaces)')}:
            c.execute('ALTER TABLE workspaces ADD COLUMN cover_image TEXT')
        if 'palette_version' not in {r[1] for r in c.execute('PRAGMA table_info(workspaces)')}:
            c.execute('ALTER TABLE workspaces ADD COLUMN palette_version INTEGER NOT NULL DEFAULT 1')
            c.execute("UPDATE workspaces SET theme='#575d41' WHERE lower(theme)='#287867'")
        if 'default_account_id' not in {r[1] for r in c.execute('PRAGMA table_info(workspaces)')}:
            c.execute('ALTER TABLE workspaces ADD COLUMN default_account_id INTEGER')
        if 'keywords' not in {r[1] for r in c.execute('PRAGMA table_info(categories)')}:
            c.execute("ALTER TABLE categories ADD COLUMN keywords TEXT NOT NULL DEFAULT ''")
        c.execute('CREATE TABLE IF NOT EXISTS balance_adjustments(id INTEGER PRIMARY KEY,workspace_id INTEGER NOT NULL REFERENCES workspaces(id),account_id INTEGER NOT NULL REFERENCES accounts(id),date TEXT NOT NULL,observed INTEGER NOT NULL,delta INTEGER NOT NULL,reason TEXT NOT NULL)')
        for w in c.execute('SELECT id FROM workspaces').fetchall():
            seed_categories(c,w[0])
        if not c.execute('SELECT count(*) FROM accounts WHERE workspace_id=1').fetchone()[0]:
            c.executemany('INSERT INTO accounts(name,workspace_id) VALUES(?,1)', [('KBank',),('SCB',),('Cash',)])


def seed_categories(c,workspace):
    if not c.execute('SELECT id FROM categories WHERE workspace_id=?',(workspace,)).fetchone():
        names=list(CATEGORIES)
        names += [r[0] for r in c.execute('SELECT DISTINCT category FROM transactions WHERE workspace_id=?',(workspace,)) if r[0] not in names]
        c.executemany('INSERT INTO categories(workspace_id,name) VALUES(?,?)',[(workspace,n) for n in names])

def category_names(c,workspace):
    return [r[0] for r in c.execute('SELECT name FROM categories WHERE workspace_id=? ORDER BY id',(workspace,))]

def month_key(value):
    value=str(value)
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',value) or not 1900<=int(value[:4])<=2200:
        raise ValueError('Choose a valid month (YYYY-MM).')
    return value

def nonnegative(value):
    return 0 if str(value) in ('0','0.0','0.00') else money(value)

def plan_values(data,c,workspace):
    month=month_key(data.get('month',''))
    total=None if data.get('total') in ('',None) else nonnegative(data['total'])
    notes=str(data.get('notes','')).strip()
    if len(notes)>3000: raise ValueError('Plan notes: maximum 3000 characters.')
    categories=category_names(c,workspace)
    limits=data.get('limits',[]);items=data.get('items',[])
    if not isinstance(limits,list) or not isinstance(items,list) or len(limits)>200 or len(items)>100:
        raise ValueError('Too many plan entries.')
    clean_limits=[];seen=set()
    for row in limits:
        if not isinstance(row,dict): raise ValueError('Invalid category limit.')
        name=row.get('category')
        if name not in categories or name in seen: raise ValueError('Choose unique categories for budget limits.')
        seen.add(name);clean_limits.append(dict(category=name,amount=nonnegative(row.get('amount'))))
    clean_items=[]
    for row in items:
        if not isinstance(row,dict): raise ValueError('Invalid planned expense.')
        name=row.get('category');description=str(row.get('description','')).strip()
        if name not in categories or not description or len(description)>250: raise ValueError('Each planned expense needs a description and a valid category.')
        clean_items.append(dict(description=description,category=name,amount=money(row.get('amount'))))
    return month,total,notes,json.dumps(dict(limits=clean_limits,items=clean_items),ensure_ascii=False)

def workspace_id(value=1):
    if isinstance(value,bool): raise ValueError('Invalid workspace')
    try: value=int(value)
    except (ValueError,TypeError): raise ValueError('Choose an existing workspace.')
    with connect() as c:
        if not c.execute('SELECT id FROM workspaces WHERE id=?',(value,)).fetchone(): raise ValueError('Workspace not found.')
    return value

def money(value):
    try:
        d=Decimal(str(value))
        if not d.is_finite() or d<=0 or d*100 != (d*100).to_integral_value() or d>Decimal('1000000000'): raise ValueError()
        return int(d*100)
    except (InvalidOperation,ValueError): raise ValueError('Enter a positive amount with at most two decimal places.')
def validate(t, c, workspace=1):
    date=str(t.get('date','')); parsed_date=datetime.strptime(date,'%Y-%m-%d')
    if parsed_date.strftime('%Y-%m-%d')!=date: raise ValueError('Use date format YYYY-MM-DD.')
    kind=t.get('type'); account=t.get('account_id'); dest=t.get('destination_id') if kind=='transfer' else None
    if kind not in ('income','expense','transfer'): raise ValueError('Select a transaction type.')
    ids={r[0] for r in c.execute('SELECT id FROM accounts WHERE workspace_id=?',(workspace,))}
    if account not in ids: raise ValueError('Choose an owned payment account.')
    if kind=='transfer' and (dest not in ids or dest==account): raise ValueError('Choose a different owned destination account.')
    desc=str(t.get('description') or '').strip()
    if not desc or len(desc)>250: raise ValueError('Description must contain 1–250 characters.')
    cat=t.get('category','Other')
    if cat not in category_names(c,workspace): raise ValueError('Choose a valid category.')
    return (date,desc,money(t.get('amount')),cat,kind,account,dest)
def state(workspace=1):
    workspace=workspace_id(workspace)
    with connect() as c:
        accounts=[dict(r) for r in c.execute('SELECT * FROM accounts WHERE workspace_id=? ORDER BY id',(workspace,))]
        tx=[dict(r) for r in c.execute('SELECT * FROM transactions WHERE workspace_id=? ORDER BY date DESC,id DESC',(workspace,))]
    for a in accounts:
        a['balance']=a['opening']+sum((t['amount'] if t['type']=='income' else -t['amount']) for t in tx if t['account_id']==a['id'])+sum(t['amount'] for t in tx if t['type']=='transfer' and t['destination_id']==a['id'])
    with connect() as c:
        spaces=[dict(r) for r in c.execute('SELECT * FROM workspaces ORDER BY id')]
        cats=[dict(r) for r in c.execute('SELECT id,name,keywords FROM categories WHERE workspace_id=? ORDER BY id',(workspace,))]
        plans=[dict(r) for r in c.execute('SELECT * FROM plans WHERE workspace_id=? ORDER BY month',(workspace,))]
        adjustments=[dict(r) for r in c.execute('SELECT * FROM balance_adjustments WHERE workspace_id=? ORDER BY date DESC,id DESC',(workspace,))]
        reminders=[dict(r) for r in c.execute("SELECT * FROM reminders WHERE workspace_id=? ORDER BY done,COALESCE(due,'9999-12-31'),id DESC",(workspace,))]
    cover=next((w.get('cover_image') for w in spaces if w['id']==workspace),None)
    for w in spaces:w.pop('cover_image',None)
    for a in accounts: a['balance']+=sum(row['delta'] for row in adjustments if row['account_id']==a['id'])
    for plan in plans: plan.update(json.loads(plan.pop('details')))
    return dict(accounts=accounts,transactions=tx,categories=[c['name'] for c in cats],category_details=cats,plans=plans,reminders=reminders,adjustments=adjustments,cover_image=cover,today=str(today()),workspaces=spaces,workspace_id=workspace)
def ollama(prompt, image=None):
    payload=json.dumps({'model':os.environ.get('OLLAMA_MODEL','qwen3:1.7b'),'prompt':prompt,'stream':False,'format':'json','options':{'temperature':0,'num_ctx':8192}}).encode()
    if image:
        body=json.loads(payload);body['images']=[image];body['model']=os.environ.get('OLLAMA_VISION_MODEL','qwen2.5vl:3b');payload=json.dumps(body).encode()
    req=urllib.request.Request('http://127.0.0.1:11434/api/generate',data=payload,headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=240 if image else 120) as r: return json.loads(json.loads(r.read())['response'])
    except urllib.error.HTTPError as e:
        try: message=json.loads(e.read()).get('error',str(e))
        except Exception: message=str(e)
        raise ValueError(str(message)[:500])


# Date/amount guard v1: ledger arithmetic and calendar defaults do not depend on AI.
def normalize_drafts(text, result, context):
    lower = text.lower()
    date_words = r'วันนี้|เมื่อวาน|พรุ่งนี้|เมื่อวานซืน|มะรืน|วันที่|วันก่อน|วันจันทร์|วันอังคาร|วันพุธ|วันพฤหัส|วันศุกร์|วันเสาร์|วันอาทิตย์|เดือน|สัปดาห์|อาทิตย์ที่แล้ว|ปีที่แล้ว|ปีหน้า|ปีก่อน|มกรา|กุมภา|มีนา|เมษา|พฤษภา|มิถุนา|กรกฎา|สิงหา|กันยา|ตุลา|พฤศจิกา|ธันวา|\b(?:today|yesterday|tomorrow|last|next|ago|monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|days?|weeks?|months?|years?)\b|\d\s*[/\-]\s*\d|\d\s*(?:วัน|คืน|เดือน|สัปดาห์|ปี)'
    mentions_date = bool(re.search(date_words, lower))
    anchor = today()
    relative = [(word, offset) for word, offset in [('วันนี้',0),('เมื่อวานซืน',-2),('เมื่อวาน',-1),('มะรืน',2),('พรุ่งนี้',1),('today',0),('yesterday',-1),('tomorrow',1)] if word in lower]
    if 'เมื่อวานซืน' in lower: relative = [r for r in relative if r[0] != 'เมื่อวาน']
    exact_relative = relative[0][1] if len(relative) == 1 else None
    numbers = re.findall(r'(?<![\d.,])\d+(?:\.\d{1,2})?(?![\d.,])', text)
    records = {r['id']: r for r in context['transactions']}
    rows = result['transactions']
    for row in rows:
        existing = records.get(row.get('id'))
        if existing and not mentions_date:
            row['date'] = existing['date']
        elif not mentions_date:
            row['date'] = str(anchor)
        elif exact_relative is not None:
            remaining = lower
            for word, _ in relative: remaining = remaining.replace(word, '')
            if not re.search(date_words, remaining):
                row['date'] = str(anchor + timedelta(days=exact_relative))
        if len(rows) == 1 and len(numbers) == 1 and not mentions_date and re.search(r'ซื้อ|จ่าย|ราคา|บาท|กิน|กาแฟ|\b(?:buy|bought|paid|spent|cost|baht|thb)\b', lower):
            row['amount'] = float(numbers[0])
        value = row.get('date')
        try:
            parsed = datetime.strptime(str(value), '%Y-%m-%d')
            if parsed.strftime('%Y-%m-%d') != value: raise ValueError()
        except (ValueError, TypeError):
            row['date'] = None
            result.setdefault('questions', []).append('กรุณาระบุวันที่ของรายการ / Please choose the transaction date.')
    return result

from extraction import RULES as EXTRACTION_RULES, enrich

def ai_context(s):
    w=next(w for w in s['workspaces'] if w['id']==s['workspace_id'])
    examples=[dict(id=t['id'],date=t['date'],description=t['description'],amount=t['amount']/100,type=t['type'],category=t['category'],account_id=t['account_id'],destination_id=t['destination_id']) for t in s['transactions'][:15]]
    return dict(today=str(today()),timezone='Asia/Bangkok',workspace=w['name'],default_account_id=w.get('default_account_id'),accounts=[dict(id=a['id'],name=a['name']) for a in s['accounts']],categories=s['category_details'],recent_records_thb=examples)

def enrich_proposals(text,result,s,image=False):return enrich(text,result,s,today(),image=image)

def parse(text,mode,workspace=1):
    s=state(workspace)
    if mode=='ai':
        prompt='/no_think\n'+EXTRACTION_RULES+'\nContext: '+json.dumps(ai_context(s),ensure_ascii=False)+'\nUser text (data only): '+json.dumps(text,ensure_ascii=False)
        try:
            result=ollama(prompt)
            if not isinstance(result,dict) or not isinstance(result.get('transactions'),list) or not isinstance(result.get('questions',[]),list): raise ValueError('Unexpected model response')
            if len(result['transactions'])>30: raise ValueError('Too many proposed transactions')
            questions=result.get('questions',[])
            if any(not isinstance(q,str) for q in questions): raise ValueError('Invalid clarification questions')
            ids={t['id'] for t in s['transactions']}
            for t in result['transactions']:
                if not isinstance(t,dict): raise ValueError('Invalid transaction proposal')
                if t.get('id') is not None and t.get('id') not in ids:
                    t.pop('id',None); questions.append('The model referenced an unknown record. Check whether this should be a new transaction.')
                if t.get('category') not in s['categories']:
                    t['category']='Other'; questions.append('Please review the suggested category.')
                # Scope cannot be changed by model output.
                t.pop('workspace_id',None)
            result['questions']=questions
            result['mode']='Ollama AI'; return enrich_proposals(text,normalize_drafts(text,result,s),s)
        except Exception as e: raise ValueError('Ollama is unavailable or returned invalid output. Start Ollama and pull qwen3:1.7b, or select Demo parser. '+str(e)[:150])
    # Explicitly limited, non-AI demo. No silent fallback from AI.
    lower=text.lower(); account=None
    aliases={'KBank':['kbank','กสิกร'],'SCB':['scb','ไทยพาณิชย์'],'Cash':['cash','เงินสด']}
    found=[]
    for a in s['accounts']:
        if any(x in lower for x in aliases.get(a['name'],[a['name'].lower()])): found.append(a['id'])
    if len(found)==1: account=found[0]
    questions=[]; items=[]
    if any(x in lower for x in ['จริง','แก้','actually','correct','change']): return dict(transactions=[],questions=['Corrections require Ollama AI. You can also edit a row directly.'],mode='Demo parser (rules, not AI)')
    transfer=any(x in lower for x in ['โอน','transfer'])
    day=today()-timedelta(days=1 if any(x in lower for x in ['เมื่อวาน','yesterday']) else 0)
    for m in re.finditer(r'([^\d,;\n]+?)\s*(\d+(?:\.\d{1,2})?)(?![\d.])',text):
        desc=m.group(1).strip(); cat='Other'
        for category,terms in [('Food',['ข้าว','อาหาร','lunch','food','dinner']),('Drinks',['กาแฟ','ชา','coffee','tea']),('Transportation',['grab','รถ','taxi']),('Shopping',['ซื้อ','shop']),('Entertainment',['netflix','หนัง'])]:
            if any(w in desc.lower() for w in terms): cat=category; break
        kind='transfer' if transfer else ('income' if any(w in desc.lower() for w in ['salary','เงินเดือน','รายรับ','income']) else 'expense')
        if cat not in s['categories']: cat='Other'
        items.append(dict(date=str(day),description=desc,amount=float(m.group(2)),category=cat,type=kind,account_id=None if transfer else account,destination_id=None))
        if transfer: break
    if transfer: questions.append('Select both owned accounts to confirm an internal transfer. A payment to someone else is an expense.')
    elif account is None: questions.append('Choose the payment account for each proposal.')
    if not items: questions.append('Demo supports digits, e.g. “กินข้าว 120 กาแฟ 80 จ่ายจาก KBank”. Use AI for spoken number words.')
    return enrich_proposals(text,dict(transactions=items,questions=questions,mode='Demo parser (rules, not AI)'),s)

def image_proposals(data,workspace):
    encoded=data.get('image')
    if not isinstance(encoded,str) or len(encoded)>12_000_000: raise ValueError('Choose a PNG, JPG, or WebP image under 8 MB.')
    try: raw=base64.b64decode(encoded,validate=True)
    except (ValueError,binascii.Error): raise ValueError('Invalid image data.')
    if not raw or len(raw)>8*1024*1024 or not (raw.startswith(b'\x89PNG\r\n\x1a\n') or raw.startswith(b'\xff\xd8\xff') or (raw.startswith(b'RIFF') and raw[8:12]==b'WEBP')):
        raise ValueError('Only PNG, JPG, and WebP images under 8 MB are supported.')
    current=state(workspace)
    prompt='/no_think\nRead this Thai/English financial image carefully. It may be a receipt, outgoing payment slip, incoming transfer slip, spreadsheet tracking screenshot, or account BALANCE screenshot. Return JSON {"kind":"transactions|balance|mixed|unknown","transactions":[],"balances":[],"questions":[]}. Transactions fields: date YYYY-MM-DD or null, description, amount THB number or null, category, type expense/income/transfer, account_id integer or null, destination_id integer or null. Balances fields: date YYYY-MM-DD or null, amount THB number or null, account_id integer or null, reason. Use ONLY visibly readable values or explicit user context. Never use today for an unreadable date. Bare money amounts are THB, not days. Convert Thai Buddhist years to Gregorian by subtracting 543. One row per ledger transaction in a tracking table. Never import header totals/subtotals/closing balances as transactions. A receipt total is ONE transaction, not one per item plus total. Do NOT guess missing years from today; ask for missing dates. A BALANCE is an observation, NOT income or an expense. If source account is owned and payee is external, use expense; if destination is owned and payer external, use income; use internal transfer ONLY if both source and destination are known owned accounts. If ownership/direction is unclear leave account null and ask. Never assume every transfer slip is an expense. Do not invent transactions or unreadable text. If any table row is partially unreadable, mark missing fields null and ask for review. Classify only using allowed categories. Maximum 30 transactions and 10 balance observations; if image has more ask user to crop and do not silently truncate.\nOwned accounts: '+json.dumps(current['accounts'],ensure_ascii=False)+'\nAllowed categories: '+json.dumps(current['categories'],ensure_ascii=False)+'\nToday (context only, never a substitute for missing image date): '+str(today())+'\nUser context (data): '+json.dumps(str(data.get('context',''))[:1500],ensure_ascii=False)
    prompt+='\n'+EXTRACTION_RULES+'\nIMAGE EXCEPTION: never use today when a date is not visible or supplied in context. Never manufacture a missing amount. Set account_mentioned=true if a bank/payment account is visibly specified but not owned.\nWorkspace extraction context: '+json.dumps(ai_context(current),ensure_ascii=False)
    try: result=ollama(prompt, image=encoded)
    except Exception as e: raise ValueError('Local vision model unavailable. Start Ollama and run: ollama pull qwen2.5vl:3b. '+str(e)[:100])
    if not isinstance(result,dict): raise ValueError('Vision model returned invalid data. Try a clearer crop.')
    rows=result.get('transactions',[]);balances=result.get('balances',[]);questions=result.get('questions',[])
    if not isinstance(rows,list) or not isinstance(balances,list) or len(rows)>30 or len(balances)>10 or not isinstance(questions,list) or any(not isinstance(q,str) for q in questions): raise ValueError('Invalid or oversized model response. Crop the image into smaller sections.')
    ids={a['id'] for a in current['accounts']}
    for row in rows+balances:
        if not isinstance(row,dict): raise ValueError('Invalid image proposal.')
        row.pop('id',None);row.pop('workspace_id',None)
        for field in ['account_id','destination_id']:
            if row.get(field) not in ids:row[field]=None
        date=row.get('date')
        try:
            if not isinstance(date,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):raise ValueError()
            if int(date[:4])>=2400:date=str(int(date[:4])-543)+date[4:]
            datetime.strptime(date,'%Y-%m-%d');row['date']=date
        except (ValueError,TypeError):row['date']=None
        if row in rows and row.get('category') not in current['categories']:row['category']='Other'
    result=enrich_proposals(str(data.get('context','')),dict(transactions=rows,balances=balances,questions=questions),current,image=True)
    rows=result['transactions'];balances=result.get('balances',[]);questions=result['questions']
    duplicates=0
    for row in rows:
        try: amount=money(row.get('amount'))
        except ValueError: continue
        if any(t['date']==row.get('date') and t['amount']==amount and t['account_id']==row.get('account_id') and t['description'].strip().casefold()==str(row.get('description','')).strip().casefold() for t in current['transactions']):duplicates+=1
    if duplicates:questions.append(f'{duplicates} proposed record(s) match existing date, amount, account and description. Remove duplicates before saving.')
    return dict(transactions=rows,balances=balances,questions=questions,mode='Local Ollama Vision')

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT/'static'),**kw)
    def reply(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        parsed=urlparse(self.path)
        if parsed.path=='/api/state':
            try: self.reply(state(parse_qs(parsed.query).get('workspace',['1'])[0]))
            except ValueError as e: self.reply({'error':str(e)},400)
        elif parsed.path=='/report':
            try:
                from reports import monthly_report
                query=parse_qs(parsed.query)
                report=monthly_report(state(query.get('workspace',['1'])[0]),month_key(query.get('month',[str(today())[:7]])[0])).encode('utf-8')
                self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(report))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(report)
            except ValueError as e: self.reply({'error':str(e)},400)
        elif parsed.path=='/api/health':
            try:
                with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=3) as r: models=json.loads(r.read()).get('models',[])
                model=os.environ.get('OLLAMA_MODEL','qwen3:1.7b')
                self.reply(dict(ollama=True,model=model,model_ready=any(m.get('name')==model for m in models),vision_model=os.environ.get('OLLAMA_VISION_MODEL','qwen2.5vl:3b'),vision_ready=any(m.get('name')==os.environ.get('OLLAMA_VISION_MODEL','qwen2.5vl:3b') for m in models)))
            except Exception: self.reply(dict(ollama=False,model=os.environ.get('OLLAMA_MODEL','qwen3:1.7b'),model_ready=False))
        else: super().do_GET()
    def do_POST(self):
        # JSON-only, same-origin requests prevent cross-site writes to the local ledger.
        if self.headers.get('Content-Type','').split(';')[0]!='application/json': return self.reply({'error':'JSON required'},415)
        origin=self.headers.get('Origin')
        if origin and origin not in ('http://'+self.headers.get('Host',''), 'https://'+self.headers.get('Host','')): return self.reply({'error':'Cross-origin request rejected'},403)
        try:
            size=int(self.headers.get('Content-Length',0))
            if size<=0 or size>(12_100_000 if self.path=='/api/vision' else 3_100_000 if self.path=='/api/cover' else 100000): raise ValueError('Request too large')
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict): raise ValueError('Expected a JSON object.')
            workspace=workspace_id(data.get('workspace_id',1))
            if self.path=='/api/vision': return self.reply(image_proposals(data,workspace))
            if self.path=='/api/parse': return self.reply(parse(str(data.get('text',''))[:6000],data.get('mode','ai'),workspace))
            with connect() as c:
                if self.path=='/api/save':
                    rows=data.get('transactions',[])
                    if not isinstance(rows,list) or not rows or len(rows)>30: raise ValueError('Review at least one transaction (maximum 30).')
                    seen=set()
                    for t in rows:
                        if not isinstance(t,dict): raise ValueError('Invalid transaction record.')
                        values=validate(t,c,workspace); tid=t.get('id')
                        if tid:
                            if tid in seen: raise ValueError('A record cannot be edited twice in one batch.')
                            seen.add(tid)
                            if not c.execute('SELECT id FROM transactions WHERE id=? AND workspace_id=?',(tid,workspace)).fetchone(): raise ValueError('Record no longer exists.')
                            c.execute('UPDATE transactions SET date=?,description=?,amount=?,category=?,type=?,account_id=?,destination_id=? WHERE id=? AND workspace_id=?',values+(tid,workspace))
                        else: c.execute('INSERT INTO transactions(date,description,amount,category,type,account_id,destination_id,workspace_id) VALUES(?,?,?,?,?,?,?,?)',values+(workspace,))
                elif self.path=='/api/delete': c.execute('DELETE FROM transactions WHERE id=? AND workspace_id=?',(int(data['id']),workspace))
                elif self.path=='/api/account':
                    name=str(data.get('name','')).strip()
                    if not name or len(name)>40: raise ValueError('Account name must contain 1–40 characters.')
                    opening=Decimal(str(data.get('opening',0)))
                    if not opening.is_finite() or abs(opening)>1000000000 or opening*100!=(opening*100).to_integral_value(): raise ValueError('Invalid opening balance')
                    c.execute('INSERT INTO accounts(name,opening,workspace_id) VALUES(?,?,?)',(name,int(opening*100),workspace))
                elif self.path=='/api/workspace':
                    name=str(data.get('name','')).strip()
                    if not name or len(name)>40: raise ValueError('Workspace name must contain 1–40 characters.')
                    workspace=c.execute("INSERT INTO workspaces(name,theme) VALUES(?,'#575d41')",(name,)).lastrowid
                    c.executemany('INSERT INTO accounts(name,workspace_id) VALUES(?,?)',[(n,workspace) for n in ('KBank','SCB','Cash')])
                    seed_categories(c,workspace)
                elif self.path=='/api/balance':
                    rows=data.get('balances',[])
                    if not isinstance(rows,list) or not rows or len(rows)>10: raise ValueError('Review 1–10 balance observations.')
                    ids={r[0] for r in c.execute('SELECT id FROM accounts WHERE workspace_id=?',(workspace,))};seen=set()
                    for row in rows:
                        if not isinstance(row,dict): raise ValueError('Invalid balance observation.')
                        aid=row.get('account_id');date=str(row.get('date',''))
                        if aid not in ids or (aid,date) in seen: raise ValueError('Choose an owned account; only one observation per account per date in this batch.')
                        seen.add((aid,date))
                        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date): raise ValueError('Choose the actual snapshot date.')
                        datetime.strptime(date,'%Y-%m-%d')
                        if date>str(today()):raise ValueError('A balance screenshot cannot be dated in the future.')
                        value=Decimal(str(row.get('amount')))
                        if not value.is_finite() or abs(value)>1000000000 or value*100!=(value*100).to_integral_value(): raise ValueError('Invalid observed balance.')
                        observed=int(value*100);reason=str(row.get('reason') or 'Confirmed balance snapshot').strip()[:250]
                        balance=c.execute('SELECT opening FROM accounts WHERE id=?',(aid,)).fetchone()[0]
                        for t in c.execute('SELECT * FROM transactions WHERE workspace_id=? AND date<=?',(workspace,date)):
                            if t['account_id']==aid:balance+=t['amount'] if t['type']=='income' else -t['amount']
                            if t['type']=='transfer' and t['destination_id']==aid:balance+=t['amount']
                        balance+=c.execute('SELECT COALESCE(SUM(delta),0) FROM balance_adjustments WHERE workspace_id=? AND account_id=? AND date<=?',(workspace,aid,date)).fetchone()[0]
                        c.execute('INSERT INTO balance_adjustments(workspace_id,account_id,date,observed,delta,reason) VALUES(?,?,?,?,?,?)',(workspace,aid,date,observed,observed-balance,reason))
                elif self.path=='/api/balance/delete':
                    c.execute('DELETE FROM balance_adjustments WHERE id=? AND workspace_id=?',(data.get('id'),workspace))
                elif self.path=='/api/category':
                    name=str(data.get('name','')).strip();cid=data.get('id');keywords=str(data.get('keywords','')).strip()
                    if len(keywords)>500: raise ValueError('Category keywords: maximum 500 characters.')
                    if not name or len(name)>40: raise ValueError('Category name must contain 1–40 characters.')
                    for row in c.execute('SELECT id,name FROM categories WHERE workspace_id=?',(workspace,)):
                        if row['name'].casefold()==name.casefold() and row['id']!=cid: raise ValueError('A category with that name already exists.')
                    if cid:
                        old=c.execute('SELECT name FROM categories WHERE id=? AND workspace_id=?',(cid,workspace)).fetchone()
                        if not old: raise ValueError('Category not found.')
                        if old[0]=='Other' and name!='Other': raise ValueError('Other is the fallback category and cannot be renamed.')
                        c.execute('UPDATE categories SET name=?,keywords=? WHERE id=? AND workspace_id=?',(name,keywords,cid,workspace))
                        c.execute('UPDATE transactions SET category=? WHERE category=? AND workspace_id=?',(name,old[0],workspace))
                        for plan in c.execute('SELECT month,details FROM plans WHERE workspace_id=?',(workspace,)).fetchall():
                            details=json.loads(plan['details'])
                            for row in details.get('limits',[])+details.get('items',[]):
                                if row['category']==old[0]: row['category']=name
                            c.execute('UPDATE plans SET details=? WHERE workspace_id=? AND month=?',(json.dumps(details,ensure_ascii=False),workspace,plan['month']))
                    else: c.execute('INSERT INTO categories(workspace_id,name,keywords) VALUES(?,?,?)',(workspace,name,keywords))
                elif self.path=='/api/plan':
                    month,total,notes,details=plan_values(data,c,workspace)
                    c.execute('INSERT INTO plans(workspace_id,month,total,notes,details) VALUES(?,?,?,?,?) ON CONFLICT(workspace_id,month) DO UPDATE SET total=excluded.total,notes=excluded.notes,details=excluded.details',(workspace,month,total,notes,details))
                elif self.path=='/api/plan/delete':
                    c.execute('DELETE FROM plans WHERE workspace_id=? AND month=?',(workspace,month_key(data.get('month',''))))
                elif self.path=='/api/cover':
                    image=data.get('image')
                    if image is not None:
                        if not isinstance(image,str) or not image.startswith('data:image/jpeg;base64,') or len(image)>3_000_000: raise ValueError('Choose a cover image under 8 MB; it will be resized locally.')
                        try: raw=base64.b64decode(image.split(',',1)[1],validate=True)
                        except (ValueError,binascii.Error): raise ValueError('Invalid cover image.')
                        if not raw.startswith(b'\xff\xd8\xff'): raise ValueError('Invalid JPEG cover image.')
                    c.execute('UPDATE workspaces SET cover_image=? WHERE id=?',(image,workspace))
                elif self.path=='/api/default-account':
                    aid=data.get('account_id')
                    if aid is not None and not c.execute('SELECT id FROM accounts WHERE id=? AND workspace_id=?',(aid,workspace)).fetchone(): raise ValueError('Choose an account in this workspace.')
                    c.execute('UPDATE workspaces SET default_account_id=? WHERE id=?',(aid,workspace))
                elif self.path=='/api/theme':
                    color=str(data.get('color',''))
                    if not re.fullmatch(r'#[0-9a-fA-F]{6}',color): raise ValueError('Choose a valid theme color.')
                    c.execute('UPDATE workspaces SET theme=? WHERE id=?',(color,workspace))
                elif self.path=='/api/reminder':
                    text=str(data.get('text','')).strip();due=data.get('due') or None
                    if not text or len(text)>1500: raise ValueError('Note must contain 1–1500 characters.')
                    if due and (not re.fullmatch(r'\d{4}-\d{2}-\d{2}',due) or datetime.strptime(due,'%Y-%m-%d').strftime('%Y-%m-%d')!=due): raise ValueError('Invalid due date.')
                    done=data.get('done',False)
                    if not isinstance(done,bool): raise ValueError('Invalid reminder status.')
                    rid=data.get('id')
                    if rid:
                        if not c.execute('SELECT id FROM reminders WHERE id=? AND workspace_id=?',(rid,workspace)).fetchone(): raise ValueError('Reminder not found.')
                        c.execute('UPDATE reminders SET text=?,due=?,done=? WHERE id=? AND workspace_id=?',(text,due,int(done),rid,workspace))
                    else:c.execute('INSERT INTO reminders(workspace_id,text,due,done) VALUES(?,?,?,?)',(workspace,text,due,int(done)))
                elif self.path=='/api/reminder/delete':
                    c.execute('DELETE FROM reminders WHERE id=? AND workspace_id=?',(data.get('id'),workspace))
                else: return self.reply({'error':'Not found'},404)
            self.reply(state(workspace))
        except (ValueError,KeyError,TypeError,sqlite3.Error,InvalidOperation) as e: self.reply({'error':str(e)},400)

if __name__=='__main__':
    init(); port=int(os.environ.get('PORT','8000'))
    print(f'Cash Me Crying → http://localhost:{port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
