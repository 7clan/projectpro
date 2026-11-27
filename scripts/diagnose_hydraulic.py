"""A/B diagnostic for the exact synthetic hydraulic question; no user data."""
import asyncio
import ast
import json
import os
import pathlib
import subprocess
import time
import traceback
import types
import httpx
from app import providers, whiteboard, numerical_checks, local_board

QUESTION="Explain how a hydraulic press works using Pascal's principle. Animate two pistons of different sizes connected by a fluid. Show how an input force of 50 N applied to a piston of 5 cm² produces an output force on a piston of 100 cm²."
BASELINE="401c40e92199bb5b523cf518a53082cb3aeadd41"
MODEL="qwen/qwen3.7-flash"
OUT=pathlib.Path("diagnostic")
OUT.mkdir(exist_ok=True)
key=os.environ.get("BAZAARLINK_API_KEY","")
assert key,"Missing BazaarLink secret"
# Load actual previous trusted repository code, not a reconstructed prompt.
baseline=types.ModuleType("app.baseline_whiteboard")
baseline.__package__="app"
src=subprocess.check_output(["git","show",BASELINE+":app/whiteboard.py"],text=True)
exec(compile(src,"baseline_whiteboard.py","exec"),baseline.__dict__)

def safe_error(exc):
    frames=traceback.extract_tb(exc.__traceback__)
    locations=[f"{pathlib.Path(f.filename).name}:{f.lineno}:{f.name}" for f in frames if "app" in f.filename or "baseline_whiteboard" in f.filename]
    # This script uses synthetic questions only. Still redact configured keys.
    msg=str(exc).replace(key,"[redacted]")
    for n in ("GEMINI_API_KEY","OPENROUTER_API_KEY"):
        secret=os.getenv(n)
        if secret:msg=msg.replace(secret,"[redacted]")
    return {"error_type":type(exc).__name__,"reason":msg[:240],"locations":locations}

async def capture(module):
    captures={}
    old=providers.route
    async def intercept(prompt,validator,budget=3000,**kwargs):
        captures.update(prompt=prompt,validator=validator,budget=budget)
        return None
    providers.route=intercept
    try:
        with providers.use_mode("cloud",True):
            await module.generate(QUESTION,"en",[],[])
    finally:
        providers.route=old
    assert captures,"No generation prompt"
    return captures

def validate(fn,raw):
    try:
        steps,checks=fn(raw)
        return {"accepted":True,"scenes":len(steps),"checks":len(checks)}
    except Exception as exc:
        return {"accepted":False,**safe_error(exc)}

async def main():
    prompts={"baseline":await capture(baseline),"candidate":await capture(whiteboard)}
    print("PROMPT LENGTHS", {k:len(v["prompt"]) for k,v in prompts.items()},flush=True)
    results={}
    # Two real requests to same known model, no other provider or model changes.
    for name in ("candidate","baseline"):
        p=prompts[name]
        start=time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(45,connect=5),trust_env=False) as client:
                r=await client.post("https://api.bazaarlink.ai/v1/chat/completions",
                    headers={"Authorization":"Bearer "+key,"X-Free-Fallback":"false"},
                    json={"model":MODEL,"messages":[{"role":"user","content":p["prompt"]}],"temperature":0.4,"max_tokens":p["budget"]})
                if r.status_code!=200:
                    results[name]={"http_status":r.status_code}
                    print("DIAGNOSTIC",name,json.dumps(results[name]),flush=True)
                    continue
                d=r.json()
                c=d["choices"][0]
                raw=c["message"].get("content") or ""
                safe=raw.replace(key,"[redacted]")
                for n in ("GEMINI_API_KEY","OPENROUTER_API_KEY"):
                    secret=os.getenv(n)
                    if secret:safe=safe.replace(secret,"[redacted]")
                (OUT/(name+"-synthetic-response.txt")).write_text(safe,encoding="utf-8")
                usage=d.get("usage") or {}
                results[name]={"http_status":200,"finish_reason":c.get("finish_reason"),"output_chars":len(raw),
                   "completion_tokens":usage.get("completion_tokens"),"seconds":round(time.monotonic()-start,2),
                   "validation":{k:validate(v["validator"],raw) for k,v in prompts.items()}}
        except (httpx.HTTPError,ValueError,KeyError,TypeError,IndexError) as exc:
            results[name]=safe_error(exc)
        print("DIAGNOSTIC",name,json.dumps(results[name],ensure_ascii=False),flush=True)
        (OUT/"results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    # Diagnostic completion is not acceptance. Deliberately fail if no usable result.
    assert any(v.get("validation",{}).get("candidate",{}).get("accepted") for v in results.values()),"No response passed candidate validator"

if __name__=="__main__":
    asyncio.run(main())
