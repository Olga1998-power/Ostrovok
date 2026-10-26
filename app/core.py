import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / 'data' / 'demo.sqlite3'


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def connect(path=DATABASE):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def init_database(path=DATABASE):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = connect(path)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS hotels(id INTEGER PRIMARY KEY, name TEXT NOT NULL, city TEXT NOT NULL, area TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, description TEXT NOT NULL, image TEXT, price INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY AUTOINCREMENT, hotel_id INTEGER NOT NULL REFERENCES hotels(id), feature TEXT NOT NULL, value TEXT NOT NULL, source TEXT NOT NULL, confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1), observed_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','conflict','superseded')), UNIQUE(hotel_id,feature,value,source));
    CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY AUTOINCREMENT, hotel_id INTEGER NOT NULL REFERENCES hotels(id), text TEXT NOT NULL, feature TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', answer TEXT, created_at TEXT NOT NULL, answered_at TEXT);
    CREATE TABLE IF NOT EXISTS definitions(key TEXT PRIMARY KEY, label TEXT NOT NULL, description TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'text');
    CREATE TABLE IF NOT EXISTS swipes(id INTEGER PRIMARY KEY AUTOINCREMENT, guest_id TEXT NOT NULL, hotel_id INTEGER NOT NULL, liked INTEGER NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS landmarks(id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS change_log(id INTEGER PRIMARY KEY AUTOINCREMENT, hotel_id INTEGER NOT NULL, feature TEXT NOT NULL, change_type TEXT NOT NULL, created_at TEXT NOT NULL);
    ''')
    if not db.execute('SELECT COUNT(*) FROM hotels').fetchone()[0]:
        seed = json.loads((ROOT/'data'/'seed.json').read_text(encoding='utf-8'))
        db.executemany('INSERT INTO hotels VALUES (:id,:name,:city,:area,:lat,:lon,:description,:image,:price)',seed['hotels'])
        db.executemany('INSERT INTO landmarks VALUES (:id,:name,:category,:lat,:lon)',seed['landmarks'])
        db.executemany('INSERT INTO definitions VALUES (:key,:label,:description,:kind)',seed['definitions'])
        for fact in seed['facts']:
            db.execute('INSERT INTO facts(hotel_id,feature,value,source,confidence,observed_at) VALUES (?,?,?,?,?,?)', (fact['hotel_id'],fact['feature'],json.dumps(fact['value'],ensure_ascii=False),fact['source'],fact['confidence'],fact['observed_at']))
        for q in seed['questions']:
            db.execute('INSERT INTO questions(hotel_id,text,feature,created_at) VALUES (?,?,?,?)',(q['hotel_id'],q['text'],q['feature'],utcnow()))
        for hotel in seed['hotels']:
            nearby = [(haversine(hotel['lat'],hotel['lon'],p['lat'],p['lon']),p) for p in seed['landmarks'] if p['category']=='water']
            if nearby:
                dist, landmark = min(nearby, key=lambda x:x[0])
                db.execute('INSERT INTO facts(hotel_id,feature,value,source,confidence,observed_at) VALUES (?,?,?,?,?,?)',(hotel['id'],'water_distance_m',json.dumps(round(dist)),f'geospatial:haversine:landmark:{landmark["id"]}',0.93,utcnow()))
    db.commit()
    db.close()


def haversine(a,b,c,d):
    radius=6371008.8
    p1,p2=math.radians(a),math.radians(c)
    dp=math.radians(c-a)
    dl=math.radians(d-b)
    k=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*radius*math.asin(min(1,math.sqrt(k)))


def add_fact(db, hotel_id, feature, value, source, confidence=0.8):
    value_json=json.dumps(value,ensure_ascii=False)
    active=db.execute('SELECT id,value,source FROM facts WHERE hotel_id=? AND feature=? AND status="active"',(hotel_id,feature)).fetchall()
    conflict=any(json.loads(x['value'])!=value for x in active)
    status='conflict' if conflict else 'active'
    if conflict:
        db.execute('UPDATE facts SET status="conflict" WHERE hotel_id=? AND feature=? AND status="active"',(hotel_id,feature))
        db.execute('INSERT INTO change_log(hotel_id,feature,change_type,created_at) VALUES (?,?,?,?)',(hotel_id,feature,'conflict_detected',utcnow()))
    db.execute('INSERT INTO facts(hotel_id,feature,value,source,confidence,observed_at,status) VALUES (?,?,?,?,?,?,?) ON CONFLICT(hotel_id,feature,value,source) DO UPDATE SET confidence=excluded.confidence,observed_at=excluded.observed_at,status=excluded.status',(hotel_id,feature,value_json,source,confidence,utcnow(),status))
    db.commit()
    return status


def resolve_fact(db, hotel_id, feature, value):
    value_json=json.dumps(value,ensure_ascii=False)
    db.execute('UPDATE facts SET status=CASE WHEN value=? THEN "active" ELSE "superseded" END WHERE hotel_id=? AND feature=?',(value_json,hotel_id,feature))
    db.execute('INSERT INTO change_log(hotel_id,feature,change_type,created_at) VALUES (?,?,?,?)',(hotel_id,feature,'resolved',utcnow()))
    db.commit()


def hotel_view(db, hotel):
    result=dict(hotel)
    rows=db.execute('SELECT feature,value,source,confidence,observed_at,status FROM facts WHERE hotel_id=? ORDER BY confidence DESC',(hotel['id'],)).fetchall()
    facts={}
    for r in rows:
        item=dict(r)
        item['value']=json.loads(item['value'])
        facts.setdefault(item['feature'],[]).append(item)
    result['facts']=facts
    result['conflicts']=[k for k,v in facts.items() if any(x['status']=='conflict' for x in v)]
    return result


def extract_answer(text, feature):
    lower=text.lower().replace('ё','е')
    if feature=='pets_allowed':
        if re.search(r'не (?:разрешен|допуска|пуска|можно)|без животных|запрещен|нельзя',lower): return False
        if re.search(r'можно|разрешен|допуска|пуска|принимаем',lower): return True
    if feature=='pet_max_kg':
        m=re.search(r'(?:до|не более|максимум)\s*(\d+(?:[,.]\d+)?)\s*кг',lower)
        if m:return float(m.group(1).replace(',','.'))
    if feature=='pet_fee_rub':
        m=re.search(r'(\d[\d ]*)\s*(?:руб|₽|р\.)',lower)
        if m:return int(m.group(1).replace(' ',''))
        if 'бесплатно' in lower:return 0
    if feature=='window_direction':
        for word,direction in [('запад','west'),('восток','east'),('север','north'),('юг','south')]:
            if word in lower:return direction
    if feature=='soundproof':
        if re.search(r'нет шумоизоляции|без шумоизоляции',lower):return False
        if 'шумоизоляц' in lower:return True
    if feature=='roof_terrace':
        if 'нет террас' in lower:return False
        if 'террас' in lower:return True
    return text.strip() if text.strip() else None

TERMS={
 'quiet':['тих','тишин','без шума','спокойн'], 'sunset':['закат','запад'],
 'water':['море','моря','пляж','воды','набережн'], 'pets':['питом','собак','кошк','животн'],
 'history':['истори','старин','особняк','архитектур'], 'terrace':['террас','крыше'],
 'cheap':['недорог','бюджет','дешев']
}

def intents(query):
    text=query.lower().replace('ё','е')
    return {k for k,words in TERMS.items() if any(word in text for word in words)}


def best_fact(hotel, feature):
    candidates=[x for x in hotel['facts'].get(feature,[]) if x['status']=='active']
    return max(candidates,key=lambda x:x['confidence']) if candidates else None


def search_hotels(db, query, limit=12):
    requirements=intents(query)
    results=[]
    for row in db.execute('SELECT * FROM hotels').fetchall():
        hotel=hotel_view(db,row)
        score=50
        why=[]
        caveats=[]
        def check(key, matched, good, bad, points=18):
            nonlocal score
            if key in requirements:
                score += points if matched else -points//2
                (why if matched else caveats).append(good if matched else bad)
        quiet=best_fact(hotel,'quiet')
        direction=best_fact(hotel,'window_direction')
        pets=best_fact(hotel,'pets_allowed')
        terrace=best_fact(hotel,'roof_terrace')
        history=best_fact(hotel,'building_history')
        distance=best_fact(hotel,'water_distance_m')
        check('quiet',bool(quiet and quiet['value'] is True),'Подтверждена тихая обстановка','Тишина не подтверждена')
        check('sunset',bool(direction and direction['value']=='west'),'Есть номера с западными окнами','Западный вид не подтверждён')
        check('pets',bool(pets and pets['value'] is True),'Размещение с питомцем разрешено','Условия для питомцев не подтверждены')
        check('terrace',bool(terrace and terrace['value'] is True),'Есть терраса','Терраса не подтверждена')
        check('history',bool(history),'Есть сведения об истории здания','История здания пока не проверена')
        check('water',bool(distance and distance['value']<=1200),f"До воды около {distance['value']} м" if distance else 'Вода рядом','До воды далеко или расстояние не определено',22)
        check('cheap',hotel['price']<=6500,'Доступная цена в демокаталоге','Стоимость выше бюджетного порога')
        results.append({'hotel':hotel,'score':max(0,min(100,score)),'why':why or ['Подходит для знакомства с регионом'],'caveats':caveats,'requirements':sorted(requirements)})
    return sorted(results,key=lambda r:(-r['score'],r['hotel']['price']))[:limit]


def quality(db):
    hotel_count=db.execute('SELECT count(*) FROM hotels').fetchone()[0]
    feature_count=db.execute('SELECT count(*) FROM definitions').fetchone()[0]
    observed=db.execute('SELECT count(DISTINCT hotel_id || ":" || feature) FROM facts WHERE status="active"').fetchone()[0]
    conflicts=db.execute('SELECT count(DISTINCT hotel_id || ":" || feature) FROM facts WHERE status="conflict"').fetchone()[0]
    questions=db.execute('SELECT count(*),sum(CASE WHEN status="answered" THEN 1 ELSE 0 END) FROM questions').fetchone()
    return {'hotels':hotel_count,'features':feature_count,'coverage':round(observed/max(1,hotel_count*feature_count),3),'conflicts':conflicts,'questions_total':questions[0],'questions_answered':questions[1] or 0,'question_rate':round(questions[0]/max(1,hotel_count*feature_count),3)}
