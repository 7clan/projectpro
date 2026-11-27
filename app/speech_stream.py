"""Optional streaming, on-host speech recognition. No audio persistence or cloud inference."""
import asyncio
import importlib.util
import json
import os
import threading
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import WebSocket, WebSocketDisconnect
from .storage import session_user

ROOT=Path(__file__).resolve().parents[1]
_models={}
_model_lock=threading.Lock()
_active=set()
MAX_STREAMS=2
MAX_AUDIO_BYTES=16_000*2*45

def model_path(lang):
    default="vosk-model-small-fr-0.22" if lang=="fr" else "vosk-model-small-en-us-0.15"
    return Path(os.getenv("DECLIC_VOSK_"+lang.upper(),str(ROOT/"speech-models"/default)))

def available(lang):
    return lang in ("fr","en") and importlib.util.find_spec("vosk") is not None and (model_path(lang)/"am").is_dir()

def capabilities():
    return {lang:available(lang) for lang in ("fr","en")}

def recognizer(lang):
    from vosk import Model,KaldiRecognizer,SetLogLevel
    path=str(model_path(lang).resolve())
    with _model_lock:
        if path not in _models:
            SetLogLevel(-1)
            _models[path]=Model(model_path=path)
        model=_models[path]
    return KaldiRecognizer(model,16000)

def accept(rec,data):
    final=rec.AcceptWaveform(data)
    value=json.loads(rec.Result() if final else rec.PartialResult())
    return {"type":"final" if final else "partial","text":str(value.get("text" if final else "partial",""))[:800]}

def finish(rec):
    return {"type":"final","text":str(json.loads(rec.FinalResult()).get("text",""))[:800]}

def same_origin(ws):
    try:
        origin=urlsplit(ws.headers.get("origin",""))
        return origin.scheme in ("http","https") and origin.netloc.casefold()==ws.headers.get("host","").casefold() and not origin.username and not origin.password
    except ValueError:return False

def install(app):
    @app.websocket("/api/studio/listen")
    async def listen(ws:WebSocket):
        if not same_origin(ws):
            await ws.close(code=1008);return
        if len(_active)>=MAX_STREAMS:
            await ws.close(code=1013);return
        await ws.accept()
        uid=None
        reserved=False
        try:
            first=await asyncio.wait_for(ws.receive_text(),5)
            if len(first)>2048:await ws.close(code=1009);return
            config=json.loads(first)
            if not isinstance(config,dict):await ws.close(code=1008);return
            token=config.get("token");lang=config.get("lang")
            if not isinstance(token,str) or len(token)>256 or lang not in ("fr","en"):
                await ws.close(code=1008);return
            user=await asyncio.to_thread(session_user,token)
            if not user:await ws.close(code=1008);return
            uid=user["id"]
            if uid in _active or len(_active)>=MAX_STREAMS:
                await ws.close(code=1013);return
            _active.add(uid);reserved=True
            if not available(lang):
                await ws.send_json({"type":"error","message":"Local speech model unavailable"})
                await ws.close(code=1011);return
            rec=await asyncio.to_thread(recognizer,lang)
            await ws.send_json({"type":"ready","backend":"vosk-local","sample_rate":16000})
            total=0;deadline=asyncio.get_running_loop().time()+55
            while asyncio.get_running_loop().time()<deadline:
                message=await asyncio.wait_for(ws.receive(),min(8,max(.1,deadline-asyncio.get_running_loop().time())))
                if message["type"]=="websocket.disconnect":return
                data=message.get("bytes")
                if data is not None:
                    if not data or len(data)%2 or len(data)>16000:
                        await ws.close(code=1009);return
                    total+=len(data)
                    if total>MAX_AUDIO_BYTES:
                        await ws.send_json(await asyncio.to_thread(finish,rec));await ws.close();return
                    result=await asyncio.to_thread(accept,rec,data)
                    if result["text"]:
                        await ws.send_json(result)
                        if result["type"]=="final":await ws.close();return
                elif message.get("text")=="end":
                    await ws.send_json(await asyncio.to_thread(finish,rec));await ws.close();return
                else:
                    await ws.close(code=1008);return
            await ws.send_json(await asyncio.to_thread(finish,rec));await ws.close()
        except WebSocketDisconnect:pass
        except (asyncio.TimeoutError,ValueError,TypeError,RuntimeError,OSError):
            try:await ws.close(code=1011)
            except (RuntimeError,WebSocketDisconnect):pass
        finally:
            if reserved:_active.discard(uid)
