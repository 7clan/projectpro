"""Real Chromium recording, never injects a lesson or substitutes mocked audio."""
import json, os, pathlib, subprocess, time, urllib.request, re
from playwright.sync_api import sync_playwright
out=pathlib.Path("acceptance");out.mkdir(exist_ok=True)
for i in range(80):
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/api/health")
        break
    except Exception:
        time.sleep(.3)
cases=[
    ("geometry","Montre le théorème de Pythagore sur un triangle rectangle 3, 4, 5, avec les aires 9, 16, 25 et des couleurs distinctes."),
    ("physics","Montre la deuxième loi de Newton pour une masse de 2 kg et une force de 6 N, avec une accélération de 3 m/s² et des vecteurs animés.")
]
results=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=False,ignore_default_args=["--mute-audio"],args=["--window-size=1440,900","--window-position=0,0","--start-maximized","--autoplay-policy=no-user-gesture-required"])
    for label,question in cases:
        context=browser.new_context(no_viewport=True)
        page=context.new_page()
        errors=[]
        page.on("pageerror",lambda e:errors.append(str(e)))
        rec=None
        result={"subject":label,"generated":False}
        try:
            page.goto("http://127.0.0.1:8000")
            page.locator("#demo-login").click()
            page.wait_for_function("document.querySelector('#ai-mode').textContent.includes('gemini') || document.querySelector('#ai-mode').textContent.includes('openrouter')")
            page.locator('[data-view="studio"]').click()
            page.locator("#studio-consent").check()
            page.locator("#studio-voice").check()
            page.evaluate("""() => {
                window.studioTrace=[];
                document.querySelector('#studio-svg').addEventListener('studio:reveal',e=>window.studioTrace.push({...e.detail,wall:performance.now()}));
            }""")
            page.locator("#studio-question").fill(question)
            with page.expect_response(lambda r:'/api/studio' in r.url and r.request.method=='POST' and r.url.endswith('/api/studio'),timeout=330000) as event:
                page.locator("#studio-send").click()
            lesson=event.value.json()
            (out/(label+".json")).write_text(json.dumps(lesson,ensure_ascii=False,indent=2))
            assert lesson.get("mode")=="live_ai" and lesson.get("visual_mode")=="generated",lesson.get("notice")
            result["generated"]=True
            result["model"]=lesson.get("model")
            # Replay from the beginning so both streams start together and no generation wait dominates the clip.
            page.locator("#studio-play").click()
            page.locator("#studio-steps button").first.click()
            page.evaluate("window.studioTrace=[]")
            rec=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-y","-thread_queue_size","512","-f","x11grab","-framerate","20","-video_size","1440x900","-i",os.environ["DISPLAY"],"-thread_queue_size","512","-f","pulse","-i","declic.monitor","-c:v","libx264","-preset","ultrafast","-crf","25","-pix_fmt","yuv420p","-c:a","aac","-movflags","+faststart",str(out/(label+".mp4"))],stdin=subprocess.PIPE)
            time.sleep(1)
            page.locator("#studio-play").click()
            page.wait_for_function("document.querySelector('#studio-svg').dataset.audio==='playing'",timeout=30000)
            assert int(page.locator("#studio-svg").get_attribute("data-cue-count") or 0)>0
            page.wait_for_function("document.querySelector('#studio-play').textContent.includes('Play')",timeout=150000)
            assert page.locator("#studio-svg").get_attribute("data-audio")=="ended"
            trace=page.evaluate("window.studioTrace")
            (out/(label+".trace.json")).write_text(json.dumps(trace,ensure_ascii=False,indent=2))
            assert any(e["at"]>0 and e["audioTime"] is not None and e["audioTime"]>0 for e in trace),"No synchronized reveal during audio"
            result["synchronized_reveal"]=True
            page.screenshot(path=str(out/(label+"-final.png")))
            time.sleep(1)
            rec.communicate(b"q",timeout=20);rec=None
            f=out/(label+".mp4")
            check=subprocess.run(["ffmpeg","-hide_banner","-i",str(f),"-af","volumedetect","-vn","-f","null","-"],capture_output=True,text=True)
            match=re.search(r"max_volume: (-?[0-9.]+)",check.stderr)
            result["audible"]=bool(match and float(match.group(1))>-50)
            assert result["audible"],"Silent recording"
            assert not errors,errors
            print("PASS",label,result,flush=True)
        except Exception as exc:
            result["error"]=str(exc)[:300]
            print("FAIL",label,result["error"],flush=True)
        finally:
            if rec:
                try: rec.communicate(b"q",timeout=15)
                except Exception: rec.kill()
            context.close()
            results.append(result)
            (out/"results.json").write_text(json.dumps(results,indent=2))
    browser.close()
assert all(r.get("generated") and r.get("synchronized_reveal") and r.get("audible") for r in results),results
