"""Unmocked cloud AI generation plus real local narration, captured from browser audio.
No built-in or replayed lesson accepted. No production code changes."""
import os, pathlib, subprocess, time, json, re, urllib.request, io, wave, array
from playwright.sync_api import sync_playwright
from browser_wait import wait_for
out=pathlib.Path("live-voice-evidence");out.mkdir(exist_ok=True)
cases=[
 ("en","pocket-george",["Explain the Pythagorean theorem using an animated right triangle with sides 3, 4 and 5. Show the square areas.","Explain more"]),
 ("fr","piper-fr_FR-tom-medium",["Explique le théorème de Pythagore avec un triangle rectangle de côtés 6, 8 et 10 et montre les aires des carrés.","Explique davantage"])
]
results=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=False,ignore_default_args=["--mute-audio"],args=["--window-size=1440,900","--window-position=0,0","--start-maximized","--autoplay-policy=no-user-gesture-required"])
 for lang,voice,questions in cases:
    ctx=browser.new_context(no_viewport=True)
    page=ctx.new_page();errors=[]
    page.on("pageerror",lambda e:errors.append(str(e)))
    page.goto("http://127.0.0.1:8000")
    page.locator("#demo-login").click()
    wait_for(page,"!!state.user && !!state.aiMode && document.querySelector('#auth-overlay').hidden")
    if page.evaluate("state.language")!=lang:page.locator("#language").click()
    page.locator('[data-view="studio"]').click()
    if page.locator("#studio-ai-mode").input_value()!="cloud":page.locator("#studio-ai-mode").select_option("cloud")
    assert page.evaluate("state.aiMode")== "cloud"
    page.locator("#studio-consent").check()
    page.locator("#studio-generative").check()
    page.locator("#studio-voice").check()
    page.locator("#studio-voice-engine").select_option("local")
    assert page.locator("#studio-voice-profile").input_value()==""
    page.evaluate("""() => {window.studioTrace=[];document.querySelector('#studio-svg').addEventListener('studio:reveal',e=>window.studioTrace.push({...e.detail,wall:performance.now()}));}""")
    rec=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-y","-thread_queue_size","512","-f","x11grab","-framerate","20","-video_size","1440x900","-i",os.environ["DISPLAY"],"-thread_queue_size","512","-f","pulse","-i","declic.monitor","-c:v","libx264","-preset","ultrafast","-crf","24","-pix_fmt","yuv420p","-c:a","aac","-movflags","+faststart",str(out/(lang+".mp4"))],stdin=subprocess.PIPE)
    try:
        if lang=="en":questions=questions+["whats the latest update on gold worth?","whats the latest update on gold worth in us dollars?","could you explain more ? do you have current price of gold in us dollars?","could you explain more ? do you have current price of gold in us dollars?","im only talking about gold and not math"]
        for i,question in enumerate(questions):
            result={"lang":lang,"turn":i+1,"question":question,"pass":False}
            audio=[]
            def capture(r):
                if r.url.endswith("/api/studio/audio") and r.request.method=="POST":audio.append(r)
            page.on("response",capture)
            try:
                page.evaluate("window.studioTrace=[]")
                page.locator("#studio-question").fill(question)
                with page.expect_response(lambda r:r.url.endswith("/api/studio") and r.request.method=="POST",timeout=150000) as ev:
                    page.locator("#studio-send").click()
                response=ev.value
                lesson=response.json()
                (out/(lang+f"-turn{i+1}.json")).write_text(json.dumps(lesson,ensure_ascii=False,indent=2))
                result.update({"mode":lesson.get("mode"),"visual_mode":lesson.get("visual_mode"),"provider":lesson.get("provider"),"model":lesson.get("model")})
                fresh=lang=="en" and i>=2
                if fresh:
                    assert response.status==200 and lesson["visual_mode"]=="information" and "live data feed" in lesson["steps"][0]["narration"] and "triangle" not in json.dumps(lesson).lower()
                else:assert response.status==200 and lesson.get("mode")=="live_ai" and lesson.get("visual_mode")=="generated" and lesson.get("provider") in ("openrouter","bazaarlink","gemini") and lesson.get("model"),"No genuine cloud-generated lesson"
                if not fresh:assert len(lesson["steps"])>=2
                payload=response.request.post_data_json
                assert payload["ai_mode"]=="cloud" and payload["consent_external"] and payload["generative"]
                if i==1:assert any(questions[0] in h.get("text","") for h in payload["history"]),"Missing first turn context"
                result["history_entries"]=len(payload["history"])
                wait_for(page,"document.querySelector('#studio-svg').dataset.audio==='playing'",timeout=60000)
                page.locator("#studio-title").scroll_into_view_if_needed()
                page.screenshot(path=str(out/(lang+f"-turn{i+1}.png")))
                wait_for(page,"document.querySelector('#studio-play').textContent.includes('Play') && document.querySelector('#studio-svg').dataset.audio==='ended'",timeout=210000)
                assert len(audio)==len(lesson["steps"]),f"audio requests {len(audio)} vs scenes {len(lesson['steps'])}"
                evidence=[]
                for j,r in enumerate(audio):
                    assert r.status==200 and r.headers.get("x-studio-voice")==voice,(r.status,r.headers.get("x-studio-voice"))
                    raw=r.body();marks=json.loads(r.headers["x-studio-cues"])
                    with wave.open(io.BytesIO(raw),"rb") as w:
                        seconds=w.getnframes()/w.getframerate();samples=array.array("h",w.readframes(w.getnframes()))
                    assert seconds>1 and max(abs(x) for x in samples)>500 and marks and all(0<=m["time"]<seconds for m in marks)
                    (out/(lang+f"-turn{i+1}-scene{j+1}.wav")).write_bytes(raw)
                    evidence.append({"backend":voice,"seconds":seconds,"cues":marks})
                trace=page.evaluate("window.studioTrace")
                if not fresh:assert any(e.get("at",0)>0 and (e.get("audioTime") or 0)>0 for e in trace),"No synchronized reveal during audio"
                (out/(lang+f"-trace{i+1}.json")).write_text(json.dumps(trace,indent=2))
                assert not errors,errors
                result.update({"pass":True,"audio":evidence,"numerical_checks":lesson.get("numerical_checks",[])})
                print("PASS",lang,i+1,result["provider"],result["model"],voice,flush=True)
            except Exception as exc:
                result["error"]=str(exc)[:400];print("FAIL",lang,i+1,result["error"],flush=True)
                page.screenshot(path=str(out/(lang+f"-failure{i+1}.png")))
            finally:
                page.remove_listener("response",capture)
                results.append(result)
                (out/"results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2))
            if not result["pass"]:break
    finally:
        rec.communicate(b"q",timeout=20)
        ctx.close()
    check=subprocess.run(["ffmpeg","-hide_banner","-i",str(out/(lang+".mp4")),"-af","volumedetect","-vn","-f","null","-"],capture_output=True,text=True)
    m=re.search(r"max_volume: (-?[0-9.]+)",check.stderr)
    print("VIDEO",lang,"max_volume",m.group(1) if m else "none",flush=True)
    if any(x["pass"] and x["lang"]==lang for x in results):assert m and float(m.group(1))>-45,"Silent recording"
 browser.close()
assert len(results)==9 and all(x["pass"] for x in results),"Live end-to-end acceptance incomplete; inspect results and recordings"
