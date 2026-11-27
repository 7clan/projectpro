"""Record real Studio local speech and direct bilingual A/B samples."""
from browser_wait import wait_for
from pathlib import Path
import asyncio,io,json,os,subprocess,time,wave,array
from playwright.sync_api import sync_playwright,expect
from app.voice import synthesize_preferred
from app.kokoro_voice import synthesize_kokoro
OUT=Path("kokoro-evidence");OUT.mkdir(exist_ok=True)
texts={"en":"A moment is the turning effect of a force. The farther the force acts from the pivot, the greater the moment.","fr":"Un moment est l'effet de rotation d'une force. Plus la force agit loin du pivot, plus le moment est grand."}
def inspect(audio,marks):
    with wave.open(io.BytesIO(audio)) as w:
        duration=w.getnframes()/w.getframerate()
        samples=array.array("h",w.readframes(w.getnframes()))
    assert duration>0.5 and max(map(abs,samples),default=0)>100
    assert all(0<=m["time"]<duration for m in marks)
    assert {m["at"] for m in marks}=={0,.4,.7}
    return duration
async def samples():
    results=[]
    for lang,text in texts.items():
        for name,fn in [("kokoro",synthesize_kokoro),("piper",synthesize_preferred)]:
            t=time.monotonic()
            audio,marks,backend=await fn(text,lang,[0,.4,.7])
            assert backend==name+"-neural",backend
            duration=inspect(audio,marks)
            info={"lang":lang,"backend":backend,"generation_seconds":round(time.monotonic()-t,2),"audio_seconds":round(duration,2)}
            results.append(info);print("PASS SAMPLE",json.dumps(info),flush=True)
            (OUT/f"{lang}-{name}.wav").write_bytes(audio)
    (OUT/"sample-results.json").write_text(json.dumps(results,indent=2))
asyncio.run(samples())
if os.getenv("KOKORO_SAMPLES_ONLY")=="1":raise SystemExit(0)
records=[];errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=False,ignore_default_args=["--mute-audio"],args=["--no-sandbox","--window-size=1440,900","--window-position=0,0","--start-maximized","--autoplay-policy=no-user-gesture-required"])
    ctx=browser.new_context(no_viewport=True)
    page=ctx.new_page()
    page.on("pageerror",lambda e:errors.append(str(e)))
    def observe(r):
        if r.url.endswith("/api/studio/audio"):
            records.append({"status":r.status,"backend":r.headers.get("x-studio-voice"),"lang":r.request.post_data_json.get("lang"),"engine":r.request.post_data_json.get("voice_engine")})
    page.on("response",observe)
    rec=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-y","-thread_queue_size","512","-f","x11grab","-framerate","20","-video_size","1440x900","-i",os.environ["DISPLAY"],"-thread_queue_size","512","-f","pulse","-i","declic.monitor","-c:v","libx264","-preset","ultrafast","-crf","23","-pix_fmt","yuv420p","-c:a","aac","-movflags","+faststart",str(OUT/"DECLIC-kokoro-local-studio.mp4")],stdin=subprocess.PIPE)
    try:
        page.goto("http://127.0.0.1:8000")
        page.locator("#demo-login").click()
        wait_for(page,"state.challenge!==null && !state.labBusy")
        for lang,text in texts.items():
            if page.evaluate("state.language")!=lang:page.locator("#language").click()
            page.locator('[data-view="studio"]').click()
            page.locator("#studio-consent").uncheck()
            page.locator("#studio-voice").check()
            page.locator("#studio-voice-engine").select_option("kokoro")
            page.locator("#studio-generative").uncheck()
            page.locator("#studio-question").fill("Explain the moment of a force and the lever arm" if lang=="en" else "Explique le moment d'une force et le bras de levier")
            with page.expect_response(lambda r:r.request.method=="POST" and r.url.endswith("/api/studio")) as e:
                page.locator("#studio-send").click()
            assert e.value.status==200
            wait_for(page,"document.querySelector('#studio-svg').dataset.audio==='playing'",timeout=90000)
            assert page.locator("#studio-svg").get_attribute("data-voice-backend")=="kokoro-neural"
            page.screenshot(path=str(OUT/f"{lang}-studio.png"))
            wait_for(page,"document.querySelector('#studio-play').textContent.includes('Play')",timeout=200000)
            assert page.locator("#studio-svg").get_attribute("data-audio")=="ended"
            print("PASS STUDIO",lang,flush=True)
        assert all(r["backend"]=="kokoro-neural" and r["status"]==200 for r in records),records
        assert {r["lang"] for r in records}=={"fr","en"}
        assert not errors,errors
    finally:
        rec.communicate(b"q",timeout=20)
        ctx.close();browser.close()
        (OUT/"browser-results.json").write_text(json.dumps({"audio":records,"errors":errors},indent=2))
