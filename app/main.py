import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .core import ROOT, add_fact, best_fact, connect, extract_answer, hotel_view, init_database, quality, resolve_fact, search_hotels, utcnow

app=FastAPI(title='Ostrovok Intelligence',version='1.0.0')
app.mount('/assets',StaticFiles(directory=str(ROOT/'web')),name='assets')

@app.on_event('startup')
def startup():init_database()

class SearchBody(BaseModel):
    query:str=Field(min_length=1,max_length=1000)

class AnswerBody(BaseModel):
    text:str=Field(min_length=1,max_length=2000)

class FeatureBody(BaseModel):
    key:str=Field(pattern=r'^[a-z][a-z0-9_]{2,48}$')
    label:str
    description:str
    kind:str='text'

class FactBody(BaseModel):
    feature:str
    value:bool|float|int|str
    source:str='hotelier:manual'
    confidence:float=Field(default=0.95,ge=0,le=1)

class SwipeBody(BaseModel):
    guestId:str='demo'
    hotelId:int
    liked:bool

class ChatBody(BaseModel):
    message:str
    guestId:str='demo'
    liked:list[int]=[]


def validate_telegram(init_data:str):
    token=os.getenv('TELEGRAM_BOT_TOKEN','')
    if not token or not init_data:return None
    data=dict(parse_qsl(init_data,keep_blank_values=True))
    supplied=data.pop('hash','')
    try:
        if abs(time.time()-int(data['auth_date']))>86400:return None
    except (KeyError,ValueError):return None
    check='\n'.join(f'{k}={v}' for k,v in sorted(data.items()))
    secret=hmac.new(b'WebAppData',token.encode(),hashlib.sha256).digest()
    expected=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,supplied):return None
    return json.loads(data.get('user','{}'))


def hotelier_access(request:Request):
    key=os.getenv('HOTELIER_API_KEY','')
    if key and not hmac.compare_digest(request.headers.get('X-Hotelier-Key',''),key):
        raise HTTPException(403,'Invalid hotelier key')
    if not key and os.getenv('APP_ENV','development')=='production':
        raise HTTPException(503,'HOTELIER_API_KEY is not configured')

@app.get('/')
def index():return FileResponse(ROOT/'web'/'index.html')

@app.get('/health')
def health():return {'status':'ok','store':'sqlite','demo':True}

@app.get('/v1/hotels')
def hotels():
    with connect() as db:return [hotel_view(db,h) for h in db.execute('SELECT * FROM hotels').fetchall()]

@app.get('/v1/hotels/{hotel_id}')
def get_hotel(hotel_id:int):
    with connect() as db:
        h=db.execute('SELECT * FROM hotels WHERE id=?',(hotel_id,)).fetchone()
        if not h:raise HTTPException(404,'Hotel not found')
        return hotel_view(db,h)

@app.post('/v1/search')
def search(body:SearchBody):
    with connect() as db:return {'query':body.query,'results':search_hotels(db,body.query)}

@app.post('/v1/agent/chat')
def agent_chat(body:ChatBody):
    with connect() as db:
        found=search_hotels(db,body.message,5)
        return {'reply':'Подобраны варианты по указанным пожеланиям. Для каждого указаны подтверждённые характеристики и ограничения.','recommendations':found,'used_llm':False}

@app.get('/v1/features')
def features():
    with connect() as db:return [dict(x) for x in db.execute('SELECT * FROM definitions')]

@app.post('/v1/features')
def create_feature(body:FeatureBody,request:Request):
    hotelier_access(request)
    with connect() as db:
        db.execute('INSERT INTO definitions(key,label,description,kind) VALUES (?,?,?,?) ON CONFLICT(key) DO UPDATE SET label=excluded.label,description=excluded.description,kind=excluded.kind',(body.key,body.label,body.description,body.kind))
        db.commit()
    return {'created':body.key}

@app.get('/v1/hotelier/{hotel_id}/questions')
def questions(hotel_id:int,request:Request):
    hotelier_access(request)
    with connect() as db:return [dict(x) for x in db.execute('SELECT * FROM questions WHERE hotel_id=? ORDER BY id',(hotel_id,))]

@app.post('/v1/hotelier/questions/{question_id}/answer')
def answer(question_id:int,body:AnswerBody,request:Request):
    hotelier_access(request)
    with connect() as db:
        q=db.execute('SELECT * FROM questions WHERE id=?',(question_id,)).fetchone()
        if not q:raise HTTPException(404,'Question not found')
        value=extract_answer(body.text,q['feature'])
        if value is None:raise HTTPException(422,'Could not extract answer')
        status=add_fact(db,q['hotel_id'],q['feature'],value,'hotelier:answer',0.96)
        db.execute('UPDATE questions SET answer=?,status="answered",answered_at=? WHERE id=?',(body.text,utcnow(),question_id))
        db.commit()
        return {'feature':q['feature'],'value':value,'status':status}

@app.post('/v1/hotelier/{hotel_id}/facts')
def update_fact(hotel_id:int,body:FactBody,request:Request):
    hotelier_access(request)
    with connect() as db:
        if not db.execute('SELECT 1 FROM hotels WHERE id=?',(hotel_id,)).fetchone():raise HTTPException(404,'Hotel not found')
        if not db.execute('SELECT 1 FROM definitions WHERE key=?',(body.feature,)).fetchone():raise HTTPException(422,'Unknown feature')
        return {'status':add_fact(db,hotel_id,body.feature,body.value,body.source,body.confidence)}

@app.post('/v1/hotelier/{hotel_id}/resolve')
def resolve(hotel_id:int,body:FactBody,request:Request):
    hotelier_access(request)
    with connect() as db:
        resolve_fact(db,hotel_id,body.feature,body.value)
        return {'status':'resolved'}

@app.get('/v1/metrics')
def metrics():
    with connect() as db:return quality(db)

@app.post('/v1/swipes')
def swipe(body:SwipeBody):
    with connect() as db:
        db.execute('INSERT INTO swipes(guest_id,hotel_id,liked,created_at) VALUES (?,?,?,?)',(body.guestId,body.hotelId,int(body.liked),utcnow()))
        db.commit()
        return {'saved':True,'recommendations':search_hotels(db,'тихий отель рядом с морем',3)}

@app.get('/v1/saved')
def saved(guestId:str=Query('demo',max_length=100)):
    with connect() as db:
        rows=db.execute('SELECT DISTINCT h.* FROM hotels h JOIN swipes s ON s.hotel_id=h.id WHERE s.guest_id=? AND s.liked=1 ORDER BY s.id DESC',(guestId,)).fetchall()
        return [hotel_view(db,h) for h in rows]

@app.get('/v1/profile')
def profile(guestId:str=Query('demo',max_length=100)):
    with connect() as db:
        x=db.execute('SELECT count(*),sum(liked) FROM swipes WHERE guest_id=?',(guestId,)).fetchone()
        return {'guestId':guestId,'swipes':x[0],'liked':x[1] or 0}

@app.get('/v1/auth/telegram')
def telegram_auth(request:Request):
    user=validate_telegram(request.headers.get('X-Telegram-Init-Data',''))
    if not user:raise HTTPException(401,'Telegram authentication failed')
    return {'user':user}
