from browser_wait import wait_for
import io
import subprocess
import time
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get("DECLIC_URL","http://127.0.0.1:8000")
OUT=Path("app-session")
OUT.mkdir(exist_ok=True)
checks=[]
# No external narrator or prerecorded voice. Only browser audio is captured.
def pause(page,ms=1200):
    page.wait_for_timeout(ms)
def checkpoint(page,name):
    page.screenshot(path=str(OUT/(name+".png")),full_page=True)
    checks.append({"check":name,"passed":True})
    print("PASS",name,flush=True)
    pause(page,1800)

with sync_playwright() as p:
    browser=p.chromium.launch(headless=False,ignore_default_args=["--mute-audio"],args=["--no-sandbox","--window-size=1440,900","--window-position=0,0","--start-maximized","--autoplay-policy=no-user-gesture-required"])
    ctx=browser.new_context(no_viewport=True)
    page=ctx.new_page()
    errors=[]
    page.on("pageerror",lambda e:errors.append(str(e)))
    audio_responses=[]
    def record_audio(response):
        if response.url.endswith("/api/studio/audio"):
            audio_responses.append({"status":response.status,"backend":response.headers.get("x-studio-voice"),"cues":response.headers.get("x-studio-cues")})
    page.on("response",record_audio)
    page.on("dialog",lambda d:d.dismiss() if "Autoriser" in d.message or "Allow" in d.message else d.accept())
    page.goto(BASE)
    rec=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-y","-thread_queue_size","512","-f","x11grab","-framerate","20","-video_size","1440x900","-i",os.environ["DISPLAY"],"-thread_queue_size","512","-f","pulse","-i","declic.monitor","-c:v","libx264","-preset","ultrafast","-crf","24","-pix_fmt","yuv420p","-c:a","aac","-movflags","+faststart",str(OUT/"DECLIC-real-app-session.mp4")],stdin=subprocess.PIPE)
    try:
        time.sleep(1)
        pause(page,1800)
        page.locator("#demo-login").click()
        expect(page.locator("#auth-overlay")).to_be_hidden()
        wait_for(page,"state.challenge!==null && !state.labBusy")
        pause(page,1800)
        page.locator('[data-view="lab"]').click()
        for name,value in {"length-input":"8","load-input":"12","position-input":"2","udl-input":"2"}.items():
            page.locator("#"+name).fill(value)
        with page.expect_response(lambda r:r.url.endswith("/api/challenges") and r.request.method=="POST") as event:
            page.locator("#apply-beam").click()
        assert event.value.status==201
        expect(page.locator("#step-predict")).to_be_visible()
        wait_for(page,"!state.labBusy")
        page.locator("#load-input").fill("16")
        page.locator('[data-pred="equal"]').click()
        expect(page.locator("#step-predict")).to_be_visible()
        assert page.evaluate("state.choice===null")
        page.locator("#load-input").fill("12")
        page.locator('[data-pred="equal"]').click()
        expect(page.locator("#step-solve")).to_be_visible()
        wait_for(page,"!state.labBusy")
        cid=page.evaluate("state.challenge.id")
        page.reload()
        wait_for(page,"state.challenge!==null && !state.labBusy")
        assert page.evaluate("state.challenge.id")==cid
        page.locator('[data-view="lab"]').click()
        expect(page.locator("#step-solve")).to_be_visible()
        checkpoint(page,"01-resume-and-configuration-guard")
        page.locator("#answer-ra").fill("9")
        page.locator("#answer-rb").fill("3")
        page.locator("#submit-solution").click()
        expect(page.locator("#solution-feedback")).to_contain_text("RA = 17")
        expect(page.locator("#solution-feedback")).to_contain_text("RB = 11")
        wait_for(page,"!state.labBusy")
        checkpoint(page,"02-misconception-feedback")
        page.locator("#continue-explain").click()
        page.locator("#student-explanation").fill("Je calcule la somme des forces, les moments autour du support et les bras de levier.")
        page.locator("#submit-explanation").click()
        expect(page.locator("#explanation-feedback")).to_be_visible()
        wait_for(page,"!state.labBusy")
        page.reload()
        wait_for(page,"state.challenge!==null && !state.labBusy")
        page.locator('[data-view="lab"]').click()
        expect(page.locator("#step-transfer")).to_be_visible()
        page.locator("#start-transfer").click()
        wait_for(page,"state.challenge.kind==='transfer' && !state.labBusy")
        assert page.evaluate("state.challenge.id")!=cid
        assert page.evaluate("state.solution===null")
        page.locator('[data-view="studio"]').click()
        page.locator("#studio-question").fill("Donne les réactions numériques")
        with page.expect_response(lambda r:r.url.endswith("/api/studio") and r.request.method=="POST") as event:
            page.locator("#studio-send").click()
        assert event.value.status==409
        expect(page.locator("#studio-status")).to_contain_text("indépendant")
        checkpoint(page,"03-independent-assessment-protection")
        page.locator('[data-view="lab"]').click()
        b=page.evaluate("state.challenge")
        ra=b["load"]*(b["length"]-b["position"])/b["length"]+b["udl"]*b["length"]/2
        rb=b["load"]*b["position"]/b["length"]+b["udl"]*b["length"]/2
        answer="equal" if abs(ra-rb)<1e-8 else "left" if ra>rb else "right"
        page.locator('[data-pred="'+answer+'"]').click()
        expect(page.locator("#step-solve")).to_be_visible()
        wait_for(page,"!state.labBusy")
        page.locator("#answer-ra").fill(str(round(ra,3)))
        page.locator("#answer-rb").fill(str(round(rb,3)))
        page.locator("#submit-solution").click()
        expect(page.locator("#solution-feedback")).to_have_class("feedback success")
        wait_for(page,"!state.labBusy")
        checkpoint(page,"04-independent-transfer-success")
        page.locator('[data-view="library"]').click()
        page.locator("#course-file").set_input_files("data/demo_rdm2.pdf")
        with page.expect_response(lambda r:r.url.endswith("/api/documents") and r.request.method=="POST") as event:
            page.locator("#upload-form button").click()
        assert event.value.status==201
        doc=event.value.json()["id"]
        expect(page.locator("#reader")).to_be_visible()
        wait_for(page,"state.reader && !state.readerLoading && document.querySelector('#reader-image').naturalWidth>0")
        checkpoint(page,"05-pdf-auto-open")
        page.locator("#next-page").click()
        wait_for(page,"state.reader.page===1 && !state.readerLoading")
        expect(page.locator("#reader-page")).to_contain_text("2 /")
        page.locator("#text-page").click()
        expect(page.locator("#reader-text")).to_be_visible()
        checkpoint(page,"06-pdf-page-navigation")
        page.locator('[data-view="studio"]').click()
        page.locator("#studio-voice").uncheck()
        page.locator("#studio-question").fill("Explique le moment et les forces")
        with page.expect_response(lambda r:r.url.endswith("/api/studio") and r.request.method=="POST") as event:
            page.locator("#studio-send").click()
        lesson=event.value.json()
        assert lesson["mode"]=="guided_offline" and lesson["sources"]
        expect(page.locator("#studio-sources button").first).to_be_visible()
        checkpoint(page,"07-source-grounded-offline-studio")
        source=lesson["sources"][0]
        page.locator("#studio-sources button").first.click()
        wait_for(page,"(source)=>state.currentView==='library' && state.reader && state.reader.id===source.document_id && state.reader.page===source.page && !state.readerLoading",arg=source)
        assert page.evaluate("state.reader.id")==source["document_id"]
        assert page.evaluate("state.reader.page")==source["page"]
        checkpoint(page,"08-source-exact-page")
        page.locator('[data-view="coach"]').click()
        page.locator("#chat-input").fill("Comment calculer le moment ?")
        with page.expect_response(lambda r:r.url.endswith("/api/coach") and r.request.method=="POST",timeout=90000) as event:
            page.locator("#chat-form button").click()
        assert event.value.status==200
        expect(page.locator(".coach-message").last).to_be_visible()
        pause(page,1800)
        page.locator('[data-view="discover"]').click()
        expect(page.locator(".resource-card").first).to_be_visible()
        pause(page,1800)
        page.locator('[data-view="studio"]').click()
        page.locator("#studio-consent").check()
        page.locator("#studio-voice").check()
        page.locator("#studio-voice-engine").select_option("cloud")
        pause(page,1800)
        page.evaluate("""() => {window.studioTrace=[];document.querySelector('#studio-svg').addEventListener('studio:reveal',e=>window.studioTrace.push({...e.detail,wall:performance.now()}));}""")
        page.locator("#studio-question").fill("Explique la deuxième loi de Newton avec une masse de 2 kg, une force nette de 6 N et une accélération de 3 m/s². Anime les vecteurs.")
        with page.expect_response(lambda r:r.url.endswith("/api/studio") and r.request.method=="POST",timeout=120000) as event:
            page.locator("#studio-send").click()
        live=event.value.json()
        (OUT/"live-lesson.json").write_text(json.dumps(live,ensure_ascii=False,indent=2))
        generated=live.get("visual_mode")=="generated" and live.get("mode")=="live_ai"
        if generated:
            wait_for(page,"document.querySelector('#studio-svg').dataset.audio==='playing'",timeout=55000)
            wait_for(page,"document.querySelector('#studio-play').textContent.includes('Play')",timeout=200000)
            assert page.locator("#studio-svg").get_attribute("data-audio")=="ended"
            assert any(x["status"]==200 and x["backend"] for x in audio_responses),"No server-generated app speech"
            trace=page.evaluate("window.studioTrace")
            assert any(e["at"]>0 and e["audioTime"] is not None and e["audioTime"]>0 for e in trace),"No synchronized reveal during audio"
            (OUT/"live-trace.json").write_text(json.dumps(trace,ensure_ascii=False,indent=2))
            checkpoint(page,"live-generated-lesson")
            pause(page,1800)
        else:
            page.wait_for_timeout(1500)
            page.locator('[data-view="dashboard"]').click()
            pause(page,1800)
        checks.append({"check":"live-generation","passed":generated,"model":live.get("model"),"provider":live.get("provider")})
        if generated:
            # Real follow-up question in the same conversation, not a prewritten answer.
            page.locator("#studio-question").fill("Et si la masse double, avec la même force de 6 N, que devient l’accélération ? Montre la comparaison.")
            with page.expect_response(lambda r:r.url.endswith("/api/studio") and r.request.method=="POST",timeout=120000) as event:
                page.locator("#studio-send").click()
            follow=event.value.json()
            (OUT/"follow-up.json").write_text(json.dumps(follow,ensure_ascii=False,indent=2))
            follow_ok=follow.get("mode")=="live_ai" and follow.get("visual_mode")=="generated"
            if follow_ok:
                wait_for(page,"document.querySelector('#studio-svg').dataset.audio==='playing'",timeout=55000)
                wait_for(page,"document.querySelector('#studio-play').textContent.includes('Play')",timeout=200000)
                checkpoint(page,"live-follow-up")
            else:
                page.wait_for_timeout(2200)
            checks.append({"check":"live-follow-up","passed":follow_ok,"provider":follow.get("provider"),"model":follow.get("model")})
        page.locator('[data-view="library"]').click()
        page.evaluate("state.readerSeconds=10")
        page.locator('[data-view="dashboard"]').click()
        wait_for(page,"state.readerSeconds===0")
        page.wait_for_timeout(5500)
        assert page.evaluate("state.readerSeconds===0")
        page.locator('[data-view="library"]').click()
        page.locator('[data-delete-doc="'+doc+'"]').click()
        expect(page.locator('[data-delete-doc="'+doc+'"]')).to_have_count(0)
        checkpoint(page,"09-document-deletion-and-inactive-reading")
        page.locator('[data-view="profile"]').click()
        page.locator("#plan-minutes").select_option("45")
        expect(page.locator("#study-plan-tasks .plan-task")).to_have_count(3)
        wait_for(page,"Array.from(document.querySelectorAll('#study-plan-tasks .plan-task')).reduce((n,b)=>n+parseInt(b.textContent),0)===45")
        checkpoint(page,"10-adaptive-study-plan")
        page.locator("#delete-account").click()
        expect(page.locator("#auth-overlay")).to_be_visible()
        assert page.evaluate("localStorage.getItem('declic_token')===null")
        checkpoint(page,"11-account-deletion")
    finally:
        rec.communicate(b"q",timeout=20)
        ctx.close()
        browser.close()
(OUT/"results.json").write_text(json.dumps({"checks":checks,"browser_errors":errors,"audio_responses":audio_responses,"external_voiceover":False},indent=2))
print("SESSION RESULTS",json.dumps({"checks":checks,"browser_errors":errors,"audio_responses":audio_responses},ensure_ascii=False),flush=True)
assert not errors,errors
assert generated,"No live original lesson generated"
assert follow_ok,"Live follow-up unavailable"
print("PASS: full real application session, app audio only",flush=True)
