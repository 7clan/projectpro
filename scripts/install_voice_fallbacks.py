"""Install the two approved offline fallback voices, using pinned upstream runtime.
Run from the existing DÉCLIC Python environment. No API credentials are needed.
"""
import asyncio
import hashlib
import io
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import wave
import zipfile

ROOT=Path(__file__).resolve().parents[1]
BASE="https://github.com/kyutai-labs/pocket-tts/releases/download/v4.0.1/"
def download(url,path):
    with urllib.request.urlopen(url,timeout=120) as src,path.open("wb") as dst:
        while block:=src.read(1024*1024):
            dst.write(block)

def main():
    os.chdir(ROOT)
    if platform.machine().lower() not in ("amd64","x86_64"):
        raise SystemExit("This installer supports x86-64 Windows and Linux.")
    windows=os.name=="nt"
    if not windows and platform.system()!="Linux":raise SystemExit("Unsupported operating system")
    runtime="pocket-tts.exe" if windows else "pocket-tts"
    archive="pocket-tts-3.3.0-x86_64-pc-windows-msvc.zip" if windows else "pocket-tts-3.3.0-x86_64-unknown-linux-gnu.tar.gz"
    directory=ROOT/"voices"/"pocket"
    directory.mkdir(parents=True,exist_ok=True)
    executable=directory/runtime
    if not executable.is_file():
        with tempfile.TemporaryDirectory() as folder:
            bundle=Path(folder)/archive
            sums=Path(folder)/"SHA256SUMS"
            download(BASE+"SHA256SUMS",sums)
            expected=next(line.split()[0] for line in sums.read_text().splitlines() if line.split()[-1].lstrip("*")==archive)
            download(BASE+archive,bundle)
            if hashlib.sha256(bundle.read_bytes()).hexdigest()!=expected:
                raise RuntimeError("Pocket runtime checksum mismatch")
            if windows:
                with zipfile.ZipFile(bundle) as z:
                    members=[n for n in z.namelist() if Path(n).name==runtime]
                    assert len(members)==1
                    executable.write_bytes(z.read(members[0]))
            else:
                with tarfile.open(bundle) as t:
                    members=[m for m in t.getmembers() if m.isfile() and Path(m.name).name==runtime]
                    assert len(members)==1
                    executable.write_bytes(t.extractfile(members[0]).read())
                executable.chmod(0o755)
    subprocess.run([sys.executable,"-m","pip","install","-r","requirements-voice.txt"],check=True)
    subprocess.run([sys.executable,"-m","piper.download_voices","--data-dir",str(ROOT/"voices"),"fr_FR-tom-medium"],check=True)
    # Initialize George's public model files before the first lesson. The
    # one-time download may take longer than the live narration deadline.
    env={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ("KEY","TOKEN","SECRET","PASSWORD","GEMEINI","OPENROUTER","BAZAARLINK","SOME"))}
    env.update({"RAYON_NUM_THREADS":"2","OMP_NUM_THREADS":"2","HF_HUB_DISABLE_TELEMETRY":"1"})
    with tempfile.TemporaryDirectory() as folder:
        subprocess.run([str(executable),"generate","--language","english_2026-04","--voice","george","--text","Welcome to your lesson.","--output-path",str(Path(folder)/"warmup.wav")],check=True,env=env,timeout=600)
    sys.path.insert(0,str(ROOT))
    from app.voice import synthesize_preferred
    async def verify():
        for lang,text,expected in (("en","Let us explore the forces acting on this beam.","pocket-george"),("fr","Observons les forces qui agissent sur cette poutre.","piper-fr_FR-tom-medium")):
            audio,marks,backend=await asyncio.wait_for(synthesize_preferred(text,lang,[0,.5],cloud=False),45)
            assert backend==expected,(lang,backend)
            with wave.open(io.BytesIO(audio),"rb") as wav:
                frames=wav.readframes(wav.getnframes())
                assert len(frames)>2400 and any(frames)
            assert marks and {m["at"] for m in marks}=={0,.5}
            print("PASS",lang,backend,flush=True)
            (directory/("verified-"+lang+".wav")).write_bytes(audio)
    asyncio.run(verify())
    print("George and Tom are ready. Restart DÉCLIC.")
if __name__=="__main__":
    main()
