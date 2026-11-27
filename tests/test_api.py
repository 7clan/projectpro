import io
import fitz
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DECLIC_DB_PATH',str(tmp_path/'db.sqlite3'))
    with TestClient(app) as c:
        yield c

@pytest.fixture
def auth(client):
    r=client.post('/api/auth/demo')
    assert r.status_code==200
    return {'Authorization':'Bearer '+r.json()['token']}


def test_auth_and_safety(client,auth):
    assert client.get('/api/dashboard').status_code==401
    r=client.get('/api/dashboard',headers=auth)
    assert r.status_code==200
    assert r.json()['profile']['average_mastery'] is None
    assert client.post('/api/auth/register',json={'name':'Jane Doe','email':'jane@example.org','password':'test-password-123'}).status_code==201
    assert client.post('/api/auth/register',json={'name':'Jane Doe','email':'jane@example.org','password':'test-password-123'}).status_code==409
    assert client.post('/api/auth/login',json={'email':'jane@example.org','password':'bad'}).status_code==401
    assert client.post('/api/auth/login',json={'email':'jane@example.org','password':'test-password-123'}).status_code==200


def test_full_learning_cycle(client,auth):
    new=client.post('/api/challenges',headers=auth,json={'kind':'practice','length':8,'load':12,'position':2,'udl':2})
    assert new.status_code==201
    cid=new.json()['challenge']['id']
    def url(p):return '/api/challenges/'+cid+p
    assert client.post(url('/submit'),headers=auth,json={'ra':17,'rb':11}).status_code==409
    r=client.post(url('/predict'),headers=auth,json={'answer':'equal'})
    assert r.status_code==200 and not r.json()['correct']
    assert client.post(url('/predict'),headers=auth,json={'answer':'left'}).status_code==409
    r=client.post(url('/submit'),headers=auth,json={'ra':9,'rb':3,'stage':'practice'})
    assert r.status_code==200 and not r.json()['correct']
    assert r.json()['misconception']=='forgot_distributed_load'
    assert r.json()['expected']=={'ra':17,'rb':11}
    assert client.post(url('/submit'),headers=auth,json={'ra':17,'rb':11,'stage':'practice'}).status_code==409
    r=client.post(url('/explain'),headers=auth,json={'text':'Je prends le moment autour du support A, les forces doivent être en équilibre et la distance dépend de la position.'})
    assert r.status_code==200
    r=client.post('/api/challenges',headers=auth,json={'kind':'transfer','length':10,'load':20,'position':7,'udl':0})
    assert r.status_code==201
    tid=r.json()['challenge']['id']
    assert client.post('/api/challenges/'+tid+'/predict',headers=auth,json={'answer':'right'}).status_code==200
    assert client.post('/api/challenges/'+tid+'/submit',headers=auth,json={'ra':6,'rb':14,'stage':'transfer'}).json()['correct']
    profile=client.get('/api/dashboard',headers=auth).json()['profile']
    assert profile['attempt_count']==5
    assert isinstance(profile['average_mastery'],int)


def test_reading_tracking_and_ownership(client,auth):
    pdf=fitz.open();page=pdf.new_page();page.insert_text((50,50),'Equilibre des forces et moments');data=pdf.tobytes();pdf.close()
    r=client.post('/api/documents',headers=auth,files={'file':('statics.pdf',data,'application/pdf')})
    assert r.status_code==201
    did=r.json()['id']
    assert client.get('/api/documents/'+did+'/pages/0/text',headers=auth).json()['content'].startswith('Equilibre')
    assert client.get('/api/documents/'+did+'/pages/0/image',headers=auth).headers['content-type']=='image/png'
    assert client.get('/api/documents/'+did+'/pdf',headers=auth).content.startswith(b'%PDF-')
    assert client.post('/api/documents/'+did+'/events',headers=auth,json={'page':0,'activity':'view','seconds':0}).status_code==201
    assert client.post('/api/documents/'+did+'/events',headers=auth,json={'page':0,'activity':'active','seconds':22}).status_code==201
    stats=client.get('/api/documents/'+did+'/analytics',headers=auth).json()
    assert stats['pages_visited']==1 and stats['total_seconds']==22
    assert client.post('/api/documents',headers=auth,files={'file':('bad.pdf',b'not really a pdf','application/pdf')}).status_code==415
    assert client.post('/api/documents/'+did+'/events',headers=auth,json={'page':5,'activity':'active','seconds':10}).status_code==422
    other=client.post('/api/auth/demo').json()['token']
    assert client.get('/api/documents/'+did+'/pdf',headers={'Authorization':'Bearer '+other}).status_code==404


def test_coach_offline(client,auth,monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    r=client.post('/api/coach',headers=auth,json={'question':'Comment calculer le moment ?','lang':'fr'})
    assert r.status_code==200
    assert r.json()['mode']=='guided_offline'
    assert 'RB' in r.json()['answer']


def test_preferences_and_invalid_parameters(client,auth):
    assert client.put('/api/preferences',headers=auth,json={'exam_date':'2026-12-05'}).status_code==200
    assert client.post('/api/challenges',headers=auth,json={'length':3,'load':5,'position':5,'udl':0}).status_code==422
    assert client.post('/api/challenges',headers=auth,json={'kind':'transfer'}).status_code==409
