"""DÉCLIC demo API. Run with: uvicorn app.main:app --reload.

This is a privacy-minimizing, single-instance competition prototype, not a
production LMS. Core grading and structural computation never depend on an LLM.
"""
from __future__ import annotations

import io
import math
import os
import random
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import fitz
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .ai import ai_status, coach, fallback_help, search_sources
from .providers import use_mode,configured_modes
from .engine import Beam, CONCEPTS, MISTAKES_EN, MISTAKES_FR, explanation_check
from .learning import RESOURCES, profile, resources_for, study_plan
from .storage import (
    all_rows, create_session, create_user, db, hash_password, init_db,
    now, one, session_user, verify_password,
)

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'app' / 'static'
MAX_PDF = 12 * 1024 * 1024
MAX_PAGES = 120


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title='DÉCLIC — Adaptive Learning', version='0.1.0', lifespan=lifespan)
from .pilot_security import PilotSecurity
app.add_middleware(PilotSecurity)
app.mount('/static', StaticFiles(directory=STATIC), name='static')


class Register(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    email: EmailStr
    password: str = Field(min_length=8, max_length=120)

    @field_validator('name')
    @classmethod
    def nonblank_name(cls,value):
        if len(value.strip())<2: raise ValueError('Name must contain at least two characters')
        return value.strip()


class Login(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1,max_length=120)


class Preferences(BaseModel):
    exam_date: str | None = None

    @field_validator('exam_date')
    @classmethod
    def date_only(cls, value):
        if value is not None:
            from datetime import date
            try:
                date.fromisoformat(value)
            except ValueError:
                raise ValueError('Date must use YYYY-MM-DD') from None
        return value


class ChallengeRequest(BaseModel):
    kind: str = Field(default='practice', pattern='^(practice|transfer|explore)$')
    length: float | None = Field(default=None, ge=2, le=20)
    load: float | None = Field(default=None, ge=0, le=100)
    position: float | None = Field(default=None, gt=0)
    udl: float | None = Field(default=None, ge=0, le=30)


class Prediction(BaseModel):
    answer: str = Field(pattern='^(left|right|equal)$')


class Submission(BaseModel):
    ra: float
    rb: float
    stage: str = Field(default='practice', pattern='^(practice|transfer)$')

    @field_validator('ra', 'rb')
    @classmethod
    def finite(cls, value):
        if not math.isfinite(value) or abs(value) > 100000:
            raise ValueError('Finite values required')
        return value


class Explanation(BaseModel):
    text: str = Field(min_length=10, max_length=3000)
    lang: str = Field(default='fr',pattern='^(fr|en)$')


class CoachRequest(BaseModel):
    question: str = Field(min_length=3, max_length=800)
    challenge_id: str | None = None
    lang: str = Field(default='fr',pattern='^(fr|en)$')
    reveal: bool = False
    consent_external: bool = False
    ai_mode: str = Field(default='hybrid',pattern='^(local|cloud|hybrid|ollama_cloud)$')


class ReadingEvent(BaseModel):
    page: int = Field(ge=0)
    activity: str = Field(pattern='^(active|view|idle|revisit|completed)$')
    seconds: int = Field(default=0, ge=0, le=60)


def user_from_token(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Authentification requise')
    user = session_user(authorization.removeprefix('Bearer ').strip())
    if not user:
        raise HTTPException(401, 'Session expirée ou invalide')
    return user


def owned_challenge(cid: str, uid: str) -> dict:
    row = one('SELECT * FROM challenges WHERE id=? AND user_id=?', (cid, uid))
    if not row:
        raise HTTPException(404, 'Exercice introuvable')
    return row


def owned_doc(did: str, uid: str) -> dict:
    row = one('SELECT id,title,subject,page_count,created_at FROM documents WHERE id=? AND user_id=?', (did, uid))
    if not row:
        raise HTTPException(404, 'Document introuvable')
    return row


def beam_for(row: dict) -> Beam:
    return Beam(row['length'], row['load'], row['position'], row['udl'])


def basic_challenge(row: dict) -> dict:
    return {k: row[k] for k in ('id', 'kind', 'length', 'load', 'position', 'udl', 'created_at')}


def record_attempt(user_id, challenge_id, stage, concept, correct, misconception, answer) -> bool:
    # A stage is immutable: submitting again must not erase earlier mistakes.
    try:
        with db() as con:
            con.execute('INSERT INTO attempts(id,user_id,challenge_id,stage,concept,correct,misconception,input,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                (uuid.uuid4().hex,user_id,challenge_id,stage,concept,int(correct),misconception,answer,now()))
        return True
    except sqlite3.IntegrityError:
        return False


@app.get('/')
def homepage():
    return FileResponse(STATIC / 'index.html')


@app.get('/api/health')
def health():
    from .speech_stream import capabilities
    return {'status':'ok','version':'0.1.0','calculation_engine':'deterministic','ai':{**ai_status(),'local_only':local_generation_allowed(),'modes':configured_modes()},'speech':capabilities()}


@app.post('/api/auth/register', status_code=201)
def register(payload: Register):
    try:
        uid = create_user(payload.name.strip(),str(payload.email),payload.password)
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'Adresse email déjà utilisée') from None
    return {'token':create_session(uid),'user':{'id':uid,'name':payload.name.strip(),'email':str(payload.email)}}


@app.post('/api/auth/login')
def login(payload: Login):
    u = one('SELECT * FROM users WHERE email=?', (str(payload.email).lower(),))
    if not u or not u['password_hash'] or not verify_password(payload.password,u['password_hash']):
        raise HTTPException(401, 'Identifiants incorrects')
    return {'token':create_session(u['id']),'user':{'id':u['id'],'name':u['name'],'email':u['email']}}


@app.post('/api/auth/demo')
def demo():
    # Deliberately isolates each demo session; does not impersonate any learner.
    uid = create_user('Étudiant démo',f'demo-{uuid.uuid4().hex}@example.invalid')
    return {'token':create_session(uid),'user':{'id':uid,'name':'Étudiant démo','demo':True}}


@app.post('/api/auth/logout')
def logout(authorization: str | None = Header(default=None), user=Depends(user_from_token)):
    import hashlib
    with db() as con:
        con.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(authorization[7:].encode()).hexdigest(),))
    return {'ok':True}


