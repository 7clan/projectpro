"""Local speech with exact phrase-level reveal markers."""
import asyncio
import io
import math
import logging
import time
import re
import shutil
import struct
import wave

def split_cues(text,cues):
    # Align each requested fractional text position with the beginning of a word.
    text=text.strip()
    boundaries=[m.start() for m in re.finditer(r"\S+",text)]
    if not boundaries: raise ValueError("Empty narration")
    if len(boundaries)>17:
        boundaries=[boundaries[round(i*(len(boundaries)-1)/16)] for i in range(17)]
    groups={0:[0.0]}
    for f in sorted(set(cues)):
        if type(f) not in (int,float) or not math.isfinite(f) or not 0<=f<=.9: raise ValueError("Invalid cue")
        pos=min(boundaries,key=lambda x:abs(x-f*len(text)))
        groups.setdefault(pos,[]).append(float(f))
    if len(groups)>17: raise ValueError("Too many cues")
    starts=sorted(groups)
    return [(text[a:b].strip(),sorted(set(groups[a]))) for a,b in zip(starts,starts[1:]+[len(text)])]

def repair_wav(data):
    wav=bytearray(data)
    if len(wav)<44 or not wav.startswith(b'RIFF'): raise ValueError("Invalid voice output")
    struct.pack_into('<I',wav,4,len(wav)-8)
    off=12
    while off+8<=len(wav):
        size=struct.unpack_from('<I',wav,off+4)[0]
        if wav[off:off+4]==b'data':
            struct.pack_into('<I',wav,off+4,len(wav)-off-8)
            return bytes(wav)
        off+=8+size+(size%2)
    raise ValueError("Missing audio data")

