"""Record real Studio playback, with actual audio captured from Chromium's PulseAudio sink.
The guided lesson is intentionally controlled so each voice reads identical text.
No voice mocks, no overdubbing, no generated lesson injection.
"""
import os, pathlib, subprocess, time, json, re, urllib.request, io, wave, array, math
from playwright.sync_api import sync_playwright
from browser_wait import wait_for
out=pathlib.Path("kokoro-evidence");out.mkdir(exist_ok=True)
for _ in range(100):
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/api/health",timeout=1)
        break
    except Exception:time.sleep(.3)
else:raise RuntimeError("Server unavailable")
cases=[("en",["kokoro-bella","kokoro-bella-smooth","kokoro-michael","kokoro-michael-smooth"])]
results=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=False,ignore_default_args=["--mute-audio"],args=["--window-size=1440,900","--window-position=0,0","--start-maximized","--autoplay-policy=no-user-gesture-required"])
    for lang,voices in cases:
        ctx=browser.new_context(no_viewport=True)
        page=ctx.new_page();errors=[]
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto("http://127.0.0.1:8000")
        page.locator("#demo-login").click()
        wait_for(page,"!!state.user && !!state.aiMode && document.querySelector('#auth-overlay').hidden")
        if page.evaluate("state.language")!=lang:page.locator("#language").click()
        page.locator('[data-view="studio"]').click()
        page.locator("#studio-voice").uncheck()
        page.locator("#studio-generative").uncheck()
        page.locator("#studio-consent").uncheck()
        page.locator("#studio-question").fill("Explain support reactions in a beam." if lang=="en" else "Explique les réactions aux appuis d'une poutre.")
        with page.expect_response(lambda r:r.url.endswith("/api/studio") and r.request.method=="POST",timeout=30000) as event:page.locator("#studio-send").click()
        lesson=event.value.json();assert lesson["steps"],lesson
        (out/(lang+"-lesson.json")).write_text(json.dumps(lesson,ensure_ascii=False,indent=2))
        wait_for(page,"document.querySelectorAll('#studio-steps button').length>0 && !document.querySelector('#studio-send').disabled")
        if "Stop" in page.locator("#studio-play").inner_text():page.locator("#studio-play").click()
        page.locator("#studio-voice-engine").select_option("local")
        for voice in voices:
            rec=None;result={"voice":voice,"lang":lang,"lesson_mode":lesson.get("mode")}
            try:
                page.locator("#studio-steps button").nth(1).click()
                page.locator("#studio-voice-profile").select_option(voice,timeout=15000)
                page.locator("#studio-voice").check()
                audio_responses=[]
                def capture_audio(r):
                    if r.url.endswith("/api/studio/audio") and r.request.method=="POST":audio_responses.append((r.status,r.headers.get("x-studio-voice")))
                page.on("response",capture_audio)
                page.locator("#studio-svg").evaluate("(el)=>{el.dataset.audio='waiting';el.dataset.voiceBackend='';}")
                rec=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-y","-thread_queue_size","512","-f","x11grab","-framerate","20","-video_size","1440x900","-i",os.environ["DISPLAY"],"-thread_queue_size","512","-f","pulse","-i","declic.monitor","-c:v","libx264","-preset","ultrafast","-crf","24","-pix_fmt","yuv420p","-c:a","aac","-movflags","+faststart",str(out/(voice+".mp4"))],stdin=subprocess.PIPE)
                time.sleep(1)
                with page.expect_response(lambda r:r.url.endswith("/api/studio/audio") and r.request.method=="POST",timeout=55000) as audio_event:
                    page.locator("#studio-play").click()
                response=audio_event.value
                assert response.status==200,response.status
                assert response.headers["x-studio-voice"]==voice,response.headers
                raw=response.body()
                (out/(voice+".wav")).write_bytes(raw)
                marks=json.loads(response.headers["x-studio-cues"])
                with wave.open(io.BytesIO(raw),"rb") as w:
                    duration=w.getnframes()/w.getframerate()
                    samples=array.array("h",w.readframes(w.getnframes()))
                assert duration>1 and max(abs(x) for x in samples)>500
                assert marks and all(0<=m["time"]<duration for m in marks)
                wait_for(page,"document.querySelector('#studio-svg').dataset.audio==='playing'",timeout=15000)
                page.locator("#studio-voice-profile").scroll_into_view_if_needed()
                page.screenshot(path=str(out/(voice+".png")))
                wait_for(page,"document.querySelector('#studio-play').textContent.includes('Play') && document.querySelector('#studio-svg').dataset.audio==='ended'",timeout=70000)
                assert len(audio_responses)==len(lesson["steps"])-1 and all(x==(200,voice) for x in audio_responses),audio_responses
                result["scene_audio_responses"]=audio_responses
                time.sleep(.5);rec.communicate(b"q",timeout=15);rec=None
                check=subprocess.run(["ffmpeg","-hide_banner","-i",str(out/(voice+".mp4")),"-af","volumedetect","-vn","-f","null","-"],capture_output=True,text=True)
                m=re.search(r"max_volume: (-?[0-9.]+)",check.stderr)
                assert m and float(m.group(1))>-45,"Silent recording"
                assert not errors,errors
                result.update({"pass":True,"backend":response.headers["x-studio-voice"],"duration_seconds":round(duration,2),"max_volume_db":float(m.group(1)),"cues":marks})
                print("PASS",voice,result["duration_seconds"],result["max_volume_db"],flush=True)
            except Exception as exc:
                result.update({"pass":False,"error":str(exc)[:500]})
                print("FAIL",voice,result["error"],flush=True)
            finally:
                page.remove_listener("response",capture_audio) if "capture_audio" in locals() else None
                if rec:
                    try:rec.communicate(b"q",timeout=15)
                    except Exception:rec.kill()
                results.append(result)
                (out/"results.json").write_text(json.dumps(results,indent=2))
        ctx.close()
    browser.close()
assert all(r["pass"] for r in results) and len(results)==4,results