@app.get('/api/me')
def me(user=Depends(user_from_token)):
    return {'id':user['id'],'name':user['name'],'email':user['email'],'exam_date':user['exam_date']}


@app.put('/api/preferences')
def preferences(payload: Preferences,user=Depends(user_from_token)):
    with db() as con:
        con.execute('UPDATE users SET exam_date=? WHERE id=?', (payload.exam_date,user['id']))
    return {'ok':True,'exam_date':payload.exam_date}


@app.get('/api/dashboard')
def dashboard(user=Depends(user_from_token)):
    p=profile(user['id'],user['exam_date'])
    docs=all_rows('SELECT id,title,subject,page_count,created_at FROM documents WHERE user_id=? ORDER BY created_at DESC', (user['id'],))
    usage=one('SELECT COALESCE(SUM(seconds),0) AS active_seconds,COUNT(DISTINCT document_id) AS opened_documents FROM reading_events WHERE user_id=? AND activity=?',(user['id'],'active'))
    return {'profile':p,'resources':resources_for(p),'documents':docs,'reading':usage,'user':{'name':user['name'],'exam_date':user['exam_date']}}


@app.get('/api/graph')
def graph(user=Depends(user_from_token)):
    return {'nodes':CONCEPTS,'links':[
        {'source':'force_balance','target':'support_reactions'},
        {'source':'moment_equilibrium','target':'support_reactions'},
        {'source':'support_reactions','target':'load_transfer'},
        {'source':'force_balance','target':'moment_equilibrium'}]}


