import asyncio
import httpx
from app import providers

def test_router_recovers_from_invalid_content_and_http_error(monkeypatch):
    async def options(client):
        return [("openrouter","bad","dummy"),("gemini","invalid","dummy"),("openrouter","good","dummy")]
    async def complete(client,provider,model,key,prompt,budget):
        if model=="bad":
            req=httpx.Request("POST","https://example.invalid")
            raise httpx.HTTPStatusError("quota",request=req,response=httpx.Response(402,request=req))
        if model=="invalid": return ""
        return "correct"
    def validate(raw):
        if raw!="correct": raise ValueError("invalid response")
        return raw
    monkeypatch.setattr(providers,"candidates",options)
    monkeypatch.setattr(providers,"complete",complete)
    assert asyncio.run(providers.route("question",validate))==("correct","openrouter","good")

def test_router_returns_none_if_no_usable_provider(monkeypatch):
    async def options(client): return []
    monkeypatch.setattr(providers,"candidates",options)
    assert asyncio.run(providers.route("question",lambda s:s)) is None


def test_text_prefers_openrouter_and_review_preserves_gemini(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY","router-test")
    monkeypatch.setenv("GEMINI_API_KEY","gemini-test")
    monkeypatch.setattr(providers,"_cooldowns",{})
    calls=[]
    async def options(client):
        return [("gemini","g","gemini-test"),("openrouter","r","router-test")]
    async def complete(client,provider,model,key,prompt,budget):
        calls.append(provider)
        return "ok"
    monkeypatch.setattr(providers,"candidates",options)
    monkeypatch.setattr(providers,"complete",complete)
    assert asyncio.run(providers.route("q",lambda x:x,role="coach"))==("ok","openrouter","r")
    assert calls==["openrouter"]
    calls.clear()
    assert asyncio.run(providers.route("q",lambda x:x,role="review",exclude_model="r")) is None
    assert not calls

def test_model_cooldown_and_text_fallback(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY","router-test")
    monkeypatch.setenv("DECLIC_GEMINI_TEXT_FALLBACK","1")
    monkeypatch.setattr(providers,"_cooldowns",{})
    calls=[]
    async def options(client):return [("openrouter","r","router-test"),("gemini","g","gemini-test")]
    async def complete(client,provider,model,key,prompt,budget):
        calls.append(provider)
        if provider=="openrouter":
            req=httpx.Request("POST","https://example.invalid")
            raise httpx.HTTPStatusError("rate limit",request=req,response=httpx.Response(429,headers={"Retry-After":"120"},request=req))
        return "ok"
    monkeypatch.setattr(providers,"candidates",options)
    monkeypatch.setattr(providers,"complete",complete)
    assert asyncio.run(providers.route("q",lambda x:x))==("ok","gemini","g")
    assert asyncio.run(providers.route("q",lambda x:x))==("ok","gemini","g")
    assert calls==["openrouter","gemini","gemini"]
    monkeypatch.setenv("DECLIC_GEMINI_TEXT_FALLBACK","0")
    assert asyncio.run(providers.route("q",lambda x:x)) is None
