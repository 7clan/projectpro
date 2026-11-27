"""Local speech with exact phrase-level reveal markers."""
import asyncio
import io
import math
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

async def synthesize_preferred(text,lang,cues):
    # Validate user-controlled inputs before attempting a backend.
    split_cues(text,cues)
    try:
        audio,marks=await asyncio.to_thread(_neural_render,text,lang,cues)
        return audio,marks,"piper-neural"
    except (ImportError,FileNotFoundError,OSError,RuntimeError,ValueError):
        if os.getenv("DECLIC_ALLOW_ESPEAK")=="1":
            audio,marks=await synthesize(text,lang,cues)
            return audio,marks,"espeak-fallback"
        raise FileNotFoundError("Neural voice unavailable; use browser speech") from None
