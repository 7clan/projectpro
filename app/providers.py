"""Discover available models and route bounded requests without logging credentials."""
import os
import asyncio
import logging
import time
import math
import re
import httpx
from contextvars import ContextVar
from contextlib import contextmanager

log=logging.getLogger(__name__)

# In-memory process-wide rate-limit state; never store or log secret values.
_cooldowns={}

def _ready(provider,model):
    now=time.monotonic()
    return max(_cooldowns.get((provider,"*"),0),_cooldowns.get((provider,model),0))<=now

def _limit(provider,model,response):
    status=response.status_code
    if status not in (401,402,403,429,502,503,504):return
    try:
        body=response.json()
        if not isinstance(body,dict):body={}
    except (ValueError,TypeError):body={}
    error=body.get("error",{})
    if not isinstance(error,dict):error={}
    metadata=error.get("metadata",{})
    if not isinstance(metadata,dict):metadata={}
    source=str(metadata.get("limit_source") or error.get("limit_source") or "").casefold()
    message=str(error.get("message","")).casefold()
    codes={str(obj.get(field,"")).casefold() for obj in (body,error)
           for field in ("code","type","reason")}
    scope=model
    default=60
    if status in (401,403):
        scope="*"
        default=300
    elif provider=="openrouter":
        if source.startswith("openrouter_free_tier_") or (
            status==429 and ("free-models-per-" in message or "free-models-per-day" in message)
        ) or source in ("openrouter_key_limit","openrouter_credits","openrouter_in_flight_budget"):
            scope="*"
        if source=="openrouter_free_tier_daily" or "free-models-per-day" in message:
            default=86400-time.time()%86400
    elif provider=="bazaarlink" and status==429:
        # Unknown BazaarLink 429s are conservatively treated as account limits.
        if "free_quota_exhausted" not in codes:
            scope="*"
    elif provider=="gemini" and status==429:
        # Gemini quota IDs identify per-day limits; RetryInfo often gives only
        # a short retry hint even when the daily model allowance is exhausted.
        details=error.get("details",[])
        if not isinstance(details,list):details=[]
        daily=False
        for detail in details:
            if not isinstance(detail,dict):continue
            violations=detail.get("violations",[])
            if not isinstance(violations,list):continue
            for violation in violations:
                if not isinstance(violation,dict):continue
                quota=str(violation.get("quotaId","")).casefold()
                metric=str(violation.get("quotaMetric","")).casefold()
                if "perday" in quota or "per_day" in metric:
                    daily=True
                if "perproject" in quota and "permodel" not in quota and not (isinstance(violation.get("quotaDimensions"),dict) and violation["quotaDimensions"].get("model")):
                    scope="*"
        if daily:
            # Google resets RPD at midnight Pacific. Windows may lack IANA
            # tzdata, in which case a conservative hourly recheck is used.
            try:
                from datetime import datetime,timedelta
                from zoneinfo import ZoneInfo
                now=datetime.now(ZoneInfo("America/Los_Angeles"))
                reset=(now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
                default=max(60,reset.timestamp()-now.timestamp())
            except (ImportError,KeyError):default=3600
        else:
            for detail in details:
                if isinstance(detail,dict) and str(detail.get("@type","")).endswith("RetryInfo"):
                    try:default=max(default,float(str(detail.get("retryDelay","")).removesuffix("s")))
                    except ValueError:pass
    # Honor server retry timing, including OpenRouter's millisecond reset
    # timestamp, without shortening daily quota cooldowns to a few minutes.
    headers=metadata.get("headers",{})
    if not isinstance(headers,dict):headers={}
    headers={str(k).casefold():v for k,v in headers.items()}
    delay=default
    retry=response.headers.get("Retry-After") or headers.get("retry-after")
    if retry is not None:
        try:delay=float(retry)
        except (ValueError,TypeError):
            try:
                from email.utils import parsedate_to_datetime
                delay=parsedate_to_datetime(str(retry)).timestamp()-time.time()
            except (ValueError,TypeError,OverflowError):delay=default
    reset=response.headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset")
    if reset is not None:
        try:delay=max(delay if retry is not None else 0,float(reset)/1000-time.time())
        except (ValueError,TypeError):pass
    if not math.isfinite(delay):delay=default
    if default>600:delay=max(delay,default)
    seconds=max(15,min(86400,delay))
    slot=(provider,scope)
    _cooldowns[slot]=max(_cooldowns.get(slot,0),time.monotonic()+seconds)
    log.info("AI cooldown provider=%s scope=%s seconds=%d status=%s",provider,scope,seconds,status)

def local_model():
    name=os.getenv("DECLIC_OLLAMA_MODEL","").strip()
    # Do not treat Ollama cloud models as offline inference.
    if not name or "cloud" in name.casefold() or "/" in name and name.startswith(("http:","https:")):return ""
    return name

def cloud_model():
    """Opt-in signed-in Ollama daemon cloud model, never treated as local."""
    name=os.getenv("DECLIC_OLLAMA_CLOUD_MODEL","").strip()
    return name if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,160}:cloud",name) else ""

