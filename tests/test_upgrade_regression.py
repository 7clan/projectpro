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
