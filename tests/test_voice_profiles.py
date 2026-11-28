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


def test_kokoro_is_explicit_and_english_only(monkeypatch):
    calls=[]
    def render(text,lang,cues,voice_name):
        calls.append(voice_name)
        return b"audio",[{"at":0,"time":0}]
    monkeypatch.setattr(voice,"_kokoro_render",render)
    _,_,backend=asyncio.run(voice.synthesize_preferred("Hello","en",[0],cloud=True,voice_name="kokoro-michael"))
    assert backend=="kokoro-michael" and calls==["kokoro-michael"]
    with pytest.raises(ValueError):
        asyncio.run(voice.synthesize_preferred("Bonjour","fr",[0],voice_name="kokoro-michael"))


def test_soft_pause_cleanup_preserves_words_length_and_timing():
    np=pytest.importorskip("numpy")
    rate=24000
    speech=(.1*np.sin(2*np.pi*220*np.arange(rate//2)/rate)).astype(np.float32)
    gap=np.full(rate//2,.0008,dtype=np.float32)
    x=np.concatenate([speech,gap,speech])
    y=voice._soften_kokoro_pauses(x,rate)
    assert len(y)==len(x)
    assert np.array_equal(y[:rate//2],speech)
    assert np.array_equal(y[rate:],speech)
    assert np.max(np.abs(y[rate*7//10:rate*8//10]))<.00013
    assert np.isfinite(y).all()
    assert np.array_equal(voice._soften_kokoro_pauses(speech,rate),speech)


def test_pocket_explicit_local_selection(monkeypatch):
    monkeypatch.setattr(voice,"_pocket_render",lambda *a:(b"audio",[{"at":0,"time":0}]))
    assert asyncio.run(voice.synthesize_preferred("Hello","en",[0],cloud=True,voice_name="pocket-alba"))[2]=="pocket-alba"
    with pytest.raises(ValueError):
        asyncio.run(voice.synthesize_preferred("Bonjour","fr",[0],voice_name="pocket-alba"))
    for rejected in ("kokoro-bella","kokoro-heart","kokoro-bella-smooth"):
        with pytest.raises(ValueError):
            asyncio.run(voice.synthesize_preferred("Hello","en",[0],voice_name=rejected))


@pytest.mark.parametrize("lang,expected", [("en","pocket-george"),("fr","piper-fr_FR-tom-medium")])
def test_cloud_failure_uses_language_specific_voice(monkeypatch,lang,expected):
    monkeypatch.delenv("DECLIC_LOCAL_ONLY",raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY","test-key-not-used")
    monkeypatch.setattr(voice,"_cloud_retry_at",0)
    monkeypatch.setattr(voice,"_router_voice_retry_at",0)
    calls=[]
    async def router(*args):
        calls.append("heygen")
        raise voice.CloudRateLimited(60)
    async def gemini(*args):
        calls.append("gemini")
        raise voice.CloudRateLimited(60)
    monkeypatch.setattr(voice,"_openrouter_render",router)
    monkeypatch.setattr(voice,"_gemini_render",gemini)
    monkeypatch.setattr(voice,"_pocket_executable",lambda:"installed")
    monkeypatch.setattr(voice,"_piper_installed",lambda name:True)
    def render(text,language,cues,name=None):
        calls.append(name)
        assert language==lang
        return b"audio",[{"at":0,"time":0}]
    monkeypatch.setattr(voice,"_pocket_render",render)
    monkeypatch.setattr(voice,"_neural_render",render)
    assert asyncio.run(voice.synthesize_preferred("Hello" if lang=="en" else "Bonjour",lang,[0],cloud=True))[2]==expected
    assert calls==["heygen","gemini","pocket-george" if lang=="en" else "fr_FR-tom-medium"]
    calls.clear()
    assert asyncio.run(voice.synthesize_preferred("Hello",lang,[0],cloud=False))[2]==expected
    assert len(calls)==1

def test_missing_or_broken_george_falls_back_to_existing_piper(monkeypatch):
    monkeypatch.setattr(voice,"_pocket_executable",lambda:"installed")
    monkeypatch.setattr(voice,"_kokoro_available",lambda:False)
    def broken(*args):raise FileNotFoundError("unavailable")
    monkeypatch.setattr(voice,"_pocket_render",broken)
    monkeypatch.setattr(voice,"_neural_render",lambda *args:(b"audio",[]))
    assert asyncio.run(voice.synthesize_preferred("Hello","en",[0]))[2]=="piper-neural"