_request_mode=ContextVar("declic_ai_mode",default="hybrid")

def mode():
    return "local" if os.getenv("DECLIC_LOCAL_ONLY")=="1" else _request_mode.get()

@contextmanager
def use_mode(value,consent=False):
    if value not in ("hybrid","local","cloud","ollama_cloud"):raise ValueError("Unknown AI mode")
    effective="local" if os.getenv("DECLIC_LOCAL_ONLY")=="1" or value=="local" else value if consent else "local" if value=="hybrid" and local_model() else "disabled"
    token=_request_mode.set(effective)
    try:yield effective
    finally:_request_mode.reset(token)

def local_only():
    return mode()=="local"

def configured_modes():
    cloud=bool(cloud_model()) or any(os.getenv(k) for k in ("GEMINI_API_KEY","GEMEINI","OPENROUTER_API_KEY","OPENROUTER","BAZAARLINK_API_KEY","SOME"))
    local=bool(local_model())
    if os.getenv("DECLIC_LOCAL_ONLY")=="1":return {"local":local,"cloud":False,"hybrid":False,**({"ollama_cloud":False} if cloud_model() else {})}
    return {"local":local,"cloud":cloud,"hybrid":cloud and local,**({"ollama_cloud":True} if cloud_model() else {})}


def local_timeout():
    try:return max(30,min(300,int(os.getenv("DECLIC_OLLAMA_TIMEOUT","180"))))
    except ValueError:return 180

def gemini_rank(name):
    # Prefer discovered low-use models from the pilot account, then Flash Lite.
    n=name.casefold().removeprefix("models/")
    return ("3.6-flash" in n, "3.5-flash-lite" in n, "lite" in n, "latest" not in n, "preview" not in n)

def router_rank(name):
    n=name.casefold()
    return (n=="google/gemma-4-31b-it:free",any(s in n for s in ("gemma","mistral","qwen","llama")),not any(s in n for s in ("thinking","reason","r1")),"instruct" in n)

async def candidates(client):
    result=[]
    local=local_model()
    if mode()=='disabled':return result
    if mode()=="ollama_cloud":
        return [("ollama_cloud",cloud_model(),"")] if cloud_model() else []
    if local and mode()!='cloud':result.append(('ollama',local,''))
    if local_only():return result
    if cloud_model():result.append(("ollama_cloud",cloud_model(),""))
    key=os.getenv("GEMINI_API_KEY") or os.getenv("GEMEINI")
    if key:
        try:
            r=await client.get("https://generativelanguage.googleapis.com/v1beta/models",headers={"x-goog-api-key":key},params={"pageSize":100})
            r.raise_for_status()
            names=[m["name"].removeprefix("models/") for m in r.json().get("models",[]) if "generateContent" in m.get("supportedGenerationMethods",[]) and "flash" in m["name"] and not any(x in m["name"] for x in ("image","audio","tts","live","thinking"))]
            names.sort(key=gemini_rank,reverse=True)
            log.info("Gemini discovered %d eligible models",len(names))
            for n in dict.fromkeys(names[:6]): result.append(("gemini",n,key))
        except (httpx.HTTPError,KeyError,ValueError) as e:
            log.warning("Gemini discovery failed: %s",type(e).__name__)
    key=os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER")
    if key:
        explicit=[x.strip() for x in os.getenv("OPENROUTER_BOARD_MODELS","").split(",") if x.strip() and x.strip().endswith(":free")]
        try:
            r=await client.get("https://openrouter.ai/api/v1/models")
            r.raise_for_status()
            free=[m["id"] for m in r.json().get("data",[]) if m["id"].endswith(":free") and "text" in m.get("architecture",{}).get("output_modalities",["text"])]
            # Prefer instruct-oriented models, then other currently listed free models.
            free.sort(key=router_rank,reverse=True)
            log.info("OpenRouter discovered %d free models",len(free))
        except (httpx.HTTPError,KeyError,ValueError):
            free=[]
        for n in dict.fromkeys(explicit+free[:8]+["openrouter/free"]):
            result.append(("openrouter",n,key))
    key=os.getenv("BAZAARLINK_API_KEY") or os.getenv("SOME")
    if key:
        # Current documented free models, with the provider's guaranteed free router as fallback.
        for model in ("qwen/qwen3.7-flash","deepseek/deepseek-v4-flash-0731free","nvidia/nemotron-3.5-lightning-free","auto:free"):
            result.append(("bazaarlink",model,key))
    return result

