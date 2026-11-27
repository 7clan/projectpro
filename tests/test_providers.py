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
