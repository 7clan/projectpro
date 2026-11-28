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


def test_bazaarlink_free_only_request(monkeypatch):
    calls=[]
    class Client:
        async def post(self,url,headers,json):
            calls.append((url,headers,json))
            return httpx.Response(200,json={"choices":[{"message":{"content":"ok"}}]},request=httpx.Request("POST",url))
    result=asyncio.run(providers.complete(Client(),"bazaarlink","qwen/qwen3.7-flash","test-key","test",500))
    assert result=="ok"
    assert calls[0][0]=="https://api.bazaarlink.ai/v1/chat/completions"
    assert calls[0][1]["X-Free-Fallback"]=="false"
    assert calls[0][1]["Authorization"]=="Bearer test-key"

def test_three_provider_roles_and_shared_bazaar_quota(monkeypatch):
    monkeypatch.setenv("BAZAARLINK_API_KEY","bazaar-test")
    monkeypatch.setenv("OPENROUTER_API_KEY","router-test")
    monkeypatch.setattr(providers,"_cooldowns",{})
    calls=[]
    async def options(client):
        return [("bazaarlink","qwen","b"),("bazaarlink","deepseek","b"),("openrouter","gemma","r"),("gemini","g","g")]
    async def complete(client,provider,model,key,prompt,budget):
        calls.append((provider,model))
        return "ok"
    monkeypatch.setattr(providers,"candidates",options)
    monkeypatch.setattr(providers,"complete",complete)
    assert asyncio.run(providers.route("q",lambda x:x,role="lesson"))==("ok","openrouter","gemma")
    assert asyncio.run(providers.route("q",lambda x:x,role="coach"))==("ok","openrouter","gemma")
    assert asyncio.run(providers.route("q",lambda x:x,role="review",exclude_model="gemma"))==("ok","bazaarlink","qwen")
    providers._limit("openrouter","gemma",httpx.Response(429,headers={"Retry-After":"60"}))
    assert asyncio.run(providers.route("q",lambda x:x,role="lesson"))==("ok","bazaarlink","qwen")
    providers._limit("bazaarlink","qwen",httpx.Response(429,headers={"Retry-After":"60"}))
    assert not providers._ready("bazaarlink","deepseek")
    providers._cooldowns.pop(("openrouter","gemma"))
    assert asyncio.run(providers.route("q",lambda x:x,role="lesson"))==("ok","openrouter","gemma")
    assert all(p!="gemini" for p,m in calls)


def test_same_provider_quota_failover_and_recovery(monkeypatch):
    monkeypatch.setattr(providers,"_cooldowns",{})
    monkeypatch.setenv("DECLIC_GEMINI_TEXT_FALLBACK","1")
    clock=[100.]
    monkeypatch.setattr(providers,"time",type("Clock",(),{"monotonic":staticmethod(lambda:clock[0]),"time":staticmethod(providers.time.time)}))
    calls=[]
    async def options(client):
        return [("openrouter","first","r"),("openrouter","second","r"),
                ("openrouter","third","r"),("bazaarlink","qwen","b")]
    async def complete(client,provider,model,key,prompt,budget):
        calls.append((provider,model,key,prompt))
        if model=="first" and clock[0]<160:
            req=httpx.Request("POST","https://example.invalid")
            raise httpx.HTTPStatusError("quota",request=req,response=httpx.Response(
                429,request=req,headers={"Retry-After":"60"},
                json={"error":{"metadata":{"limit_source":"upstream_provider_shared_pool"}}}))
        if model=="second":return ""
        return "valid"
    monkeypatch.setattr(providers,"candidates",options)
    monkeypatch.setattr(providers,"complete",complete)
    assert asyncio.run(providers.route("lesson",lambda x:x))==("valid","openrouter","third")
    assert [c[1] for c in calls]==["first","second","third"]
    assert all(c[2:]==("r","lesson") for c in calls)
    calls.clear()
    assert asyncio.run(providers.route("lesson",lambda x:x))==("valid","openrouter","third")
    assert [c[1] for c in calls]==["second","third"]
    clock[0]=161
    calls.clear()
    assert asyncio.run(providers.route("lesson",lambda x:x))==("valid","openrouter","first")


def test_shared_openrouter_quota_skips_remaining_models(monkeypatch):
    monkeypatch.setattr(providers,"_cooldowns",{})
    calls=[]
    async def options(client):
        return [("openrouter","a","r"),("openrouter","b","r"),("bazaarlink","qwen","b")]
    async def complete(client,provider,model,key,prompt,budget):
        calls.append(model)
        if provider=="openrouter":
            req=httpx.Request("POST","https://example.invalid")
            raise httpx.HTTPStatusError("quota",request=req,response=httpx.Response(
                429,request=req,json={"error":{"metadata":{"limit_source":"openrouter_free_tier_daily"}}}))
        return "ok"
    monkeypatch.setattr(providers,"candidates",options)
    monkeypatch.setattr(providers,"complete",complete)
    assert asyncio.run(providers.route("q",lambda x:x))==("ok","bazaarlink","qwen")
    assert calls==["a","qwen"]
    assert not providers._ready("openrouter","b")
    assert providers._ready("bazaarlink","qwen")


def test_bazaarlink_model_quota_moves_to_next_model_before_gemini(monkeypatch):
    monkeypatch.setattr(providers,"_cooldowns",{})
    monkeypatch.setenv("DECLIC_GEMINI_TEXT_FALLBACK","1")
    calls=[]
    async def options(client):
        return [("bazaarlink","qwen","b"),("bazaarlink","deepseek","b"),
                ("bazaarlink","nemotron","b"),("gemini","flash","g")]
    async def complete(client,provider,model,key,prompt,budget):
        calls.append(model)
        if model=="qwen":
            req=httpx.Request("POST","https://example.invalid")
            raise httpx.HTTPStatusError("quota",request=req,response=httpx.Response(
                429,request=req,json={"error":{"code":"free_quota_exhausted"}}))
        if model=="deepseek":
            return ""
        return "ok"
    monkeypatch.setattr(providers,"candidates",options)
    monkeypatch.setattr(providers,"complete",complete)
    assert asyncio.run(providers.route("q",lambda x:x))==("ok","bazaarlink","nemotron")
    assert calls==["qwen","deepseek","nemotron"]


def test_gemini_daily_model_quota_does_not_block_other_models(monkeypatch):
    monkeypatch.setattr(providers,"_cooldowns",{})
    providers._limit("gemini","flash",httpx.Response(429,json={"error":{"details":[
        {"violations":[{"quotaId":"GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
        {"@type":"type.googleapis.com/google.rpc.RetryInfo","retryDelay":"12s"}
    ]}}))
    assert not providers._ready("gemini","flash")
    assert providers._ready("gemini","flash-lite")
    assert providers._cooldowns[("gemini","flash")]>providers.time.monotonic()+10


def test_shared_openrouter_reset_header_is_respected(monkeypatch):
    monkeypatch.setattr(providers,"_cooldowns",{})
    reset=int((providers.time.time()+1800)*1000)
    providers._limit("openrouter","a",httpx.Response(429,json={"error":{"metadata":{
        "limit_source":"openrouter_free_tier_per_minute","headers":{"X-RateLimit-Reset":str(reset)}
    }}}))
    assert providers._cooldowns[("openrouter","*")]>providers.time.monotonic()+1700
    assert not providers._ready("openrouter","b")