async def complete(client,provider,model,key,prompt,budget=3000):
    if provider=="ollama":
        # Fixed loopback endpoint; clients cannot supply server URLs or models.
        r=await client.post("http://127.0.0.1:11434/api/chat",timeout=local_timeout(),json={"model":model,"messages":[{"role":"user","content":prompt}],"stream":False,"format":"json","options":{"num_predict":budget,"num_ctx":4096,"temperature":0.3}})
        r.raise_for_status()
        return r.json()["message"]["content"]
    if provider=="ollama_cloud":
        # The signed-in desktop daemon authenticates remote inference. No API key,
        # schema format or local context settings are forwarded from DÉCLIC.
        r=await client.post("http://127.0.0.1:11434/api/chat",timeout=local_timeout(),json={"model":model,"messages":[{"role":"user","content":prompt}],"stream":False})
        r.raise_for_status()
        return r.json()["message"]["content"]
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

async def _route(prompt,validator,budget=3000,exclude_model=None,max_candidates=20,role="lesson"):
    # Long multi-scene generation needs more time than a short coach response.
    # Keep connection timeout short; preserve an absolute routing deadline.
    read_timeout=35 if role=="lesson" and budget>=2600 else 12
    async with httpx.AsyncClient(timeout=httpx.Timeout(read_timeout,connect=5),trust_env=False) as client:
        options=[o for o in await candidates(client) if o[1]!=exclude_model]
        local=[o for o in options if o[0]=="ollama" and _ready(o[0],o[1])]
        router=[o for o in options if o[0]=="openrouter" and _ready(o[0],o[1])]
        bazaar=[o for o in options if o[0]=="bazaarlink" and _ready(o[0],o[1])]
        gemini=[o for o in options if o[0]=="gemini" and _ready(o[0],o[1])]
        ollama_cloud=[o for o in options if o[0]=="ollama_cloud" and _ready(o[0],o[1])]
        reserve=bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER") or os.getenv("BAZAARLINK_API_KEY") or os.getenv("SOME"))
        if reserve and (role=="review" or os.getenv("DECLIC_GEMINI_TEXT_FALLBACK","1")=="0"):
            gemini=[]
        # Keep the same API key/provider while walking its ranked model pool.
        # Shared quota failures mark the provider and skip its remaining models.
        options=router+bazaar+gemini
        options=ollama_cloud if mode()=="ollama_cloud" else local+options if local_only() else options+ollama_cloud+local
        attempts=0
        for provider,model,key in options:
            if not _ready(provider,model):continue
            if attempts>=max_candidates:break
            attempts+=1
            phase="inference"
            try:
                raw=await complete(client,provider,model,key,prompt,budget)
                if not isinstance(raw,str) or not raw.strip():raise ValueError("Empty model response")
                phase="validation"
                value=validator(raw)
                log.warning("AI route success role=%s provider=%s model=%s",role,provider,model)
                return value,provider,model
            except (httpx.HTTPError,ValueError,KeyError,TypeError,IndexError,AttributeError) as e:
                status=e.response.status_code if isinstance(e,httpx.HTTPStatusError) else None
                if status is not None:_limit(provider,model,e.response)
                elif isinstance(e,httpx.TimeoutException):
                    slot=(provider,model)
                    _cooldowns[slot]=max(_cooldowns.get(slot,0),time.monotonic()+60)
                # Do not log exception text: an upstream exception could contain prompt data.
                log.warning("Provider %s model=%s role=%s failed %s status=%s phase=%s",provider,model,role,type(e).__name__,status,phase)
    return None

async def route(prompt,validator,budget=3000,exclude_model=None,max_candidates=20,role="lesson"):
    try:
        return await asyncio.wait_for(_route(prompt,validator,budget,exclude_model,max_candidates,role),timeout=local_timeout()+10 if (local_model() and mode()!='cloud') or (cloud_model() and not local_only() and mode()!='disabled') else (110 if role=="lesson" and budget>=2600 else 50))
    except asyncio.TimeoutError:
        log.warning("Provider routing deadline exceeded role=%s",role)
        return None


async def provider_status():
    """Configuration is not proof of cloud availability; probe only local daemon."""
    modes=configured_modes()
    model=local_model()
    local={"configured":bool(model),"model":model or None,"reachable":False,"installed":False}
    if model or cloud_model():
        try:
            async with httpx.AsyncClient(timeout=3,trust_env=False) as client:
                response=await client.get("http://127.0.0.1:11434/api/tags")
                response.raise_for_status()
                local["reachable"]=True
                tags=response.json().get("models",[])
                names={model,model+":latest"} if ":" not in model else {model}
                local["installed"]=any(t.get("name") in names and not t.get("remote_model") and not t.get("remote_host") for t in tags if isinstance(t,dict))
        except (httpx.HTTPError,ValueError,TypeError,AttributeError):pass
    providers={"ollama":local,
        "gemini":{"configured":bool(os.getenv("GEMINI_API_KEY") or os.getenv("GEMEINI"))},
        "openrouter":{"configured":bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER"))},
        "bazaarlink":{"configured":bool(os.getenv("BAZAARLINK_API_KEY") or os.getenv("SOME"))}}
    if cloud_model():providers["ollama_cloud"]={"configured":True,"model":cloud_model(),"reachable":local["reachable"],"authenticated":None}
    return {"modes":modes,"providers":providers}
