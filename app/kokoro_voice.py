"""Optional offline Kokoro speech; CPU bounded, no implicit model downloads."""
import asyncio
import io
import logging
import os
import threading
import wave
from functools import lru_cache
from pathlib import Path

_LOCK=threading.Lock()
_VOICES={"en":("af_heart","en-us"),"fr":("ff_siwis","fr-fr")}
def model_directory():
    return Path(os.getenv("DECLIC_KOKORO_DIR",str(Path(__file__).resolve().parents[1]/"voices"/"kokoro")))

@lru_cache(maxsize=1)
def _engine(model,voices):
    import onnxruntime as ort
    from kokoro_onnx import Kokoro
    options=ort.SessionOptions()
    options.intra_op_num_threads=2
    options.inter_op_num_threads=1
    session=ort.InferenceSession(model,sess_options=options,providers=["CPUExecutionProvider"])
    return Kokoro.from_session(session,voices)

def _render(text,lang,cues):
    from .voice import split_cues
    import numpy as np
    directory=model_directory()
    model=directory/"kokoro-v1.0.onnx"
    voices=directory/"voices-v1.0.bin"
    if not model.is_file() or not voices.is_file():
        raise FileNotFoundError("Kokoro model files not installed")
    parts=split_cues(text,cues)
    # Coalesce adjacent reveal groups to preserve phrase-level prosody.
    # All original cues survive, and nearby cues may share a phrase onset.
    while len(parts)>3:
        i=min(range(len(parts)-1),key=lambda i:len(parts[i][0])+len(parts[i+1][0]))
        a,aa=parts[i];b,bb=parts[i+1]
        parts[i:i+2]=[(a+" "+b,sorted(set(aa+bb)))]
    speaker,language=_VOICES[lang]
    out=io.BytesIO();marks=[];offset=0
    # Avoid piling up CPU-heavy jobs across browser sessions.
    if not _LOCK.acquire(timeout=2):
        raise TimeoutError("Kokoro busy")
    try:
        engine=_engine(str(model),str(voices))
        with wave.open(out,"wb") as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000)
            for fragment,positions in parts:
                samples,rate=engine.create(fragment,voice=speaker,lang=language,speed=1.0)
                samples=np.asarray(samples,dtype=np.float32).reshape(-1)
                if rate!=24000 or not len(samples) or not np.isfinite(samples).all() or np.max(np.abs(samples))<.001:
                    raise ValueError("Invalid Kokoro audio")
                pcm=(np.clip(samples,-1,1)*32767).astype("<i2")
                marks.extend({"at":f,"time":round(offset/rate,4)} for f in positions)
                w.writeframes(pcm.tobytes());offset+=len(pcm)
    finally:
        _LOCK.release()
    return out.getvalue(),marks

async def synthesize_kokoro(text,lang,cues):
    from .voice import split_cues,synthesize_preferred
    split_cues(text,cues)
    try:
        audio,marks=await asyncio.wait_for(asyncio.to_thread(_render,text,lang,cues),25)
        return audio,marks,"kokoro-neural"
    except Exception as exc:
        # Optional runtime may fail due to DLL, missing assets, or unsupported CPU.
        # Never send the local-voice request to a cloud provider.
        logging.getLogger(__name__).warning("Kokoro local fallback: %s",type(exc).__name__)
        return await synthesize_preferred(text,lang,cues,cloud=False)
