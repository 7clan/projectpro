import json
import shutil
import fitz
import pytest
from test_api import client,auth
from app import ocr,providers
import asyncio

def upload(client,auth,texts):
    with fitz.open() as pdf:
        for text in texts:
            p=pdf.new_page()
            p.insert_text((40,60),text,fontsize=11)
        return client.post('/api/documents',headers=auth,files={'file':('course.pdf',pdf.tobytes(),'application/pdf')}).json()

def test_quiz_source_exact_and_private(client,auth):
    from app.storage import one
    d=upload(client,auth,["Equilibrium requires the sum of all vertical forces to equal zero.","Acceleration depends on the net force and the mass of the object."])
    r=client.post('/api/quizzes',headers=auth,json={'document_id':d['id'],'count':12})
    assert r.status_code==201,r.text
    q=r.json()
    assert len(q['questions'])==2
    assert {x['page'] for x in q['questions']}=={0,1}
    assert all('answer' not in x and 'excerpt' not in x for x in q['questions'])
    saved=json.loads(one("SELECT questions FROM quizzes WHERE id=?",(q['id'],))['questions'])
    answers={x['id']:x['answer'] for x in saved}
    other={'Authorization':'Bearer '+client.post('/api/auth/demo').json()['token']}
    url='/api/quizzes/'+q['id']+'/submit'
    assert client.post(url,headers=other,json={'answers':answers}).status_code==404
    result=client.post(url,headers=auth,json={'answers':answers}).json()
    assert result['correct']==2 and result['total']==2
    assert client.post(url,headers=auth,json={'answers':answers}).status_code==409
    assert client.delete('/api/documents/'+d['id'],headers=auth).status_code==200
    assert client.post(url,headers=auth,json={'answers':answers}).status_code==404

def test_classroom_consent_and_scope(client,auth):
    student={'Authorization':'Bearer '+client.post('/api/auth/demo').json()['token']}
    outsider={'Authorization':'Bearer '+client.post('/api/auth/demo').json()['token']}
    c=client.post('/api/classrooms',headers=auth,json={'name':'Mechanics'}).json()
    url='/api/classrooms/'+c['id']+'/report'
    assert client.get(url,headers=student).status_code==404
    assert client.get(url,headers=outsider).status_code==404
    assert client.post('/api/classrooms/join',headers=student,json={'code':c['join_code']}).status_code==403
    assert client.post('/api/classrooms/join',headers=student,json={'code':c['join_code'],'consent':True}).status_code==200
    challenge=client.post('/api/challenges',headers=student,json={'kind':'practice','length':8,'load':12,'position':2,'udl':2}).json()['challenge']['id']
    assert client.post('/api/challenges/'+challenge+'/predict',headers=student,json={'answer':'left'}).status_code==200
    report=client.get(url,headers=auth).json()
    assert report['learners'][0]['attempts']==1
    assert set(report['learners'][0])=={'name','joined_at','attempts','transfer_attempts','transfer_correct'}
    assert client.delete('/api/classrooms/'+c['id'],headers=outsider).status_code==404
    assert client.delete('/api/classrooms/'+c['id']+'/membership',headers=student).status_code==200
    assert client.get(url,headers=auth).json()['learners']==[]
    assert client.delete('/api/me',headers=auth).status_code==200
    assert client.get('/api/classrooms',headers=student).json()['joined']==[]

def make_scan():
    with fitz.open() as source:
        p=source.new_page(width=600,height=220)
        p.insert_text((30,65),"Newton's second law relates force to mass.",fontsize=20)
        p.insert_text((30,110),"Acceleration equals force divided by mass.",fontsize=20)
        pix=p.get_pixmap(matrix=fitz.Matrix(2,2))
        with fitz.open() as scan:
            q=scan.new_page(width=600,height=220)
            q.insert_image(q.rect,pixmap=pix)
            return scan.tobytes()

def test_native_and_ocr_absence(client,auth,monkeypatch):
    monkeypatch.setattr(ocr.shutil,"which",lambda _:None)
    r=client.post('/api/documents',headers=auth,files={'file':('scan.pdf',make_scan(),'application/pdf')})
    assert r.status_code==201
    assert r.json()['extraction'][0]['method']=='ocr_unavailable'
    assert r.json()['indexed_pages']==0

