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
_EXTRA_VOICES={"en_US-amy-medium":"en","en_US-ryan-medium":"en","en_GB-alba-medium":"en","fr_FR-tom-medium":"fr"}
_KOKORO_VOICES={"kokoro-michael":"am_michael","kokoro-michael-smooth":"am_michael"}
_POCKET_VOICES={"pocket-alba":"alba","pocket-george":"george"}
def _pocket_executable():
    directory=Path(__file__).resolve().parents[1]/"voices"/"pocket"
    candidate=directory/("pocket-tts.exe" if os.name=="nt" else "pocket-tts")
    return str(candidate) if candidate.is_file() else None

def _pocket_render(text,lang,cues,voice_name):
    """Optional local standalone engine, no API credentials or custom references."""
    import subprocess
    import tempfile
    import numpy as np
    executable=_pocket_executable()
    if not executable:raise FileNotFoundError("Pocket TTS executable not installed")
    # One or two longer phrases retain prosody. Group boundaries are aligned
    # to actual frames; coalesced reveal cues share the phrase start.
    chunks=split_cues(text,cues)
    while len(chunks)>1 and (len(chunks)>2 or any(len(x[0].split())<7 for x in chunks)):
        i=min(range(len(chunks)-1),key=lambda i:len(chunks[i][0])+len(chunks[i+1][0]))
        a,aa=chunks[i];b,bb=chunks[i+1]
        chunks[i:i+2]=[(a+" "+b,sorted(set(aa+bb)))]
    env={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ("KEY","TOKEN","SECRET","PASSWORD","GEMEINI","OPENROUTER","BAZAARLINK","SOME"))}
    env.update({"RAYON_NUM_THREADS":"2","OMP_NUM_THREADS":"2","MKL_NUM_THREADS":"2","HF_HUB_DISABLE_TELEMETRY":"1"})
    output=io.BytesIO();marks=[];offset=0;deadline=time.monotonic()+16
    with _VOICE_LOCK,tempfile.TemporaryDirectory() as folder,wave.open(output,"wb") as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000)
        for i,(fragment,positions) in enumerate(chunks):
            path=Path(folder)/f"phrase-{i}.wav"
            try:
                subprocess.run([executable,"generate","--language","english_2026-04","--voice",_POCKET_VOICES[voice_name],"--text="+fragment,"--output-path",str(path),"--sampler-decode-steps","3"],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=max(.1,deadline-time.monotonic()),check=True)
            except (subprocess.SubprocessError,OSError) as exc:
                logging.getLogger(__name__).warning("Pocket synthesis failed: %s",type(exc).__name__)
                raise FileNotFoundError("Pocket voice unavailable") from exc
            with wave.open(str(path),"rb") as src:
                if (src.getnchannels(),src.getsampwidth(),src.getframerate())!=(1,2,24000):raise ValueError("Unexpected Pocket audio format")
                raw=src.readframes(src.getnframes())
            samples=np.frombuffer(raw,dtype="<i2")
            if len(samples)<2400 or not np.any(np.abs(samples.astype(np.int32))>100):raise ValueError("Empty Pocket audio")
            marks.extend({"at":f,"time":round(offset/24000,4)} for f in positions)
            w.writeframes(raw);offset+=len(samples)
    return output.getvalue(),marks

def _kokoro_paths():
    directory=Path(os.getenv("DECLIC_KOKORO_DIR",str(Path(__file__).resolve().parents[1]/"voices"/"kokoro")))
    return directory/"kokoro-v1.0.onnx",directory/"voices-v1.0.bin"

def _kokoro_available():
    import importlib.util
    return all(p.is_file() for p in _kokoro_paths()) and importlib.util.find_spec("kokoro_onnx") is not None

@lru_cache(maxsize=1)
def _kokoro_model(model_path,voices_path):
    import onnxruntime as ort
    from kokoro_onnx import Kokoro
    # Bound CPU threads to avoid competing with the browser on a small laptop.
    options=ort.SessionOptions()
    options.intra_op_num_threads=2
    options.inter_op_num_threads=1
    session=ort.InferenceSession(model_path,sess_options=options,providers=["CPUExecutionProvider"])
    return Kokoro.from_session(session,voices_path)