@app.post('/api/challenges', status_code=201)
def create_challenge(payload: ChallengeRequest, user=Depends(user_from_token)):
    if payload.kind == 'transfer' and not one("SELECT p.id FROM attempts p JOIN attempts e ON e.user_id=p.user_id AND e.challenge_id=p.challenge_id AND e.stage='explanation' WHERE p.user_id=? AND p.stage='practice' LIMIT 1",(user['id'],)):
        raise HTTPException(409,'Terminez un exercice et son explication avant le test de transfert')
    if payload.length is not None:
        length=payload.length
    else:
        length=float(random.choice([6,8,10,12]))
    load=payload.load if payload.load is not None else float(random.choice([8,12,16,20]))
    position=payload.position if payload.position is not None else round(length * random.choice([0.25,0.35,0.6,0.75]),2)
    udl=payload.udl if payload.udl is not None else float(random.choice([0,0,2,4]))
    try:
        b=Beam(length,load,position,udl)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from None
    if payload.kind=='transfer' and one('SELECT id FROM challenges WHERE user_id=? AND length=? AND load=? AND position=? AND udl=?',(user['id'],b.length,b.load,b.position,b.udl)):
        if any(v is not None for v in (payload.length,payload.load,payload.position,payload.udl)):
            raise HTTPException(409,'Choisis une configuration réellement inédite')
        for _ in range(80):
            length=float(random.choice([6,8,10,12,14,16,18,20]))
            load=float(random.choice([8,12,16,20,24,28,32]))
            position=round(length*random.choice([.2,.25,.35,.45,.6,.7,.75,.8]),2)
            udl=float(random.choice([0,2,4,6]))
            b=Beam(length,load,position,udl)
            if not one('SELECT id FROM challenges WHERE user_id=? AND length=? AND load=? AND position=? AND udl=?',(user['id'],length,load,position,udl)):
                break
        else:
            raise HTTPException(409,'Impossible de générer un cas inédit')
    if not b.validate_equilibrium():
        raise HTTPException(500,'Échec de vérification statique')
    cid=uuid.uuid4().hex
    with db() as con:
        con.execute('INSERT INTO challenges(id,user_id,kind,length,load,position,udl,created_at) VALUES(?,?,?,?,?,?,?,?)',(cid,user['id'],payload.kind,length,load,position,udl,now()))
    return {'challenge':{'id':cid,'kind':payload.kind,'length':length,'load':load,'position':position,'udl':udl},'stage':'predict'}


@app.get('/api/challenges/current')
def current_challenge(user=Depends(user_from_token)):
    row=one('SELECT * FROM challenges WHERE user_id=? ORDER BY created_at DESC LIMIT 1',(user['id'],))
    if not row:
        return {'challenge':None,'attempts':[]}
    attempts=all_rows('SELECT stage,concept,correct,misconception,input,created_at FROM attempts WHERE user_id=? AND challenge_id=? ORDER BY created_at',(user['id'],row['id']))
    result={'challenge':basic_challenge(row),'attempts':attempts}
    solved=next((a for a in attempts if a['stage'] in ('practice','transfer')),None)
    if solved:
        b=beam_for(row)
        result['solution']=b.overview()
        result['expected']={'ra':round(b.ra,3),'rb':round(b.rb,3)}
        result['feedback_fr']=MISTAKES_FR.get(solved['misconception'],'Les deux équations d’équilibre sont vérifiées.')
        result['feedback_en']=MISTAKES_EN.get(solved['misconception'],'Both equilibrium equations are satisfied.')
    return result


@app.get('/api/challenges/{challenge_id}')
def get_challenge(challenge_id: str,user=Depends(user_from_token)):
    row=owned_challenge(challenge_id,user['id'])
    attempts=all_rows('SELECT stage,concept,correct,misconception,created_at FROM attempts WHERE user_id=? AND challenge_id=? ORDER BY created_at', (user['id'],challenge_id))
    return {'challenge':basic_challenge(row),'attempts':attempts}


