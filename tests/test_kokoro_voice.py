import asyncio
import io
import wave
import pytest
from app import kokoro_voice,voice
from test_api import client,auth

def test_kokoro_failure_falls_back_without_cloud(monkeypatch):
    def fail(*a):raise FileNotFoundError()
    async def piper(text,lang,cues,cloud=False):
        assert cloud is False
        return b"fallback",[],"piper-neural"
    monkeypatch.setattr(kokoro_voice,"_render",fail)
    monkeypatch.setattr(voice,"synthesize_preferred",piper)
    assert asyncio.run(kokoro_voice.synthesize_kokoro("Example","en",[0]))[2]=="piper-neural"

def test_kokoro_api_dispatch_is_local_even_with_cloud_consent(client,auth,monkeypatch):
    async def fake(text,lang,cues):
        assert lang=="en"
        return b"audio",[{"at":0,"time":0}],"kokoro-neural"
    monkeypatch.setattr(kokoro_voice,"synthesize_kokoro",fake)
    r=client.post("/api/studio/audio",headers=auth,json={"text":"Hello","lang":"en","voice_engine":"kokoro","cloud":True,"consent_external":True})
    assert r.status_code==200 and r.headers["x-studio-voice"]=="kokoro-neural"

def test_kokoro_validates_cues():
    with pytest.raises(ValueError):
        asyncio.run(kokoro_voice.synthesize_kokoro("Example","en",[1.1]))
