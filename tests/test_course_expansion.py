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


def test_concept_quizzes_and_teacher_assignment_workflow(client,auth,monkeypatch):
    from app.storage import one
    student={"Authorization":"Bearer "+client.post("/api/auth/demo").json()["token"]}
    stranger={"Authorization":"Bearer "+client.post("/api/auth/demo").json()["token"]}
    quiz=client.post("/api/quizzes",headers=student,json={"kind":"conceptual","count":8,"difficulty":"hard","lang":"en"})
    assert quiz.status_code==201,quiz.text
    data=quiz.json()
    assert len(data["questions"])==8
    assert all(len(set(q["options"]))==4 and "answer" not in q and q["difficulty"]=="hard" for q in data["questions"])
    qs=json.loads(one("SELECT questions FROM quizzes WHERE id=?",(data["id"],))["questions"])
    assert client.post("/api/quizzes/"+data["id"]+"/submit",headers=student,json={"answers":{q["id"]:q["answer"] for q in qs}}).json()["correct"]==8
    c=client.post("/api/classrooms",headers=auth,json={"name":"Statics"}).json()
    base="/api/classrooms/"+c["id"]
    assert client.post("/api/classrooms/join",headers=student,json={"code":c["join_code"],"consent":True}).status_code==200
    monkeypatch.setenv("DECLIC_REQUIRE_APPROVED_TEACHER","1")
    assert client.post(base+"/assignments",headers=auth,json={"title":"Practice"}).status_code==403
    uid=client.get("/api/me",headers=auth).json()["id"]
    monkeypatch.setenv("DECLIC_APPROVED_TEACHER_IDS",uid)
    assert client.get("/api/teacher/status",headers=auth).json()["operator_approved"]
    a=client.post(base+"/assignments",headers=auth,json={"title":"Practice","count":4,"difficulty":"hard"})
    assert a.status_code==201,a.text
    url=base+"/assignments/"+a.json()["id"]
    assert client.get(url,headers=stranger).status_code==404
    assert client.get(url+"/report",headers=student).status_code==404
    q=client.get(url,headers=student).json()["questions"]
    assert all("answer" not in x for x in q)
    saved=json.loads(one("SELECT questions FROM class_assignments WHERE id=?",(a.json()["id"],))["questions"])
    payload={"answers":{x["id"]:x["answer"] for x in saved}}
    assert client.post(url+"/submit",headers=student,json=payload).json()["correct"]==4
    assert client.post(url+"/submit",headers=student,json=payload).status_code==409
    assert client.get(url+"/report",headers=auth).json()["submissions"][0]["correct"]==4
    assert client.delete(base+"/membership",headers=student).status_code==200
    assert client.get(url+"/report",headers=auth).json()["submissions"]==[]

def test_local_semantic_scene_compilation():
    from app.local_board import compile_plan
    scenes=[{"title":"Triangle","speech":"Trois au carré plus quatre au carré égale vingt-cinq.","formula":"9 + 16 = 25","diagram":"triangle","a":3,"b":4,"label1":"a","label2":"b","label3":"c"},{"title":"Force","speech":"Une force de six newtons sur deux kilogrammes donne trois mètres par seconde carrée.","formula":"6 / 2 = 3","diagram":"force","a":2,"b":6,"label1":"m","label2":"F","label3":"a"}]
    steps,checks=compile_plan(json.dumps({"scenes":scenes}))
    assert len(steps)==2 and len(checks)>=4
    assert any(o.get("text")=="a = 3 m/s²" for o in steps[1]["objects"])
    scenes[1]["formula"]="6 / 2 = 4"
    with pytest.raises(ValueError):compile_plan(json.dumps({"scenes":scenes}))

def test_exact_shear_jump():
    from app.engine import Beam
    b=Beam(8,12,2.3,2)
    plot=b.overview()
    indexes=[i for i,x in enumerate(plot["x"]) if x==2.3]
    assert len(indexes)==2
    a,c=indexes
    assert abs(plot["shear"][a]-plot["shear"][c]-12)<1e-6
    assert plot["moment"][a]==plot["moment"][c]
    assert plot["max_moment"] in plot["moment"]

def test_pilot_security_headers_and_limits(client,monkeypatch):
    monkeypatch.setenv("DECLIC_PILOT_LIMITS","1")
    r=client.get("/api/health")
    assert r.headers["x-frame-options"]=="DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"]=="no-store"
    for i in range(12):
        assert client.post("/api/auth/demo").status_code==200
    assert client.post("/api/auth/demo").status_code==429