def _soften_kokoro_pauses(samples,rate=24000):
    """Reduce only sustained low-energy pauses; preserve samples and cue timing."""
    import numpy as np
    samples=np.asarray(samples,dtype=np.float32).reshape(-1)
    # 20 ms RMS windows, requiring 160 ms of sustained quiet. Protect 40 ms
    # beside speech; ramp attenuation instead of a hard gate or deleting samples.
    block=rate//50
    count=len(samples)//block
    if count<8:return samples.copy()
    frames=samples[:count*block].reshape(count,block)
    rms=np.sqrt(np.mean(frames*frames,axis=1))
    quiet=rms<10**(-48/20)
    edges=np.flatnonzero(np.diff(np.r_[False,quiet,False]))
    gain=np.ones(len(samples),dtype=np.float32)
    for start,end in zip(edges[::2],edges[1::2]):
        if end-start<8:continue
        a=(start+2)*block
        b=(end-2)*block
        ramp=min(block*2,(b-a)//2)
        if ramp<1:continue
        floor=np.float32(10**(-18/20))
        gain[a:a+ramp]=1-(1-floor)*(.5-.5*np.cos(np.linspace(0,np.pi,ramp)))
        gain[a+ramp:b-ramp]=floor
        gain[b-ramp:b]=floor+(1-floor)*(.5-.5*np.cos(np.linspace(0,np.pi,ramp)))
    return samples*gain

def _kokoro_render(text,lang,cues,voice_name):
    import numpy as np
    if not _kokoro_available():raise FileNotFoundError("Kokoro voice model not installed")
    smooth=voice_name.endswith("-smooth")
    chunks=split_cues(text,cues)
    # Prefer sentence-sized narration in smooth mode when the cue plan has
    # only one reveal. Keep multi-cue grouping/timing for animated examples.
    # Keep longer phrases for prosody; all original cue keys remain represented.
    while len(chunks)>1 and (len(chunks)>3 or any(len(x[0].split())<6 for x in chunks)):
        i=min(range(len(chunks)-1),key=lambda i:len(chunks[i][0])+len(chunks[i+1][0]))
        a,aa=chunks[i];b,bb=chunks[i+1]
        chunks[i:i+2]=[(a+" "+b,sorted(set(aa+bb)))]
    output=io.BytesIO();marks=[];offset=0
    with _VOICE_LOCK:
        model=_kokoro_model(*(str(p) for p in _kokoro_paths()))
        with wave.open(output,"wb") as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000)
            for fragment,positions in chunks:
                samples,rate=model.create(fragment,voice=_KOKORO_VOICES[voice_name],speed=.94 if smooth else 1.0,lang="en-us")
                samples=np.asarray(samples,dtype=np.float32).reshape(-1)
                if rate!=24000 or samples.size<2400 or not np.isfinite(samples).all() or np.max(np.abs(samples))<.001:
                    raise ValueError("Invalid Kokoro audio")
                if smooth:samples=_soften_kokoro_pauses(samples,rate)
                raw=(np.clip(samples,-1,1)*32767).astype("<i2").tobytes()
                marks.extend({"at":f,"time":round(offset/24000,4)} for f in positions)
                w.writeframes(raw);offset+=samples.size
    return output.getvalue(),marks

def _piper_installed(voice_name):
    directory=Path(os.getenv("DECLIC_PIPER_DIR",str(Path(__file__).resolve().parents[1]/"voices")))
    return (directory/(voice_name+".onnx")).is_file() and (directory/(voice_name+".onnx.json")).is_file()

def voice_choices():
    return [{"id":name,"lang":lang,"installed":_piper_installed(name)} for name,lang in _EXTRA_VOICES.items()]+[{"id":name,"lang":"en","installed":_kokoro_available()} for name in _KOKORO_VOICES]+[{"id":name,"lang":"en","installed":_pocket_executable() is not None} for name in _POCKET_VOICES]