async def synthesize(text,lang,cues):
    executable=shutil.which('espeak-ng') or shutil.which('espeak')
    if not executable: raise FileNotFoundError("No local voice")
    parts=split_cues(text,cues)
    frames=[];marks=[];params=None;offset=0
    for fragment,positions in parts:
        proc=await asyncio.create_subprocess_exec(executable,'--stdout','-v',lang,'-s','155','--stdin',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        try:
            raw,_=await asyncio.wait_for(proc.communicate(fragment.encode()),5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise
        if proc.returncode: raise ValueError("Voice generation failed")
        with wave.open(io.BytesIO(repair_wav(raw)),'rb') as w:
            p=w.getparams()
            if params is None: params=p
            if (p.nchannels,p.sampwidth,p.framerate)!=(params.nchannels,params.sampwidth,params.framerate): raise ValueError("Inconsistent voice format")
            marks.extend([{"at":f,"time":round(offset/p.framerate,4)} for f in positions])
            frames.append(w.readframes(p.nframes))
            offset+=p.nframes
    out=io.BytesIO()
    with wave.open(out,'wb') as w:
        w.setnchannels(params.nchannels);w.setsampwidth(params.sampwidth);w.setframerate(params.framerate)
        w.writeframes(b''.join(frames))
    return out.getvalue(),marks

# Optional local neural voice. eSpeak remains available as an explicitly enabled
# emergency backend, not the default audible experience.
import os
import threading
from pathlib import Path
from functools import lru_cache

_VOICE_LOCK=threading.Lock()
_VOICE_NAMES={"fr":"fr_FR-siwis-medium","en":"en_US-lessac-medium"}

@lru_cache(maxsize=2)
def _piper_voice(path):
    from piper import PiperVoice
    return PiperVoice.load(path)

def _neural_render(text,lang,cues):
    directory=Path(os.getenv("DECLIC_PIPER_DIR",str(Path(__file__).resolve().parents[1]/"voices")))
    path=directory/(_VOICE_NAMES[lang]+".onnx")
    if not path.is_file() or not Path(str(path)+".json").is_file():
        raise FileNotFoundError("Neural voice model not installed")
    chunks=split_cues(text,cues)
    # Avoid extra inter-fragment gaps: use actual frame counts for all cue offsets.
    frames=[];marks=[];params=None;offset=0
    with _VOICE_LOCK:
        voice=_piper_voice(str(path))
        for fragment,positions in chunks:
            buffer=io.BytesIO()
            with wave.open(buffer,"wb") as w:
                voice.synthesize_wav(fragment,w)
            with wave.open(io.BytesIO(buffer.getvalue()),"rb") as w:
                p=w.getparams()
                if params is None: params=p
                if (p.nchannels,p.sampwidth,p.framerate)!=(params.nchannels,params.sampwidth,params.framerate):
                    raise ValueError("Inconsistent neural voice format")
                data=w.readframes(p.nframes)
                if not data or p.nframes<1: raise ValueError("Empty neural voice fragment")
                marks.extend({"at":f,"time":round(offset/p.framerate,4)} for f in positions)
                frames.append(data);offset+=p.nframes
    out=io.BytesIO()
    with wave.open(out,"wb") as w:
        w.setnchannels(params.nchannels);w.setsampwidth(params.sampwidth);w.setframerate(params.framerate)
        w.writeframes(b"".join(frames))
    return out.getvalue(),marks

_cloud_retry_at=0.0

class CloudRateLimited(RuntimeError):
    def __init__(self,seconds=60):
        super().__init__("Cloud speech rate limited")
        self.seconds=max(15,min(600,seconds))

async def synthesize_preferred(text,lang,cues,cloud=False):
    global _cloud_retry_at
    # Validate user-controlled inputs before attempting a backend.
    split_cues(text,cues)
    if cloud and time.monotonic()>=_cloud_retry_at:
        try:
            audio,marks=await asyncio.wait_for(_gemini_render(text,lang,cues),35)
            return audio,marks,'gemini-neural'
        except CloudRateLimited as exc:
            _cloud_retry_at=max(_cloud_retry_at,time.monotonic()+exc.seconds)
            logging.getLogger(__name__).warning("Cloud voice rate limited; local voice used for %s seconds",exc.seconds)
        except (asyncio.TimeoutError,ImportError,FileNotFoundError,OSError,RuntimeError,ValueError,TypeError,KeyError,IndexError,AttributeError,wave.Error) as exc:
            logging.getLogger(__name__).warning('Cloud voice fallback: %s (%s)',type(exc).__name__,str(exc)[:100] if type(exc) in (ValueError,RuntimeError) else '')
    try:
        audio,marks=await asyncio.to_thread(_neural_render,text,lang,cues)
        return audio,marks,"piper-neural"
    except (ImportError,FileNotFoundError,OSError,RuntimeError,ValueError):
        if os.getenv("DECLIC_ALLOW_ESPEAK")=="1":
            audio,marks=await synthesize(text,lang,cues)
            return audio,marks,"espeak-fallback"
        raise FileNotFoundError("Neural voice unavailable; use browser speech") from None

async def _gemini_render(text,lang,cues):
    """Synthesize cue-aligned phrases; never send narration without explicit opt-in."""
    import base64
    import httpx
    key=os.getenv("GEMINI_API_KEY") or os.getenv("GEMEINI")
    if not key: raise FileNotFoundError("Gemini speech key unavailable")
    model=os.getenv("GEMINI_TTS_MODEL","gemini-3.8-flash-lite-tts")
    if not re.fullmatch(r"gemini-[a-zA-Z0-9.-]+-tts",model): raise ValueError("Invalid TTS model")
    chunks=split_cues(text,cues)
    # Bound cost and latency. More complex scenes retain exact local timing.
    # Coalesce excess reveal groups to a maximum of three phrases. All cue
    # keys survive; adjacent cues may share a phrase-start timestamp.
    while len(chunks)>3:
        i=min(range(len(chunks)-1),key=lambda i:len(chunks[i][0])+len(chunks[i+1][0]))
        a,aa=chunks[i];b,bb=chunks[i+1]
        chunks[i:i+2]=[(a+" "+b,sorted(set(aa+bb)))]
    async with httpx.AsyncClient(timeout=18) as client:
        semaphore=asyncio.Semaphore(1)
        async def phrase(fragment,positions):
            language="French" if lang=="fr" else "English"
            prompt=f"Read only the following {language} passage verbatim, warmly and naturally, as a patient teacher. Do not add words or read the instruction.\n\n"+fragment
            async with semaphore:
                try:
                    r=await client.post("https://generativelanguage.googleapis.com/v1beta/models/"+model+":generateContent",headers={"x-goog-api-key":key},json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"responseModalities":["AUDIO"],"speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":"Kore"}}}}})
                    if r.status_code==429:
                        try:delay=float(r.headers.get("Retry-After","60"))
                        except ValueError:delay=60
                        raise CloudRateLimited(delay if math.isfinite(delay) else 60)
                    r.raise_for_status()
                except httpx.HTTPError as e:
                    raise RuntimeError("Cloud speech unavailable; status="+str(e.response.status_code if isinstance(e,httpx.HTTPStatusError) else type(e).__name__)) from e
            parts=[p["inlineData"] for c in r.json().get("candidates",[]) for p in c.get("content",{}).get("parts",[]) if "inlineData" in p]
            if not parts: raise ValueError("Missing audio")
            raw=b"".join(base64.b64decode(part["data"],validate=True) for part in parts)
            if len(raw)>3_000_000: raise ValueError("Audio too large")
            mime=parts[0].get("mimeType","").lower()
            if raw.startswith(b"RIFF"):
                with wave.open(io.BytesIO(raw),"rb") as w:
                    if (w.getnchannels(),w.getsampwidth(),w.getframerate())!=(1,2,24000): raise ValueError("Unexpected voice format")
                    raw=w.readframes(w.getnframes())
            elif "l16" not in mime and "pcm" not in mime: raise ValueError("Unexpected audio type")
            rate=re.search(r"rate=(\d+)",mime)
            if rate and int(rate.group(1))!=24000: raise ValueError("Unexpected sample rate")
            if len(raw)<2400 or len(raw)%2: raise ValueError("Empty or malformed audio")
            return raw,positions
        # Stop immediately at the first rejected phrase; do not spend further quota.
        parts=[]
        for fragment,positions in chunks:
            parts.append(await phrase(fragment,positions))
    output=io.BytesIO()
    offset=0
    marks=[]
    with wave.open(output,"wb") as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000)
        for raw,positions in parts:
            marks.extend({"at":f,"time":round(offset/24000,4)} for f in positions)
            w.writeframes(raw);offset+=len(raw)//2
    return output.getvalue(),marks
