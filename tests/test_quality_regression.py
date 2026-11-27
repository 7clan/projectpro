import fitz
from test_api import client,auth

def practice(client,auth):
    params={'kind':'practice','length':8,'load':12,'position':2,'udl':2}
    cid=client.post('/api/challenges',headers=auth,json=params).json()['challenge']['id']
    url='/api/challenges/'+cid
    assert client.post(url+'/predict',headers=auth,json={'answer':'left'}).status_code==200
    assert client.post(url+'/submit',headers=auth,json={'ra':17,'rb':11}).status_code==200
    return params,cid,url

def test_current_challenge_restores_only_attempted_solution(client,auth):
    assert client.get('/api/challenges/current',headers=auth).json()['challenge'] is None
    params={'kind':'practice','length':8,'load':12,'position':2,'udl':2}
    cid=client.post('/api/challenges',headers=auth,json=params).json()['challenge']['id']
    r=client.get('/api/challenges/current',headers=auth).json()
    assert r['challenge']['id']==cid and 'solution' not in r
    assert client.post('/api/challenges/'+cid+'/predict',headers=auth,json={'answer':'left'}).status_code==200
    r=client.get('/api/challenges/current',headers=auth).json()
    assert r['attempts'][0]['input']=='left' and 'solution' not in r
    assert client.post('/api/challenges/'+cid+'/submit',headers=auth,json={'ra':17,'rb':11}).status_code==200
    r=client.get('/api/challenges/current',headers=auth).json()
    assert r['expected']=={'ra':17,'rb':11} and r['solution']['ra']==17

def test_independent_transfer_gates(client,auth):
    params,cid,url=practice(client,auth)
    assert client.post('/api/challenges',headers=auth,json={'kind':'transfer'}).status_code==409
    assert client.post(url+'/explain',headers=auth,json={'text':'Somme des forces, moments autour du support et bras de levier.'}).status_code==200
    assert client.post('/api/challenges',headers=auth,json={**params,'kind':'transfer'}).status_code==409
    t=client.post('/api/challenges',headers=auth,json={'kind':'transfer','length':10,'load':20,'position':7,'udl':0})
    assert t.status_code==201
    tid=t.json()['challenge']['id']
    q={'question':'Donne les réactions numériques','challenge_id':tid,'consent_external':True}
    assert client.post('/api/studio',headers=auth,json=q).status_code==409
    assert client.post('/api/coach',headers=auth,json=q).json()['notice']=='Évaluation indépendante'
    assert 'solution' not in client.get('/api/challenges/current',headers=auth).json()
    assert client.post('/api/challenges/'+tid+'/predict',headers=auth,json={'answer':'right'}).status_code==200
    assert client.post('/api/challenges/'+tid+'/submit',headers=auth,json={'ra':6,'rb':14,'stage':'transfer'}).json()['correct']

def test_document_deletion_and_subject(client,auth):
    with fitz.open() as pdf:
        pdf.new_page()
        data=pdf.tobytes()
    d=client.post('/api/documents',headers=auth,files={'file':('lesson.pdf',data,'application/pdf')},data={'subject':'Physique'}).json()
    did=d['id']
    assert client.get('/api/documents',headers=auth).json()['documents'][0]['subject']=='Physique'
    other={'Authorization':'Bearer '+client.post('/api/auth/demo').json()['token']}
    assert client.delete('/api/documents/'+did,headers=other).status_code==404
    assert client.post('/api/documents/'+did+'/events',headers=auth,json={'activity':'view','page':0,'seconds':20}).status_code==422
    assert client.delete('/api/documents/'+did,headers=auth).status_code==200
    assert client.get('/api/documents/'+did+'/pdf',headers=auth).status_code==404
    assert client.get('/api/documents',headers=auth).json()['documents']==[]

def test_owner_account_deletion(client,auth):
    practice(client,auth)
    other={'Authorization':'Bearer '+client.post('/api/auth/demo').json()['token']}
    assert client.delete('/api/me',headers=auth).status_code==200
    assert client.get('/api/dashboard',headers=auth).status_code==401
    assert client.get('/api/dashboard',headers=other).status_code==200

def test_huge_pdf_page_bounded_raster(client,auth):
    with fitz.open() as pdf:
        pdf.new_page(width=12000,height=12000)
        data=pdf.tobytes()
    did=client.post('/api/documents',headers=auth,files={'file':('huge.pdf',data,'application/pdf')}).json()['id']
    response=client.get('/api/documents/'+did+'/pages/0/image?scale=2',headers=auth)
    assert response.status_code==200
    import struct
    w,h=struct.unpack('>II',response.content[16:24])
    assert w*h<=8_000_000 and max(w,h)<=4096

def test_blank_registration_rejected(client):
    assert client.post('/api/auth/register',json={'name':'   ','email':'user@example.org','password':'strong-password'}).status_code==422