@pytest.mark.skipif(not shutil.which("tesseract"),reason="Tesseract not installed")
def test_mixed_scan_with_native_header(client,auth,monkeypatch):
    monkeypatch.setenv("DECLIC_OCR_LANG","eng")
    with fitz.open(stream=make_scan(),filetype="pdf") as pdf:
        p=pdf[0];p.insert_text((30,190),"Page 1",fontsize=10)
        raw=pdf.tobytes()
    r=client.post("/api/documents",headers=auth,files={"file":("mixed.pdf",raw,"application/pdf")})
    assert r.status_code==201,r.text
    assert r.json()["extraction"][0]["method"]=="mixed_ocr"
    content=client.get("/api/documents/"+r.json()["id"]+"/pages/0/text",headers=auth).json()["content"]
    assert "Page 1" in content and "Acceleration" in content


def test_independent_subject_relationships_and_review():
    from app.numerical_checks import verify_subject_labels
    from app.reviewer import review
    scene={"formula":"U = R × I","objects":[{"kind":"text","text":x} for x in ["U = 12 V","R = 6 Ω","I = 2 A"]]}
    assert verify_subject_labels([scene],"Loi d'Ohm")
    scene["objects"][2]["text"]="I = 3 A"
    with pytest.raises(ValueError):verify_subject_labels([scene],"Loi d'Ohm")
    result=asyncio.run(review("Loi d'Ohm",[scene],"author-model"))
    assert result["verdict"]=="revise" and result["provider"]=="deterministic"


def test_local_diagram_must_match_question():
    from app.local_board import compile_plan,schema_for,requested_diagram
    q="Montre la deuxième loi de Newton pour une masse de 2 kg et une force de 6 N."
    assert requested_diagram(q)==("force",{"a":2.0,"b":6.0})
    props=schema_for(q)["properties"]["scenes"]["items"]["properties"]
    assert props["diagram"]["enum"]==["force"] and props["a"]["enum"]==[2.0]
    scene={"title":"Newton","speech":"La force agit sur une masse.","formula":"F = m × a","diagram":"triangle","a":2,"b":6,"label1":"a","label2":"b","label3":"c"}
    with pytest.raises(ValueError):compile_plan(json.dumps({"scenes":[scene,scene]}),q)
    scene["diagram"]="force"
    steps,checks=compile_plan(json.dumps({"scenes":[scene,scene]}),q)
    assert any(o.get("text")=="a = 3 m/s²" for o in steps[1]["objects"])
    assert "3 mètres" in steps[1]["narration"]
    scene["a"]=4
    with pytest.raises(ValueError):compile_plan(json.dumps({"scenes":[scene,scene]}),q)


def test_mode_selection_isolated_and_consent_safe(monkeypatch):
    from app.providers import use_mode,mode,candidates,configured_modes
    monkeypatch.delenv("DECLIC_LOCAL_ONLY",raising=False)
    monkeypatch.setenv("DECLIC_OLLAMA_MODEL","local-model")
    monkeypatch.setenv("BAZAARLINK_API_KEY","test-key")
    assert configured_modes()=={"cloud":True,"local":True,"hybrid":True}
    async def worker(selected,consent,expected):
        with use_mode(selected,consent):
            await asyncio.sleep(.01)
            assert mode()==expected
            if expected=="local":
                assert await candidates(None)==[("ollama","local-model","")]
            elif expected=="disabled":
                assert await candidates(None)==[]
    async def run():
        await asyncio.gather(worker("local",True,"local"),worker("cloud",False,"disabled"),worker("hybrid",False,"local"))
    asyncio.run(run())
    assert mode()=="hybrid"
    with use_mode("cloud",True):
        assert mode()=="cloud"
    monkeypatch.setenv("DECLIC_LOCAL_ONLY","1")
    with use_mode("cloud",True):
        assert mode()=="local"

def test_course_ai_grounding_and_privacy(client,auth,monkeypatch):
    from app import course_ai
    from app.providers import mode
    from app.storage import one
    text="Mitochondria produce ATP through oxidative phosphorylation. This process supplies energy to many cells."
    d=upload(client,auth,[text])
    # A response without explicit cloud consent must never invoke the generator.
    monkeypatch.delenv("DECLIC_LOCAL_ONLY",raising=False)
    monkeypatch.setenv("DECLIC_OLLAMA_MODEL","local-test")
    calls=[]
    async def fake(pages,count,difficulty,lang):
        calls.append(mode())
        raw=json.dumps({"questions":[{"prompt":"Which process produces ATP in mitochondria?","options":["oxidative phosphorylation","osmosis","diffusion","transcription"],"answer":"oxidative phosphorylation","source":"1","evidence":"Mitochondria produce ATP through oxidative phosphorylation."}]})
        return course_ai.validate_questions(raw,course_ai.excerpts(pages),count),{"provider":"ollama","review":"unavailable"}
    monkeypatch.setattr(course_ai,"generate",fake)
    body={"kind":"course_ai","document_id":d["id"],"count":1,"lang":"en","ai_mode":"cloud"}
    assert client.post("/api/quizzes",headers=auth,json=body).status_code==403
    assert calls==[]
    body["ai_mode"]="local"
    r=client.post("/api/quizzes",headers=auth,json=body)
    assert r.status_code==201,r.text
    assert calls==["local"]
    q=r.json()["questions"][0]
    assert "answer" not in q and "excerpt" not in q and len(q["options"])==4
    url="/api/quizzes/"+r.json()["id"]+"/submit"
    assert client.post(url,headers=auth,json={"answers":{q["id"]:"invented answer"}}).status_code==422
    result=client.post(url,headers=auth,json={"answers":{q["id"]:"oxidative phosphorylation"}}).json()
    assert result["correct"]==1
    assert result["results"][0]["excerpt"] in text