@app.post('/api/challenges/{challenge_id}/predict')
def predict(challenge_id: str,payload: Prediction,user=Depends(user_from_token)):
    row=owned_challenge(challenge_id,user['id'])
    b=beam_for(row)
    expected=b.expected_prediction()
    correct=payload.answer==expected
    misconception=None if correct else 'symmetry_assumption' if payload.answer=='equal' else 'moment_equilibrium'
    saved=record_attempt(user['id'],challenge_id,'prediction','support_reactions',correct,misconception,payload.answer)
    if not saved:
        raise HTTPException(409,'Prévision déjà enregistrée')
    return {'correct':correct,'expected':expected,'feedback':'Prédiction correcte : passe aux équations.' if correct else 'Observe le côté le plus proche de la charge : sa réaction est généralement plus élevée.','feedback_en':'Correct prediction. Proceed to the equations.' if correct else 'Observe which support is closer to the point load.'}


@app.post('/api/challenges/{challenge_id}/submit')
def submit(challenge_id: str,payload: Submission,user=Depends(user_from_token)):
    row=owned_challenge(challenge_id,user['id'])
    if payload.stage=='transfer' and row['kind']!='transfer':
        raise HTTPException(422,'Utilise un nouvel exercice de transfert')
    if payload.stage=='practice' and row['kind']=='transfer':
        raise HTTPException(422,'Exercice réservé au transfert')
    if not one('SELECT id FROM attempts WHERE user_id=? AND challenge_id=? AND stage=?',(user['id'],challenge_id,'prediction')):
        raise HTTPException(409,'Commence par une prévision')
    b=beam_for(row)
    verdict=b.check(payload.ra,payload.rb)
    concept= 'force_balance' if verdict['misconception'] in ('force_balance','forgot_distributed_load') else 'moment_equilibrium' if verdict['misconception'] in ('moment_equilibrium','moment_arms_reversed','symmetry_assumption') else 'load_transfer' if payload.stage=='transfer' else 'support_reactions'
    saved=record_attempt(user['id'],challenge_id,payload.stage,concept,verdict['correct'],verdict['misconception'],f'{payload.ra}|{payload.rb}')
    if not saved:
        raise HTTPException(409,'Tentative déjà enregistrée ; crée un nouvel exercice')
    explanation = MISTAKES_FR.get(verdict['misconception'],'Très bien : les deux équations d’équilibre sont vérifiées.')
    return {**verdict,'expected':{'ra':round(b.ra,3),'rb':round(b.rb,3)},'explanation':explanation,'explanation_en':MISTAKES_EN.get(verdict['misconception'],'Well done: both equilibrium equations are satisfied.'),'solution':b.overview(), 'profile':profile(user['id'],user['exam_date'])}


@app.post('/api/challenges/{challenge_id}/explain')
def explain(challenge_id: str,payload: Explanation,user=Depends(user_from_token)):
    owned_challenge(challenge_id,user['id'])
    if not one('SELECT id FROM attempts WHERE user_id=? AND challenge_id=? AND stage IN (?,?)',(user['id'],challenge_id,'practice','transfer')):
        raise HTTPException(409,'Résous les équations avant de les expliquer')
    result=explanation_check(payload.text,payload.lang)
    saved=record_attempt(user['id'],challenge_id,'explanation','moment_equilibrium',result['quality']=='complete',None if result['quality']=='complete' else 'incomplete_reasoning',payload.text)
    if not saved:
        raise HTTPException(409,'Explication déjà soumise ; essaie un autre exercice')
    return {**result,'note':'Checklist pédagogique basée sur des indices textuels, pas une notation de vérité.'}


@app.get('/api/study-plan')
def learner_study_plan(minutes:int=Query(30,ge=10,le=120),user=Depends(user_from_token)):
    return study_plan(profile(user['id'],user['exam_date']),minutes)

@app.get('/api/resources')
def resources(user=Depends(user_from_token)):
    return {'items':resources_for(profile(user['id'],user['exam_date'])),'curated':True}


