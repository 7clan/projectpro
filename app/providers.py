"""Discover available models and route bounded requests without logging credentials."""
import os
import asyncio
import logging
import httpx

log=logging.getLogger(__name__)

async def candidates(client):
    result=[]
    key=os.getenv("GEMINI_API_KEY") or os.getenv("GEMEINI")
    if key:
        try:
            r=await client.get("https://generativelanguage.googleapis.com/v1beta/models",headers={"x-goog-api-key":key},params={"pageSize":100})
            r.raise_for_status()
            names=[m["name"].removeprefix("models/") for m in r.json().get("models",[]) if "generateContent" in m.get("supportedGenerationMethods",[]) and "flash" in m["name"] and not any(x in m["name"] for x in ("image","audio","tts","live","thinking"))]
            names.sort(key=lambda n:("lite" not in n,"preview" in n),reverse=False)
            log.info("Gemini discovered %d eligible models",len(names))
            for n in names[:2]: result.append(("gemini",n,key))
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
        for n in dict.fromkeys(explicit+free[:4]+["openrouter/free"]):
            result.append(("openrouter",n,key))
    return result[:7]

async def complete(client,provider,model,key,prompt,budget=3000):
    if provider=="gemini":
        r=await client.post("https://generativelanguage.googleapis.com/v1beta/models/"+model+":generateContent",headers={"x-goog-api-key":key},json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.4,"maxOutputTokens":budget,"responseMimeType":"application/json"}})
        r.raise_for_status()
        d=r.json()
        text=" ".join(p.get("text","") for c in d.get("candidates",[]) for p in c.get("content",{}).get("parts",[]) if not p.get("thought"))
        return text
    r=await client.post("https://openrouter.ai/api/v1/chat/completions",headers={"Authorization":"Bearer "+key,"X-Title":"Declic whiteboard"},json={"model":model,"messages":[{"role":"user","content":prompt}],"temperature":0.4,"max_tokens":budget})
    r.raise_for_status()
    d=r.json(); c=d["choices"][0]
    log.info("Model %s finish=%s content_length=%s",d.get("model",model),c.get("finish_reason"),len(c["message"].get("content") or ""))
    return c["message"].get("content") or ""

async def route(prompt,validator,budget=3000):
    async with httpx.AsyncClient(timeout=30) as client:
        options=await candidates(client)
        # Two independent providers/models at most in flight. Never forward keys to unrelated hosts.
        async def try_one(option):
            provider,model,key=option
            try:
                raw=await complete(client,provider,model,key,prompt,budget)
                return validator(raw),provider,model
            except (httpx.HTTPError,ValueError,KeyError,TypeError,IndexError,AttributeError) as e:
                status=e.response.status_code if isinstance(e,httpx.HTTPStatusError) else None
                log.warning("Provider %s model=%s failed %s status=%s",provider,model,type(e).__name__,status)
                return None
        for i in range(0,len(options),2):
            tasks=[asyncio.create_task(try_one(o)) for o in options[i:i+2]]
            try:
                for task in asyncio.as_completed(tasks):
                    result=await task
                    if result is not None: return result
            finally:
                for task in tasks:
                    if not task.done(): task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
    return None
