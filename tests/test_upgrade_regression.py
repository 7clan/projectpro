import asyncio
import io
import json
import wave
import pytest
from app.numerical_checks import validate_checks
from app.whiteboard import validate_compact,validate_lesson
from app.learning import study_plan
from app import voice,providers
from test_api import client,auth

def test_math_checks_reject_false_results():
    assert validate_checks([{"op":"divide","operands":[6,2],"result":3}])
    assert validate_checks([{"op":"pythagoras","operands":[3,4],"result":5}])
    for check in [{"op":"divide","operands":[6,2],"result":4},{"op":"divide","operands":[6,0],"result":0},{"op":"pythagoras","operands":[3,4],"result":6}]:
        with pytest.raises(ValueError):validate_checks([check])

def test_geometry_and_motion_bounds():
    data={"s":[{"h":"Triangle","e":"3²+4²=5²","n":"Observe the triangle.","o":[{"k":"right_triangle","p":[100,100,80,60]},{"k":"rect","p":[500,250,80,60],"m":"move","a":[100,90]}]} for _ in range(2)],"checks":[{"op":"pythagoras","operands":[3,4],"result":5}]}
    steps,checks=validate_lesson(json.dumps(data))
    assert steps[0]["objects"][0]["points"]==[[100,100],[180,100],[100,160]]
    assert steps[0]["objects"][1]["dx"]==20
    assert steps[0]["objects"][1]["dy"]==20
    assert checks[0]["result"]==5
    data["checks"][0]["result"]=6
    with pytest.raises(ValueError):validate_lesson(json.dumps(data))

def test_adaptive_budget_and_urgency(client,auth):
    p=client.get('/api/study-plan?minutes=45',headers=auth).json()
    assert sum(t['minutes'] for t in p['tasks'])==45
    assert all(t['minutes']>0 for t in p['tasks'])
    assert client.get('/api/study-plan?minutes=0',headers=auth).status_code==422
    for minutes in range(10,121):
        assert all(t['minutes']>0 for t in client.get('/api/study-plan?minutes='+str(minutes),headers=auth).json()['tasks'])

def test_cloud_voice_requires_explicit_consent(client,auth,monkeypatch):
    received=[]
    async def preferred(text,lang,cues,cloud=False):
        received.append(cloud)
        return b'RIFF',[],'test'
    monkeypatch.setattr(voice,'synthesize_preferred',preferred)
    for consent in [False,True]:
        r=client.post('/api/studio/audio',headers=auth,json={'text':'Bonjour','cloud':True,'consent_external':consent})
        assert r.status_code==200
    assert received==[False,True]

def test_voice_falls_back_when_cloud_fails(monkeypatch):
    async def fail(*args):raise RuntimeError("quota")
    monkeypatch.setattr(voice,'_gemini_render',fail)
    monkeypatch.setattr(voice,'_neural_render',lambda *a:(b'local',[{"at":0,"time":0}]))
    result=asyncio.run(voice.synthesize_preferred("Bonjour le monde","fr",[0],cloud=True))
    assert result[2]=='piper-neural'

def test_router_deadline_returns_safe_fallback(monkeypatch):
    async def fail(*args):raise asyncio.TimeoutError
    monkeypatch.setattr(providers,'_route',fail)
    assert asyncio.run(providers.route("test",lambda x:x)) is None


def test_unrelated_offline_question_has_no_fake_beam_lesson(client,auth):
    r=client.post('/api/studio',headers=auth,json={'question':'Explain the Pythagorean theorem','lang':'en','generative':True})
    assert r.status_code==200
    data=r.json()
    assert data['mode']=='guided_offline'
    assert data['steps'][0]['scene']=='unavailable'


def test_visible_equations_are_checked_independently():
    from app.numerical_checks import verify_formula
    assert verify_formula("3² + 4² = 5²")
    assert verify_formula("6 ÷ 2 = 3")
    assert verify_formula("9 + 16 = 25 = 5²")
    assert verify_formula("F = ma") is None
    with pytest.raises(ValueError):verify_formula("6 / 2 = 4")
    with pytest.raises(ValueError):verify_formula("3² + 4² = 6²")

def test_fit_scene_preserves_geometry():
    from app.whiteboard import fit_scene
    points=[[-20,0],[100,0],[-20,90]]
    objects=[{"kind":"polygon","points":points}]
    fit_scene(objects)
    a,b,c=objects[0]["points"]
    assert 10<=a[0]<=590 and 10<=a[1]<=320
    assert a[1]==b[1] and a[0]==c[0]
    assert abs((b[0]-a[0])/(c[1]-a[1])-4/3)<.0001


def test_pythagorean_construction_has_outward_squares_and_exact_areas():
    from app.whiteboard import pythagoras_objects
    style={"at":0,"color":"ink","motion":"draw","duration":1,"width":2,"fill":0}
    for a,b in [(4,3),(4,-3),(-4,3),(-4,-3)]:
        objs=pythagoras_objects([280,160,a,b,20],style)
        tri=objs[-1]["points"]
        assert sorted(float(o["text"]) for o in objs if o["kind"]=="text")==[9,16,25]
        for i,square in enumerate(objs[::2][:3]):
            p,q,r,t=square["points"];opp=tri[(i+2)%3]
            assert p==tri[i] and q==tri[(i+1)%3]
            def cross(u,v,w):return (v[0]-u[0])*(w[1]-u[1])-(v[1]-u[1])*(w[0]-u[0])
            assert cross(p,q,opp)*cross(p,q,r)<0
            edges=[(v[0]-u[0],v[1]-u[1]) for u,v in zip([p,q,r,t],[q,r,t,p])]
            assert max(x*x+y*y for x,y in edges)-min(x*x+y*y for x,y in edges)<1e-6
            assert abs(edges[0][0]*edges[1][0]+edges[0][1]*edges[1][1])<1e-6
            assert all(10<=x<=590 and 10<=y<=320 for x,y in square["points"])


def test_rate_limit_cooldown_avoids_repeated_cloud_requests(monkeypatch):
    calls=[]
    monkeypatch.setattr(voice,"_cloud_retry_at",0)
    async def limited(*args):
        calls.append(1)
        raise voice.CloudRateLimited(60)
    monkeypatch.setattr(voice,"_gemini_render",limited)
    monkeypatch.setattr(voice,"_neural_render",lambda *a:(b"local",[{"at":0,"time":0}]))
    async def run():
        assert (await voice.synthesize_preferred("Bonjour", "fr",[0],cloud=True))[2]=="piper-neural"
        assert (await voice.synthesize_preferred("Autre question", "fr",[0],cloud=True))[2]=="piper-neural"
    asyncio.run(run())
    assert len(calls)==1

def test_named_equations_and_newton_labels():
    from app.numerical_checks import verify_formula,verify_newton_labels
    assert verify_formula("a = 6 / 2 = 3 m/s²")
    assert verify_formula("x = 1,5 + 2,5 = 4")
    with pytest.raises(ValueError):verify_formula("a = 6 / 2 = 4 m/s²")
    with pytest.raises(ValueError):verify_formula("6 / 0 = 1")
    scene={"formula":"F = m × a","objects":[{"kind":"text","text":t} for t in ["F = 6 N","m = 2 kg","a = 3 m/s²"]]}
    assert verify_newton_labels([scene],"Deuxième loi de Newton")
    scene["objects"][2]["text"]="a = 4 m/s²"
    with pytest.raises(ValueError):verify_newton_labels([scene],"Deuxième loi de Newton")
    assert not verify_newton_labels([scene],"Autre sujet")