@app.get('/api/documents')
def list_documents(user=Depends(user_from_token)):
    return {'documents':all_rows('SELECT id,title,subject,page_count,created_at FROM documents WHERE user_id=? ORDER BY created_at DESC',(user['id'],))}


@app.post('/api/documents', status_code=201)
async def upload_document(file: UploadFile = File(...),subject: str = Form('RDM2',max_length=50),user=Depends(user_from_token)):
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(415,'Seuls les fichiers PDF sont acceptés')
    data=await file.read(MAX_PDF+1)
    if len(data)>MAX_PDF:
        raise HTTPException(413,'PDF trop volumineux (12 Mo max)')
    if not data.startswith(b'%PDF-'):
        raise HTTPException(415,'Le fichier ne semble pas être un PDF')
    try:
        pdf=fitz.open(stream=data,filetype='pdf')
        if pdf.needs_pass:
            raise HTTPException(422,'Les PDF chiffrés ne sont pas acceptés')
        if pdf.page_count==0 or pdf.page_count>MAX_PAGES:
            raise HTTPException(422,f'Le document doit contenir entre 1 et {MAX_PAGES} pages')
        pdf.close()
        import asyncio
        from .ocr import extract_pages
        pages,methods=await asyncio.to_thread(extract_pages,data)
        count=len(pages)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422,'PDF illisible') from None
    did=uuid.uuid4().hex
    title=Path(file.filename.replace('\\','/')).name[:160]
    with db() as con:
        con.execute('INSERT INTO documents(id,user_id,title,subject,data,page_count,created_at) VALUES(?,?,?,?,?,?,?)',(did,user['id'],title,subject[:50],data,count,now()))
        con.executemany('INSERT INTO document_pages(document_id,page,content) VALUES(?,?,?)',[(did,p,text) for p,text in pages])
        con.executemany('INSERT INTO page_extraction(document_id,page,method) VALUES(?,?,?)',[(did,p,m) for p,m in methods])
    return {'id':did,'title':title,'page_count':count,'indexed_pages':sum(bool(t.strip()) for _,t in pages),'extraction':[{'page':p,'method':m} for p,m in methods]}


@app.post('/api/documents/{document_id}/pages/{page}/ocr')
def retry_page_ocr(document_id:str,page:int,user=Depends(user_from_token)):
    """Explicitly retry a deferred or unreadable page, without replacing native text."""
    from .ocr import extract_pages
    d=owned_doc(document_id,user['id'])
    if not 0<=page<d['page_count']:raise HTTPException(404,'Page introuvable')
    existing=one('SELECT content FROM document_pages WHERE document_id=? AND page=?',(document_id,page))
    if existing and existing['content'].strip() and not one("SELECT 1 FROM page_extraction WHERE document_id=? AND page=? AND method IN ('ocr_deferred','ocr_unavailable','ocr_failed','empty')",(document_id,page)):
        raise HTTPException(409,'Cette page contient déjà du texte indexé')
    source=one('SELECT data FROM documents WHERE id=? AND user_id=?',(document_id,user['id']))
    if not source:raise HTTPException(404,'Document introuvable')
    with fitz.open(stream=source['data'],filetype='pdf') as pdf, fitz.open() as single:
        single.insert_pdf(pdf,from_page=page,to_page=page)
        pages,methods=extract_pages(single.tobytes(),max_ocr=1,deadline_seconds=10)
    content=pages[0][1];method=methods[0][1]
    with db() as con:
        if not con.execute("UPDATE document_pages SET content=? WHERE document_id=? AND page=? AND EXISTS (SELECT 1 FROM documents WHERE id=? AND user_id=?)",(content,document_id,page,document_id,user['id'])).rowcount:
            raise HTTPException(404,'Document introuvable')
        con.execute("INSERT INTO page_extraction(document_id,page,method) VALUES(?,?,?) ON CONFLICT(document_id,page) DO UPDATE SET method=excluded.method",(document_id,page,method))
    return {'page':page,'method':method,'content':content}