@pytest.mark.skipif(not shutil.which("tesseract"),reason="Tesseract not installed")
def test_actual_scanned_pdf_ocr(client,auth,monkeypatch):
    monkeypatch.setenv("DECLIC_OCR_LANG","eng")
    r=client.post('/api/documents',headers=auth,files={'file':('scan.pdf',make_scan(),'application/pdf')})
    assert r.status_code==201,r.text
    assert r.json()['extraction'][0]['method']=='ocr'
    text=client.get('/api/documents/'+r.json()['id']+'/pages/0/text',headers=auth).json()
    assert text['method']=='ocr'
    assert "Acceleration" in text['content'] and "mass" in text['content']

def test_local_only_never_discovers_external_providers(monkeypatch):
    monkeypatch.setenv("DECLIC_LOCAL_ONLY","1")
    monkeypatch.setenv("DECLIC_OLLAMA_MODEL","test-local")
    monkeypatch.setenv("GEMINI_API_KEY","dummy")
    monkeypatch.setenv("OPENROUTER_API_KEY","dummy")
    monkeypatch.setenv("BAZAARLINK_API_KEY","dummy")
    assert asyncio.run(providers.candidates(None))==[("ollama","test-local","")]
    async def complete(client,provider,model,key,prompt,budget):
        assert provider=="ollama"
        return "ok"
    monkeypatch.setattr(providers,"complete",complete)
    assert asyncio.run(providers.route("q",lambda x:x))==("ok","ollama","test-local")


def test_ocr_retry_owner_only_and_preserves_indexed_text(client,auth,monkeypatch):
    # Import without OCR, then retry a single page with a controlled extractor.
    monkeypatch.setattr(ocr.shutil,"which",lambda _:None)
    r=client.post('/api/documents',headers=auth,files={'file':('scan.pdf',make_scan(),'application/pdf')})
    url='/api/documents/'+r.json()['id']+'/pages/0/ocr'
    other={'Authorization':'Bearer '+client.post('/api/auth/demo').json()['token']}
    assert client.post(url,headers=other).status_code==404
    monkeypatch.setattr(ocr,"extract_pages",lambda *a,**kw:([(0,"Recovered source text")],[(0,"ocr")]))
    result=client.post(url,headers=auth)
    assert result.status_code==200 and result.json()['content']=='Recovered source text'
    assert client.post(url,headers=auth).status_code==409
    assert client.get(url.removesuffix('/ocr')+'/text',headers=auth).json()['method']=='ocr'

def test_disconnect_cancels_pending_work():
    from app.cancellation import until_disconnect
    from fastapi import HTTPException
    cancelled=[]
    class Request:
        async def is_disconnected(self):
            await asyncio.sleep(.01)
            return True
    async def work():
        try:await asyncio.sleep(20)
        finally:cancelled.append(True)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(until_disconnect(Request(),work()))
    assert exc.value.status_code==499 and cancelled==[True]


def test_local_only_studio_without_cloud_consent(client,auth,monkeypatch):
    from app import whiteboard
    monkeypatch.setenv("DECLIC_LOCAL_ONLY","1")
    monkeypatch.setenv("DECLIC_OLLAMA_MODEL","test-local")
    async def generate(*args):return {"provider":"ollama","model":"test-local","visual_mode":"generated","mode":"live_ai"}
    monkeypatch.setattr(whiteboard,"generate",generate)
    assert client.get("/api/health").json()["ai"]["local_only"]
    r=client.post("/api/studio",headers=auth,json={"question":"Explain geometry","generative":True,"consent_external":False})
    assert r.status_code==200 and r.json()["provider"]=="ollama"

def test_local_mode_rejects_cloud_model(monkeypatch):
    monkeypatch.setenv("DECLIC_LOCAL_ONLY","1")
    monkeypatch.setenv("DECLIC_OLLAMA_MODEL","example:cloud")
    assert asyncio.run(providers.candidates(None))==[]