@lru_cache(maxsize=2)
def _piper_voice(path):
    from piper import PiperVoice
    return PiperVoice.load(path)

def _neural_render(text,lang,cues,voice_name=None):
    directory=Path(os.getenv("DECLIC_PIPER_DIR",str(Path(__file__).resolve().parents[1]/"voices")))
    path=directory/((voice_name or _VOICE_NAMES[lang])+".onnx")
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
_router_voice_retry_at=0.0

class CloudRateLimited(RuntimeError):
    def __init__(self,seconds=60):
        super().__init__("Cloud speech rate limited")
        self.seconds=max(15,min(600,seconds))

async def synthesize_preferred(text,lang,cues,cloud=False,voice_name=None):
    global _cloud_retry_at,_router_voice_retry_at
    cloud=cloud and os.getenv('DECLIC_LOCAL_ONLY')!='1'
    # Validate user-controlled inputs before attempting a backend.
    split_cues(text,cues)
    if isinstance(voice_name,str) and voice_name in _POCKET_VOICES:
        if lang!="en":raise ValueError("Unsupported voice for lesson language")
        audio,marks=await asyncio.to_thread(_pocket_render,text,lang,cues,voice_name)
        return audio,marks,voice_name
    if isinstance(voice_name,str) and voice_name in _KOKORO_VOICES:
        if lang!="en":raise ValueError("Unsupported voice for lesson language")
        try:
            audio,marks=await asyncio.to_thread(_kokoro_render,text,lang,cues,voice_name)
        except (ImportError,OSError,RuntimeError) as exc:
            raise FileNotFoundError("Kokoro voice unavailable") from exc
        return audio,marks,voice_name
    if voice_name is not None:
        if not isinstance(voice_name,str) or _EXTRA_VOICES.get(voice_name)!=lang:
            raise ValueError("Unsupported voice for lesson language")
        audio,marks=await asyncio.to_thread(_neural_render,text,lang,cues,voice_name)
        return audio,marks,"piper-"+voice_name
    # Prefer the user's proven cloud engine, then Gemini. Reserve time for
    # local synthesis within the API's 45-second response deadline.
    if cloud and time.monotonic()>=_router_voice_retry_at and (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER")):
        try:
            audio,marks=await asyncio.wait_for(_openrouter_render(text,lang,cues),10)
            return audio,marks,"openrouter-heygen-neural"
        except CloudRateLimited as exc:
            _router_voice_retry_at=time.monotonic()+exc.seconds
            logging.getLogger(__name__).warning("OpenRouter speech rate limited; trying next voice")
        except (asyncio.TimeoutError,FileNotFoundError,OSError,RuntimeError,ValueError,TypeError,KeyError,IndexError,AttributeError,wave.Error) as exc:
            _router_voice_retry_at=time.monotonic()+60
            logging.getLogger(__name__).warning("OpenRouter speech fallback: %s",type(exc).__name__)
    if cloud and time.monotonic()>=_cloud_retry_at:
        try:
            audio,marks=await asyncio.wait_for(_gemini_render(text,lang,cues),10)
            return audio,marks,'gemini-neural'
        except CloudRateLimited as exc:
            _cloud_retry_at=max(_cloud_retry_at,time.monotonic()+exc.seconds)
            logging.getLogger(__name__).warning("Cloud voice rate limited; local voice used for %s seconds",exc.seconds)
        except (asyncio.TimeoutError,ImportError,FileNotFoundError,OSError,RuntimeError,ValueError,TypeError,KeyError,IndexError,AttributeError,wave.Error) as exc:
            logging.getLogger(__name__).warning('Cloud voice fallback: %s (%s)',type(exc).__name__,str(exc)[:100] if type(exc) in (ValueError,RuntimeError) else '')
    if lang=="en" and _pocket_executable():
        try:
            audio,marks=await asyncio.wait_for(asyncio.to_thread(_pocket_render,text,lang,cues,"pocket-george"),18)
            return audio,marks,"pocket-george"
        except (asyncio.TimeoutError,ImportError,OSError,RuntimeError,ValueError,wave.Error) as exc:
            logging.getLogger(__name__).warning("George unavailable; trying installed fallback: %s",type(exc).__name__)
    if lang=="fr" and _piper_installed("fr_FR-tom-medium"):
        try:
            audio,marks=await asyncio.to_thread(_neural_render,text,lang,cues,"fr_FR-tom-medium")
            return audio,marks,"piper-fr_FR-tom-medium"
        except (ImportError,OSError,RuntimeError,ValueError,wave.Error) as exc:
            logging.getLogger(__name__).warning("Tom unavailable; trying installed fallback: %s",type(exc).__name__)
    if lang=="en" and _kokoro_available():
        try:
            audio,marks=await asyncio.wait_for(asyncio.to_thread(_kokoro_render,text,lang,cues,"kokoro-michael-smooth"),10)
            return audio,marks,"kokoro-michael-smooth"
        except (asyncio.TimeoutError,ImportError,OSError,RuntimeError,ValueError,wave.Error) as exc:
            logging.getLogger(__name__).warning("Michael unavailable; trying Piper: %s",type(exc).__name__)
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


async def _openrouter_render(text,lang,cues):
    """Free-only HeyGen speech; actual audio frame counts drive reveal timing."""
    import httpx
    key=os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER")
    if not key:raise FileNotFoundError("OpenRouter key unavailable")
    # Fixed documented zero-price model and provider. Never fall back to paid speech.
    model="heygen/heygen-voice-1-turbo:free"
    chunks=split_cues(text,cues)
    while len(chunks)>3:
        i=min(range(len(chunks)-1),key=lambda i:len(chunks[i][0])+len(chunks[i+1][0]))
        a,aa=chunks[i];b,bb=chunks[i+1]
        chunks[i:i+2]=[(a+" "+b,sorted(set(aa+bb)))]
    marks=[];offset=0
    output=io.BytesIO()
    async with httpx.AsyncClient(timeout=12) as client:
        with wave.open(output,"wb") as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(44100)
            for fragment,positions in chunks:
                try:
                    r=await client.post("https://openrouter.ai/api/v1/audio/speech",
                        headers={"Authorization":"Bearer "+key},
                        json={"model":model,"input":fragment,"voice":"nadine","response_format":"pcm","provider":{"only":["heygen"],"allow_fallbacks":False}})
                    if r.status_code==429:
                        try:delay=float(r.headers.get("Retry-After","60"))
                        except ValueError:delay=60
                        raise CloudRateLimited(delay if math.isfinite(delay) else 60)
                    r.raise_for_status()
                except httpx.HTTPError as exc:
                    raise RuntimeError("OpenRouter speech unavailable") from exc
                raw=r.content
                mime=r.headers.get("content-type","").lower()
                if not (mime.startswith("audio/") or mime.startswith("application/octet-stream")):
                    raise ValueError("Unexpected speech content type")
                if raw.startswith(b"RIFF"):
                    with wave.open(io.BytesIO(raw),"rb") as src:
                        if (src.getnchannels(),src.getsampwidth(),src.getframerate())!=(1,2,44100):
                            raise ValueError("Unexpected speech format")
                        raw=src.readframes(src.getnframes())
                elif "mpeg" in mime or "mp3" in mime or raw.startswith(b"ID3"):
                    raise ValueError("Compressed audio instead of PCM")
                if len(raw)<4410 or len(raw)>4_000_000 or len(raw)%2:
                    raise ValueError("Malformed speech audio")
                if not any(raw):raise ValueError("Silent audio")
                marks.extend({"at":f,"time":round(offset/44100,4)} for f in positions)
                w.writeframes(raw);offset+=len(raw)//2
    return output.getvalue(),marks