@app.get('/api/documents/{document_id}/pdf')
def download_document(document_id:str,user=Depends(user_from_token)):
    owned_doc(document_id,user['id'])
    row=one('SELECT data FROM documents WHERE id=? AND user_id=?',(document_id,user['id']))
    return Response(row['data'],media_type='application/pdf',headers={'Content-Disposition':'inline; filename="course.pdf"','Cache-Control':'private, no-store'})


@app.get('/api/documents/{document_id}/pages/{page}/image')
def document_page_image(document_id:str,page:int,scale:float=Query(1.3,ge=.6,le=2),user=Depends(user_from_token)):
    d=owned_doc(document_id,user['id'])
    if not 0<=page<d['page_count']:
        raise HTTPException(404,'Page introuvable')
    data=one('SELECT data FROM documents WHERE id=?',(document_id,))['data']
    with fitz.open(stream=data,filetype='pdf') as pdf:
        p=pdf.load_page(page)
        safe_scale=min(scale, math.sqrt(7_900_000/max(1,p.rect.width*p.rect.height)), 4095/max(1,p.rect.width,p.rect.height))
        pix=p.get_pixmap(matrix=fitz.Matrix(safe_scale,safe_scale),alpha=False)
        content=pix.tobytes('png')
    return Response(content,media_type='image/png',headers={'Cache-Control':'private, no-store'})


@app.get('/api/documents/{document_id}/pages/{page}/text')
def document_page_text(document_id:str,page:int,user=Depends(user_from_token)):
    d=owned_doc(document_id,user['id'])
    if not 0<=page<d['page_count']:
        raise HTTPException(404,'Page introuvable')
    data=one('SELECT content FROM document_pages WHERE document_id=? AND page=?',(document_id,page))
    method=one('SELECT method FROM page_extraction WHERE document_id=? AND page=?',(document_id,page))
    return {'title':d['title'],'page':page,'content':data['content'],'method':method['method'] if method else 'legacy'}


@app.post('/api/documents/{document_id}/events',status_code=201)
def reading_event(document_id:str,payload:ReadingEvent,user=Depends(user_from_token)):
    d=owned_doc(document_id,user['id'])
    if payload.page>=d['page_count']:
        raise HTTPException(422,'Page hors limites')
    if payload.activity!='active' and payload.seconds!=0:
        raise HTTPException(422,'Durée réservée aux événements actifs')
    with db() as con:
        con.execute('INSERT INTO reading_events(user_id,document_id,page,activity,seconds,created_at) VALUES(?,?,?,?,?,?)',(user['id'],document_id,payload.page,payload.activity,payload.seconds,now()))
    return {'recorded':True}


@app.get('/api/documents/{document_id}/analytics')
def document_analytics(document_id:str,user=Depends(user_from_token)):
    d=owned_doc(document_id,user['id'])
    bypage=all_rows('SELECT page,SUM(CASE WHEN activity=? THEN seconds ELSE 0 END) AS seconds,COUNT(*) AS events,MAX(CASE WHEN activity IN (?,?) THEN 1 ELSE 0 END) AS viewed FROM reading_events WHERE user_id=? AND document_id=? GROUP BY page ORDER BY page',('active','view','revisit',user['id'],document_id))
    pages={x['page']:x for x in bypage}
    items=[{'page':n,'seconds':int(pages.get(n,{}).get('seconds') or 0),'viewed':bool(pages.get(n,{}).get('viewed'))} for n in range(d['page_count'])]
    return {'document':d,'pages':items,'total_seconds':sum(x['seconds'] for x in items),'pages_visited':sum(x['viewed'] for x in items),'note':'Temps estimé à partir des intervalles actifs dans le lecteur DÉCLIC ; il ne prouve pas l’attention ni la compréhension.'}


