"""Minimal independent cloud inference checks; no secrets or course data printed."""
import asyncio
import os
import time
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
KEYS={"gemini":("GEMINI_API_KEY","GEMEINI"),"openrouter":("OPENROUTER_API_KEY","OPENROUTER"),"bazaarlink":("BAZAARLINK_API_KEY","SOME")}

def load_keys():
    file=ROOT/".env"
    if file.is_file():
        allowed={k for names in KEYS.values() for k in names}
        for line in file.read_text(encoding="utf-8-sig").splitlines():
            name,sep,value=line.partition("=")
            if sep and name.strip() in allowed:
                value=value.strip()
                if len(value)>=2 and value[0]==value[-1] and value[0] in ("'",'"'):
                    value=value[1:-1]
                os.environ[name.strip()]=value

async def probe(provider):
    key=next((os.getenv(k,"").strip() for k in KEYS[provider] if os.getenv(k,"").strip()),"")
    if not key:return f"{provider}: NOT CONFIGURED"
    started=time.monotonic()
    model=""
    try:
        async with httpx.AsyncClient(timeout=35,trust_env=False) as client:
            prompt="Respond with exactly the word OK. Do not explain."
            if provider=="gemini":
                base="https://generativelanguage.googleapis.com/v1beta/"
                headers={"x-goog-api-key":key}
                response=await client.get(base+"models",headers=headers,params={"pageSize":100})
                response.raise_for_status()
                models=[m["name"] for m in response.json().get("models",[]) if "generateContent" in m.get("supportedGenerationMethods",[]) and "flash" in m["name"] and not any(x in m["name"] for x in ("image","audio","tts","live","thinking"))]
                if not models:return "gemini: AUTHENTICATED, no compatible Flash text model discovered"
                model=max(models,key=lambda m:("3.6-flash" in m,"3.5-flash-lite" in m,"lite" in m,"latest" not in m,"preview" not in m))
                response=await client.post(base+model+":generateContent",headers=headers,json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"maxOutputTokens":1024}})
                response.raise_for_status()
                reply=" ".join(p.get("text","") for c in response.json().get("candidates",[]) for p in c.get("content",{}).get("parts",[]) if not p.get("thought"))
            else:
                model="openrouter/free" if provider=="openrouter" else "qwen/qwen3.7-flash"
                base="https://openrouter.ai/api/v1" if provider=="openrouter" else "https://api.bazaarlink.ai/v1"
                headers={"Authorization":"Bearer "+key}
                if provider=="bazaarlink":headers["X-Free-Fallback"]="false"
                response=await client.post(base+"/chat/completions",headers=headers,json={"model":model,"messages":[{"role":"user","content":prompt}],"max_tokens":1024})
                response.raise_for_status()
                data=response.json()
                reply=data["choices"][0]["message"].get("content") or ""
                model=data.get("model",model)
            seconds=time.monotonic()-started
            return f"{provider}: {'PASS' if reply.strip() else 'HTTP 200, EMPTY RESPONSE'} | {model} | {seconds:.1f}s"
    except httpx.HTTPStatusError as e:
        status=e.response.status_code
        reason={400:"request rejected",401:"authentication rejected",402:"payment or quota required",403:"access forbidden",429:"rate limit or quota",502:"upstream error",503:"service unavailable"}.get(status,"HTTP error")
        return f"{provider}: HTTP {status} ({reason}) | {model or 'discovery'}"
    except httpx.TimeoutException:
        return f"{provider}: TIMEOUT | {model or 'discovery'}"
    except (httpx.HTTPError,ValueError,KeyError,IndexError,TypeError,AttributeError) as e:
        return f"{provider}: FAILED ({type(e).__name__}) | {model or 'discovery'}"

async def main():
    load_keys()
    results=await asyncio.gather(*(probe(p) for p in KEYS))
    for result in results:print(result)
    print("A pass verifies a short text response now, not animation or future quota. No local AI was loaded.")

if __name__=="__main__":
    asyncio.run(main())
