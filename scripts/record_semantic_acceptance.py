from browser_wait import wait_for
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
    ("hydraulics","Explain how a hydraulic press works using Pascal's principle. Animate two pistons of different sizes connected by a fluid. Show how an input force of 50 N applied to a piston of 5 cm² produces an output force on a piston of 100 cm²."),
    ("optics","Explain refraction of light from air into glass. Show an incident ray, a normal, a refracted ray bending toward the normal, and a separate case of glass into air bending away from the normal. Animate and label the stages.")
]
fixture_mode=False
fixtures=None
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
            wait_for(page,"document.querySelector('#ai-mode').textContent.includes('gemini') || document.querySelector('#ai-mode').textContent.includes('openrouter') || document.querySelector('#ai-mode').textContent.includes('bazaarlink') || document.querySelector('#ai-mode').textContent.includes('ollama')")
            page.locator('[data-view="studio"]').click()
            # In cloud-only CI the app correctly disables the sole-mode selector.
            # Do not bypass the UI: verify its selected mode or select it when enabled.
            wait_for(page,"document.querySelector('#studio-ai-mode').value==='cloud' || (!document.querySelector('#studio-ai-mode').disabled && !document.querySelector('#studio-ai-mode option[value=cloud]').disabled)")
            if page.locator("#studio-ai-mode").input_value()!="cloud":
                page.locator("#studio-ai-mode").select_option("cloud")
            assert page.locator("#studio-ai-mode").input_value()=="cloud"
            if page.evaluate("state.language")!="en":page.locator("#language").click()
            assert page.evaluate("state.language")=="en"
            if os.getenv("DECLIC_LOCAL_ONLY")!="1":page.locator("#studio-consent").check()
            else:page.locator("#studio-consent").uncheck()
            # Avoid spending speech quota on autoplay before recording.
            page.locator("#studio-voice").uncheck()
            page.evaluate("""() => {
                window.studioTrace=[];
                document.querySelector('#studio-svg').addEventListener('studio:reveal',e=>window.studioTrace.push({...e.detail,wall:performance.now()}));
            }""")
            if fixture_mode:
                from app.whiteboard import validate_board
                steps=validate_board(json.dumps(fixtures[label]))
                replay={"mode":"live_ai","visual_mode":"generated","steps":steps,"sources":[],"notice":"REFERENCE REPLAY — AI-authored test lesson; no live API call."}
                page.route("**/api/studio",lambda route:route.fulfill(json=replay))
            page.locator("#studio-question").fill(question)
            with page.expect_response(lambda r:'/api/studio' in r.url and r.request.method=='POST' and r.url.endswith('/api/studio'),timeout=330000) as event:
                page.locator("#studio-send").click()
            lesson=event.value.json()
            (out/(label+".json")).write_text(json.dumps(lesson,ensure_ascii=False,indent=2))
            assert lesson.get("mode")=="live_ai" and lesson.get("visual_mode")=="generated",lesson.get("notice")
            result["generated"]=not fixture_mode
            result["reference_replay"]=fixture_mode
            result["model"]=lesson.get("model")
            result["provider"]=lesson.get("provider")
            assert len(lesson["steps"])>=3
            if label=="hydraulics":
                from app.visual_checks import hydraulic_inputs,check_hydraulic
                result["physical_checks"]=check_hydraulic(lesson["steps"],hydraulic_inputs(question))
            if os.getenv("DECLIC_LOCAL_ONLY")=="1":
                assert result["provider"]=="ollama",lesson.get("provider")
                labels={o.get("text") for step in lesson["steps"] for o in step["objects"] if o["kind"]=="text"}
                if label=="physics":
                    assert {"m = 2 kg","F = 6 N","a = 3 m/s²"}<=labels,labels
                    assert any(c.get("op")=="divide" and c.get("operands")==[6,2] and c.get("result")==3 for c in lesson["numerical_checks"])
                else:
                    assert {"9","16","25"}<=labels,labels
                    assert any(c.get("op")=="pythagoras" and c.get("operands")==[3,4] and c.get("result")==5 for c in lesson["numerical_checks"])
                result["semantic_acceptance"]=True
            # Replay from the beginning so both streams start together and no generation wait dominates the clip.
            if "Stop" in page.locator("#studio-play").inner_text():page.locator("#studio-play").click()
            page.locator("#studio-steps button").first.click()
            page.locator("#studio-voice-engine").select_option("cloud")
            page.locator("#studio-voice").check()
            page.evaluate("window.studioTrace=[]")
            rec=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-y","-thread_queue_size","512","-f","x11grab","-framerate","20","-video_size","1440x900","-i",os.environ["DISPLAY"],"-thread_queue_size","512","-f","pulse","-i","declic.monitor","-c:v","libx264","-preset","ultrafast","-crf","25","-pix_fmt","yuv420p","-c:a","aac","-movflags","+faststart",str(out/(label+".mp4"))],stdin=subprocess.PIPE)
            time.sleep(1)
            page.locator("#studio-play").click()
            wait_for(page,"document.querySelector('#studio-svg').dataset.audio==='playing'",timeout=55000)
            assert int(page.locator("#studio-svg").get_attribute("data-cue-count") or 0)>0
            result["voice_backend"]=page.locator("#studio-svg").get_attribute("data-voice-backend")
            if os.getenv("DECLIC_REQUIRE_NEURAL")=="1": assert result["voice_backend"]=="piper-neural",result["voice_backend"]
            if os.getenv("DECLIC_REQUIRE_GEMINI_VOICE")=="1": assert result["voice_backend"]=="gemini-neural",result["voice_backend"]
            wait_for(page,"document.querySelector('#studio-play').textContent.includes('Play')",timeout=200000)
            if os.getenv("DECLIC_REQUIRE_GEMINI_VOICE")=="1":assert page.locator("#studio-svg").get_attribute("data-voice-backend")=="gemini-neural","Final scene did not use cloud voice"
            assert page.locator("#studio-svg").get_attribute("data-audio")=="ended"
            trace=page.evaluate("window.studioTrace")
            (out/(label+".trace.json")).write_text(json.dumps(trace,ensure_ascii=False,indent=2))
            assert any(e["at"]>0 and e["audioTime"] is not None and e["audioTime"]>0 for e in trace),"No synchronized reveal during audio"
            result["synchronized_reveal"]=True
            result["final_label_collisions"]=page.locator('#studio-svg [data-label-collision="true"]').count()
            page.screenshot(path=str(out/(label+"-final.png")))
            assert result["final_label_collisions"]==0,"Final scene has unresolved label collisions"
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
assert all((r.get("reference_replay") if fixture_mode else r.get("generated")) and r.get("synchronized_reveal") and r.get("audible") and not r.get("error") for r in results),results