@app.post('/api/coach')
async def tutor(payload:CoachRequest,user=Depends(user_from_token)):
    if payload.challenge_id:
        row=owned_challenge(payload.challenge_id,user['id'])
        b=beam_for(row)
        attempted=bool(one('SELECT id FROM attempts WHERE user_id=? AND challenge_id=? AND stage IN (?,?)',(user['id'],payload.challenge_id,'practice','transfer')))
    else:
        b=Beam()
        attempted=False
    if payload.challenge_id and row['kind']=='transfer' and not attempted:
        return {'mode':'guided_offline','answer':'Termine ton essai indépendant avant de demander une aide liée à cet exercice.' if payload.lang=='fr' else 'Finish your independent attempt before requesting help with this exercise.','sources':[],'notice':'Évaluation indépendante' if payload.lang=='fr' else 'Independent assessment'}
    pages=all_rows('SELECT d.id AS document_id,d.title,p.page,p.content FROM document_pages p JOIN documents d ON d.id=p.document_id WHERE d.user_id=? LIMIT 900',(user['id'],))
    sources=search_sources(pages,payload.question)
    with use_mode(payload.ai_mode,payload.consent_external) as effective:
        if effective=="disabled":
            result=fallback_help(payload.question,b,payload.lang,sources)
            result["notice"]="Aucun partage externe sans consentement." if payload.lang=="fr" else "No external sharing without consent."
            return result
        return await coach(payload.question,b,payload.lang,sources,reveal=attempted)



class StudioTurn(BaseModel):
    role: str = Field(pattern='^(student|tutor)$')
    text: str = Field(min_length=1,max_length=1600)

class StudioRequest(BaseModel):
    question: str = Field(min_length=3,max_length=800)
    challenge_id: str | None = None
    lang: str = Field(default='fr',pattern='^(fr|en)$')
    consent_external: bool = False
    ai_mode: str = Field(default='hybrid',pattern='^(local|cloud|hybrid|ollama_cloud)$')
    history: list[StudioTurn] = Field(default_factory=list,max_length=8)
    generative: bool = False

@app.post('/api/studio')
async def studio(payload:StudioRequest,request:Request,user=Depends(user_from_token)):
    from .cancellation import until_disconnect
    from .studio import teach
    row=owned_challenge(payload.challenge_id,user['id']) if payload.challenge_id else None
    if row and row['kind']=='transfer' and not one("SELECT id FROM attempts WHERE user_id=? AND challenge_id=? AND stage='transfer'",(user['id'],row['id'])):
        raise HTTPException(409,'Termine ton essai indépendant avant de demander une leçon liée à cet exercice.' if payload.lang=='fr' else 'Finish your independent attempt before requesting a lesson linked to this exercise.')
    b=beam_for(row) if row else Beam()
    pages=all_rows('SELECT d.id AS document_id,d.title,p.page,p.content FROM document_pages p JOIN documents d ON d.id=p.document_id WHERE d.user_id=? LIMIT 900',(user['id'],))
    from .studio_context import resolve_turn,needs_fresh_data,unavailable_fresh,short_pythagoras
    question,history=resolve_turn(payload.question,[x.model_dump() for x in payload.history])
    if needs_fresh_data(question):return unavailable_fresh(payload.lang)
    sources=search_sources(pages,question)
    with use_mode(payload.ai_mode,payload.consent_external) as effective:
        enabled=effective!="disabled" and ai_status()["enabled"]
        if payload.generative and enabled:
            from .whiteboard import generate
            result=await until_disconnect(request,generate(question,payload.lang,sources,history))
            if result is not None:
                return result
        if payload.generative:
            known=short_pythagoras(question,payload.lang,sources)
            if known is not None:return known
        result=await until_disconnect(request,teach(question,b,payload.lang,sources,history,enabled))
        result['visual_mode']='predefined'
        if payload.generative:
            result['notice'] += ' · Tableau génératif non disponible' if payload.lang=='fr' else ' · Generative board unavailable'
        return result



@app.get('/api/studio/voices')
def studio_voices(user=Depends(user_from_token)):
    from .voice import voice_choices
    return {"voices":voice_choices()}

