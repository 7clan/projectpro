"""Discover available models and route bounded requests without logging credentials."""
import os
import asyncio
import logging
import time
import math
import httpx

log=logging.getLogger(__name__)

# In-memory process-wide rate-limit state; never store or log secret values.
_cooldowns={}

def _ready(provider,model):
    now=time.monotonic()
    return max(_cooldowns.get((provider,"*"),0),_cooldowns.get((provider,model),0))<=now

def _limit(provider,model,response):
    status=response.status_code
    if status not in (401,402,403,429):return
    try:delay=float(response.headers.get("Retry-After","60"))
    except ValueError:delay=60
    if not math.isfinite(delay):delay=60
    scope="*" if status in (401,403) or (provider=="bazaarlink" and status==429) else model
    # A 402 can reflect the requested token budget for an individual model.
    # Do not disable every model for that response.
    seconds=300 if status in (401,403) else max(15,min(600,delay))
    _cooldowns[(provider,scope)]=time.monotonic()+seconds

async def candidates(client):
    result=[]
    key=os.getenv("GEMINI_API_KEY") or os.getenv("GEMEINI")
    if key:
        try:
            r=await client.get("https://generativelanguage.googleapis.com/v1beta/models",headers={"x-goog-api-key":key},params={"pageSize":100})
            r.raise_for_status()
            names=[m["name"].removeprefix("models/") for m in r.json().get("models",[]) if "generateContent" in m.get("supportedGenerationMethods",[]) and "flash" in m["name"] and not any(x in m["name"] for x in ("image","audio","tts","live","thinking"))]
            names.sort(key=lambda n:(("latest" in n),("2.5" not in n),("lite" not in n),("preview" not in n)),reverse=True)
            log.info("Gemini discovered %d eligible models",len(names))
            for n in names[:4]: result.append(("gemini",n,key))
        except (httpx.HTTPError,KeyError,ValueError) as e:
            log.warning("Gemini discovery failed: %s",type(e).__name__)
    key=os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER")
    if key:
        explicit=[x.strip() for x in os.getenv("OPENROUTER_BOARD_MODELS","").split(",") if x.strip()]
        try:
            r=await client.get("https://openrouter.ai/api/v1/models")
            r.raise_for_status()
            free=[m["id"] for m in r.json().get("data",[]) if m["id"].endswith(":free") and "text" in m.get("architecture",{}).get("output_modalities",["text"])]
            # Prefer instruct-oriented models, then other currently listed free models.
            def rank(n):
                return (any(s in n.lower() for s in ("gemma","mistral","qwen","llama")),not any(s in n.lower() for s in ("thinking","reason","r1")), "instruct" in n.lower())
            free.sort(key=rank,reverse=True)
            log.info("OpenRouter discovered %d free models",len(free))
        except (httpx.HTTPError,KeyError,ValueError):
            free=[]
        for n in dict.fromkeys(explicit+free[:5]+["openrouter/free"]):
            result.append(("openrouter",n,key))
    key=os.getenv("BAZAARLINK_API_KEY") or os.getenv("SOME")
    if key:
        # Current documented free models, with the provider's guaranteed free router as fallback.
        for model in ("qwen/qwen3.7-flash","deepseek/deepseek-v4-flash-0731free","nvidia/nemotron-3.5-lightning-free","auto:free"):
            result.append(("bazaarlink",model,key))
    return result

async def complete(client,provider,model,key,prompt,budget=3000):
    if provider=="gemini":
        r=await client.post("https://generativelanguage.googleapis.com/v1beta/models/"+model+":generateContent",headers={"x-goog-api-key":key},json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.4,"maxOutputTokens":max(6000,budget),"responseMimeType":"application/json"}})
        r.raise_for_status()
        d=r.json()
        log.info("Gemini model %s finish=%s",model,[c.get("finishReason") for c in d.get("candidates",[])])
        text=" ".join(p.get("text","") for c in d.get("candidates",[]) for p in c.get("content",{}).get("parts",[]) if not p.get("thought"))
        return text
    if provider=="bazaarlink":
        r=await client.post("https://api.bazaarlink.ai/v1/chat/completions",
            headers={"Authorization":"Bearer "+key,"X-Free-Fallback":"false"},
            json={"model":model,"messages":[{"role":"user","content":prompt}],"temperature":0.4,"max_tokens":budget})
        r.raise_for_status()
        d=r.json()
        return d["choices"][0]["message"].get("content") or ""
    if provider!="openrouter":raise ValueError("Unknown provider")
    r=await client.post("https://openrouter.ai/api/v1/chat/completions",headers={"Authorization":"Bearer "+key,"X-Title":"Declic whiteboard"},json={"model":model,"messages":[{"role":"user","content":prompt}],"temperature":0.4,"max_tokens":budget})
    r.raise_for_status()
    d=r.json(); c=d["choices"][0]
    log.info("Model %s finish=%s content_length=%s",d.get("model",model),c.get("finish_reason"),len(c["message"].get("content") or ""))
    return c["message"].get("content") or ""

async def _route(prompt,validator,budget=3000,exclude_model=None,max_candidates=10,role="lesson"):
    async with httpx.AsyncClient(timeout=12) as client:
        options=[o for o in await candidates(client) if o[1]!=exclude_model]
        router=[o for o in options if o[0]=="openrouter" and _ready(o[0],o[1])]
        bazaar=[o for o in options if o[0]=="bazaarlink" and _ready(o[0],o[1])]
        gemini=[o for o in options if o[0]=="gemini" and _ready(o[0],o[1])]
        reserve=bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER") or os.getenv("BAZAARLINK_API_KEY") or os.getenv("SOME"))
        if reserve and (role=="review" or os.getenv("DECLIC_GEMINI_TEXT_FALLBACK","1")=="0"):
            gemini=[]
        # Different accounts share no local cooldown. Avoid redundant parallel calls.
        # Prefer BazaarLink for original visual lessons, OpenRouter for short coaching.
        if role=="review":
            bazaar=sorted(bazaar,key=lambda o:"deepseek" not in o[1])
        first,second=(bazaar,router) if role in ("lesson","review") else (router,bazaar)
        options=[]
        if first:options.append(first[0])
        if second:options.append(second[0])
        if len(first)>1:options.append(first[1])
        if len(second)>1:options.append(second[1])
        options.extend(gemini[:2])
        if not first and not second:options=gemini[:3]
        for provider,model,key in options[:max_candidates]:
            if not _ready(provider,model):continue
            try:
                raw=await complete(client,provider,model,key,prompt,budget)
                value=validator(raw)
                log.info("AI route success role=%s provider=%s model=%s",role,provider,model)
                return value,provider,model
            except (httpx.HTTPError,ValueError,KeyError,TypeError,IndexError,AttributeError) as e:
                status=e.response.status_code if isinstance(e,httpx.HTTPStatusError) else None
                if status is not None:_limit(provider,model,e.response)
                log.warning("Provider %s model=%s role=%s failed %s status=%s",provider,model,role,type(e).__name__,status)
    return None

async def route(prompt,validator,budget=3000,exclude_model=None,max_candidates=10,role="lesson"):
    try:
        return await asyncio.wait_for(_route(prompt,validator,budget,exclude_model,max_candidates,role),timeout=50)
    except asyncio.TimeoutError:
        log.warning("Provider routing deadline exceeded role=%s",role)
        return None