def test_ai_quiz_rejects_fabricated_evidence_and_duplicate_choices():
    from app.course_ai import validate_questions,excerpts
    sources=excerpts([{"document_id":"test","title":"Biology","page":0,"content":"Mitochondria produce ATP through oxidative phosphorylation. This process supplies energy to many cells."}])
    question={"prompt":"Which process produces ATP in mitochondria?","options":["oxidative phosphorylation","osmosis","diffusion","transcription"],"answer":"oxidative phosphorylation","source":"1","evidence":"Mitochondria produce ATP through oxidative phosphorylation."}
    def raw():return json.dumps({"questions":[question]})
    assert len(validate_questions(raw(),sources,1))==1
    question["evidence"]="Mitochondria use oxidative phosphorylation to produce glucose."
    with pytest.raises(ValueError):validate_questions(raw(),sources,1)
    question["evidence"]="Mitochondria produce ATP through oxidative phosphorylation."
    question["options"][1]=question["options"][0]
    with pytest.raises(ValueError):validate_questions(raw(),sources,1)


def test_streaming_speech_auth_and_pcm_bounds(client,auth,monkeypatch):
    from app import speech_stream as speech
    from starlette.websockets import WebSocketDisconnect
    monkeypatch.setattr(speech,"available",lambda lang:True)
    monkeypatch.setattr(speech,"recognizer",lambda lang:object())
    monkeypatch.setattr(speech,"accept",lambda rec,data:{"type":"partial","text":"bonjour"})
    monkeypatch.setattr(speech,"finish",lambda rec:{"type":"final","text":"bonjour le monde"})
    url="/api/studio/listen";headers={"origin":"http://testserver"}
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(url,headers={"origin":"https://untrusted.invalid"}):pass
    with client.websocket_connect(url,headers=headers) as ws:
        ws.send_json({"token":"invalid","lang":"fr"})
        with pytest.raises(WebSocketDisconnect):ws.receive_json()
    token=auth["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(url,headers=headers) as ws:
        ws.send_json({"token":token,"lang":"fr"})
        assert ws.receive_json()["backend"]=="vosk-local"
        ws.send_bytes(b"\x00\x00"*3200)
        assert ws.receive_json()=={"type":"partial","text":"bonjour"}
        ws.send_text("end")
        assert ws.receive_json()=={"type":"final","text":"bonjour le monde"}
    with client.websocket_connect(url,headers=headers) as ws:
        ws.send_json({"token":token,"lang":"fr"})
        assert ws.receive_json()["type"]=="ready"
        ws.send_bytes(b"\x00")
        with pytest.raises(WebSocketDisconnect):ws.receive_json()


def test_selected_sentence_uses_indexed_quote_not_model_quote():
    from app.course_ai import short_sources,validate_selected
    content="Mitochondria produce ATP through oxidative phosphorylation. ATP provides energy for cellular processes."
    sources=short_sources([{"document_id":"bio","title":"Biology","page":3,"content":content}])
    q={"prompt":"Which process produces ATP in mitochondria?","options":["oxidative phosphorylation","osmosis","diffusion","transcription"],"answer":"oxidative phosphorylation","source":"1","evidence":"invented quotation"}
    def raw():return json.dumps({"questions":[q]})
    result=validate_selected(raw(),sources,1)[0]
    assert result["excerpt"]=="Mitochondria produce ATP through oxidative phosphorylation."
    assert result["page"]==3
    q["source"]="2"
    with pytest.raises(ValueError):validate_selected(raw(),sources,1)


def test_ollama_cloud_uses_desktop_connection_and_never_leaks_into_offline(monkeypatch):
    from app.providers import candidates,complete,use_mode,configured_modes,route
    from app.ai import ai_status
    import httpx
    monkeypatch.delenv("DECLIC_LOCAL_ONLY",raising=False)
    monkeypatch.setenv("DECLIC_OLLAMA_MODEL","qwen2.5-coder:3b")
    monkeypatch.setenv("DECLIC_OLLAMA_CLOUD_MODEL","nemotron-3-super:cloud")
    assert configured_modes()["ollama_cloud"]
    async def check():
        with use_mode("ollama_cloud",False):
            assert await candidates(None)==[]
            assert not ai_status()["enabled"]
        with use_mode("local",True):
            assert await candidates(None)==[("ollama","qwen2.5-coder:3b","")]
        with use_mode("ollama_cloud",True):
            assert await candidates(None)==[("ollama_cloud","nemotron-3-super:cloud","")]
            assert ai_status()["provider"]=="ollama_cloud"
            def handler(req):
                assert str(req.url)=="http://127.0.0.1:11434/api/chat"
                assert "Authorization" not in req.headers
                body=json.loads(req.content)
                assert body["model"]=="nemotron-3-super:cloud"
                assert "format" not in body and body["stream"] is False
                return httpx.Response(200,json={"message":{"content":'{"answer":25}'}})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                assert json.loads(await complete(client,"ollama_cloud","nemotron-3-super:cloud","","test"))["answer"]==25
        monkeypatch.setenv("DECLIC_LOCAL_ONLY","1")
        with use_mode("ollama_cloud",True):
            assert await candidates(None)==[("ollama","qwen2.5-coder:3b","")]
            assert not configured_modes()["ollama_cloud"]
    asyncio.run(check())

def test_ollama_cloud_route_is_explicit_and_does_not_fall_back(monkeypatch):
    from app import providers
    monkeypatch.delenv("DECLIC_LOCAL_ONLY",raising=False)
    monkeypatch.setenv("DECLIC_OLLAMA_CLOUD_MODEL","glm-5.3-flash:cloud")
    monkeypatch.setenv("DECLIC_OLLAMA_MODEL","local-model")
    monkeypatch.setenv("GEMINI_API_KEY","test-key")
    called=[]
    async def fake_complete(client,provider,model,key,prompt,budget):
        called.append((provider,model))
        return '{"answer":25}'
    monkeypatch.setattr(providers,"complete",fake_complete)
    async def run():
        with providers.use_mode("ollama_cloud",True):
            result=await providers.route("test",json.loads)
        assert result[1:] == ("ollama_cloud","glm-5.3-flash:cloud")
        assert called==[("ollama_cloud","glm-5.3-flash:cloud")]
    asyncio.run(run())


def test_local_pythagoras_complete_narration_and_progressive_reveal():
    from app.local_board import compile_plan
    scene={"title":"Triangle","speech":"Now look at the squares formed on each side of the","formula":"a² + b² = c²","diagram":"triangle","a":3,"b":4,"label1":"a","label2":"b","label3":"c"}
    steps,checks=compile_plan(json.dumps({"scenes":[scene,scene]}),"Explain Pythagoras using a triangle with sides 3, 4, 5.","en")
    assert all(step["narration"].endswith(".") for step in steps)
    assert "side of the" not in steps[1]["narration"]
    assert "9 plus 16 equals 25" in steps[1]["narration"]
    assert "5 units long" in steps[1]["narration"]
    assert len(steps[0]["objects"])<len(steps[1]["objects"])
    assert {"9","16","25"} <= {o["text"] for o in steps[1]["objects"] if o["kind"]=="text"}


def test_cloud_pythagoras_rejects_pixel_units_and_renders_actual_areas(monkeypatch):
    from app import whiteboard,providers
    from app.local_board import requested_diagram
    question="Explain the Pythagorean theorem using an animated right triangle with sides 3, 4 and 5. Show the relationship between the three square areas."
    assert requested_diagram(question)==("triangle",{"a":3.0,"b":4.0})
    assert requested_diagram("Pythagore avec les côtés 3, 4 et 5")==("triangle",{"a":3.0,"b":4.0})
    scene={"title":"Triangle","speech":"Observe the triangle.","formula":"—","diagram":"triangle","a":60,"b":80,"label1":"a","label2":"b","label3":"c"}
    async def fake_route(prompt,validator,budget=3000,**kwargs):
        with pytest.raises(ValueError):
            validator(json.dumps({"scenes":[scene,scene]}))
        scene["a"],scene["b"]=3,4
        return validator(json.dumps({"scenes":[scene,scene]})),"openrouter","test"
    monkeypatch.delenv("DECLIC_LOCAL_ONLY",raising=False)
    monkeypatch.setattr(providers,"route",fake_route)
    with providers.use_mode("cloud",True):
        result=asyncio.run(whiteboard.generate(question,"en",[],[]))
    assert result["provider"]=="openrouter"
    labels={o["text"] for o in result["steps"][-1]["objects"] if o["kind"]=="text"}
    assert labels=={"9","16","25"}
    assert result["steps"][-1]["formula"]=="9 + 16 = 25"
    assert "checked mathematical rendering" in result["notice"]