@app.post('/api/studio/audio')
async def studio_audio(payload: dict, request:Request,user=Depends(user_from_token)):
    from .cancellation import until_disconnect
    import asyncio
    import json
    from .voice import synthesize_preferred
    text=payload.get('text')
    lang=payload.get('lang','fr')
    cues=payload.get('cues',[])
    if not isinstance(text,str) or not 1<=len(text)<=450 or lang not in ('fr','en') or not isinstance(cues,list) or len(cues)>32:
        raise HTTPException(422,'Invalid narration')
    options={"cloud":payload.get('cloud') is True and payload.get('consent_external') is True and payload.get('ai_mode')!='local'}
    if payload.get('voice_name') is not None:options['voice_name']=payload['voice_name']
    try:
        audio,marks,backend=await until_disconnect(request,asyncio.wait_for(synthesize_preferred(text,lang,cues,**options),45))
    except (ValueError,TypeError):
        raise HTTPException(422,'Invalid narration or cue')
    except (FileNotFoundError,asyncio.TimeoutError):
        raise HTTPException(503,'Neural voice unavailable')
    return Response(audio,media_type='audio/wav',headers={'Cache-Control':'no-store','X-Studio-Voice':backend,'X-Studio-Cues':json.dumps(marks,separators=(',',':'))})

class StudioReviewRequest(BaseModel):
    question: str = Field(min_length=3,max_length=800)
    steps: list[dict] = Field(min_length=2,max_length=5)
    author_model: str = Field(min_length=1,max_length=200)
    consent_external: bool = False
    ai_mode: str = Field(default='hybrid',pattern='^(local|cloud|hybrid|ollama_cloud)$')

@app.post('/api/studio/review')
async def studio_review(payload:StudioReviewRequest,user=Depends(user_from_token)):
    import json
    from .whiteboard import validate_board
    from .reviewer import review
    if not payload.consent_external and payload.ai_mode!='local' and not local_generation_allowed():
        raise HTTPException(403,'External review requires consent')
    try:
        steps=validate_board(json.dumps({'steps':payload.steps},ensure_ascii=False))
    except (ValueError,TypeError,KeyError):
        raise HTTPException(422,'Invalid visual lesson')
    with use_mode(payload.ai_mode,payload.consent_external):
        return await review(payload.question,steps,payload.author_model)


@app.delete('/api/documents/{document_id}')
def delete_document(document_id:str,user=Depends(user_from_token)):
    with db() as con:
        # Quiz snapshots may contain course excerpts: remove them on document deletion.
        import json
        for q in con.execute('SELECT id,questions FROM quizzes WHERE user_id=?',(user['id'],)).fetchall():
            if any(x.get('document_id')==document_id for x in json.loads(q['questions'])):
                con.execute('DELETE FROM quizzes WHERE id=?',(q['id'],))
        result=con.execute('DELETE FROM documents WHERE id=? AND user_id=?',(document_id,user['id']))
        if not result.rowcount: raise HTTPException(404,'Document introuvable')
    return {'deleted':True}

@app.delete('/api/me')
def delete_account(user=Depends(user_from_token)):
    uid=user['id']
    with db() as con:
        for table in ('sessions','attempts','reading_events','documents','challenges'):
            con.execute(f'DELETE FROM {table} WHERE user_id=?',(uid,))
        con.execute('DELETE FROM users WHERE id=?',(uid,))
    return {'deleted':True}


def local_generation_allowed():
    from .providers import local_only,local_model
    return local_only() and bool(local_model())

from .course_tools import install as install_course_tools
install_course_tools(app,user_from_token)

from .class_assignments import install as install_assignments
install_assignments(app,user_from_token)

from .speech_stream import install as install_speech_stream
install_speech_stream(app)


@app.get('/api/providers/status')
async def providers_status(user=Depends(user_from_token)):
    from .providers import provider_status
    return await provider_status()
