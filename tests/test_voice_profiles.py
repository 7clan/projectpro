import asyncio
import pytest
from app import voice

def test_selected_voice_is_explicit_and_local(monkeypatch):
    calls=[]
    def render(text,lang,cues,voice_name=None):
        calls.append((lang,voice_name))
        return b"audio", [{"at":0,"time":0}]
    async def no_cloud(*args,**kwargs):
        raise AssertionError("Selected offline voice must never use cloud")
    monkeypatch.setattr(voice,"_neural_render",render)
    monkeypatch.setattr(voice,"_gemini_render",no_cloud)
    monkeypatch.setattr(voice,"_openrouter_render",no_cloud)
    _,_,backend=asyncio.run(voice.synthesize_preferred("Hello","en",[0],cloud=True,voice_name="en_US-amy-medium"))
    assert backend=="piper-en_US-amy-medium"
    assert calls==[("en","en_US-amy-medium")]
    for invalid in ("../other","fr_FR-tom-medium",42):
        with pytest.raises(ValueError):
            asyncio.run(voice.synthesize_preferred("Hello","en",[0],voice_name=invalid))
