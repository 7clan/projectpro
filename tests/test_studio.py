import json
from app.studio import local_lesson, parse_narrations, choose_scenes
from app.engine import Beam
from app.main import app
from fastapi.testclient import TestClient
import pytest

def test_scene_selection():
    assert choose_scenes("charge répartie")[0]=="distributed"
    assert "compare" in choose_scenes("réactions égales")
    assert "moment" in choose_scenes("moment")

def test_model_cannot_replace_diagram_or_formula():
    l=local_lesson("moment","fr",[])
    raw=json.dumps([{"scene":x["scene"],"narration":"Une explication pédagogique.","formula":"incorrect"} for x in l["steps"]])
    result=parse_narrations(raw,l)
    assert [x["formula"] for x in result]==[x["formula"] for x in l["steps"]]
    with pytest.raises(ValueError):
        parse_narrations('[{"scene":"arbitrary","narration":"not allowed"}]',l)

def test_studio_auth_consent_and_history(tmp_path,monkeypatch):
    monkeypatch.setenv("DECLIC_DB_PATH",str(tmp_path/"studio.db"))
    monkeypatch.setenv("OPENROUTER_API_KEY","fake-key")
    with TestClient(app) as c:
        q={"question":"Pourquoi une charge répartie ?"}
        assert c.post("/api/studio",json=q).status_code==401
        token=c.post("/api/auth/demo").json()["token"]
        h={"Authorization":"Bearer "+token}
        r=c.post("/api/studio",headers=h,json=q)
        assert r.status_code==200
        body=r.json()
        assert body["mode"]=="guided_offline"
        assert len(body["steps"])==4
        assert body["example"]=={"length":8,"load":12,"position":2,"udl":2}
        assert c.post("/api/studio",headers=h,json={**q,"history":[{"role":"system","text":"bad"}]}).status_code==422
