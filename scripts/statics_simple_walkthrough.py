"""Slow English narrated walkthrough of real Statics Lab interactions."""
import os, json, subprocess, time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from browser_wait import wait_for
from app.voice import _neural_render

OUT=Path("statics-walkthrough")
OUT.mkdir(exist_ok=True)
checks=[]
transcript=[]
def say(page, name, words):
    transcript.append(name+": "+words)
    audio,_=_neural_render(words,"en",[0])
    wav=OUT/(name+".wav")
    wav.write_bytes(audio)
    player=subprocess.Popen(["paplay",str(wav)])
    while player.poll() is None:
        page.wait_for_timeout(100)
    assert player.returncode==0
    page.wait_for_timeout(1000)
    (OUT/"narration.txt").write_text("\n\n".join(transcript),encoding="utf-8")
def mark(page,name):
    page.screenshot(path=str(OUT/(name+".png")),full_page=True)
    checks.append(name)
    print("PASS",name,flush=True)

with sync_playwright() as p:
    browser=p.chromium.launch(headless=False,ignore_default_args=["--mute-audio"],args=["--no-sandbox","--window-size=1440,900","--window-position=0,0","--start-maximized"])
    ctx=browser.new_context(no_viewport=True)
    page=ctx.new_page()
    errors=[]
    page.on("pageerror",lambda e:errors.append(str(e)))
    page.goto(os.environ.get("DECLIC_URL","http://127.0.0.1:8000"))
    page.locator("#demo-login").click()
    expect(page.locator("#auth-overlay")).to_be_hidden()
    wait_for(page,"state.challenge!==null && !state.labBusy")
    if page.evaluate("state.language")!="en":
        page.locator("#language").click()
    page.locator('[data-view="lab"]').click()
    rec=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-y","-thread_queue_size","512","-f","x11grab","-framerate","20","-video_size","1440x900","-i",os.environ["DISPLAY"],"-thread_queue_size","512","-f","pulse","-i","declic.monitor","-c:v","libx264","-preset","ultrafast","-crf","24","-pix_fmt","yuv420p","-c:a","aac","-movflags","+faststart",str(OUT/"DECLIC-statics-simple.mp4")],stdin=subprocess.PIPE)
    try:
        page.wait_for_timeout(1000)
        say(page,"01-intro","Imagine two people holding a plank with weights on it. This lab helps us learn how much weight each person carries. We call those forces A and B.")
        for name,value in {"length-input":"8","load-input":"12","position-input":"2","udl-input":"2"}.items():
            page.locator("#"+name).fill(value)
            page.wait_for_timeout(450)
        with page.expect_response(lambda r:r.url.endswith("/api/challenges") and r.request.method=="POST") as event:
            page.locator("#apply-beam").click()
        assert event.value.status==201
        wait_for(page,"!state.labBusy")
        mark(page,"02-configured")
        say(page,"02-beam","Here we set an eight meter plank, a heavy object near the left, and weight spread across the plank. First, we guess which side carries more.")
        page.locator('[data-pred="equal"]').click()
        expect(page.locator("#step-solve")).to_be_visible()
        wait_for(page,"!state.labBusy")
        say(page,"03-predict","I guessed both sides carry the same weight. Now I will calculate the two forces. I deliberately forget the weight spread across the plank.")
        page.locator("#answer-ra").fill("9")
        page.wait_for_timeout(650)
        page.locator("#answer-rb").fill("3")
        page.wait_for_timeout(650)
        page.locator("#submit-solution").click()
        expect(page.locator("#solution-feedback")).to_contain_text("RA = 17")
        expect(page.locator("#solution-feedback")).to_contain_text("RB = 11")
        wait_for(page,"!state.labBusy")
        page.locator("#solution-feedback").scroll_into_view_if_needed()
        mark(page,"03-correction")
        say(page,"04-feedback","The red feedback shows my mistake. I forgot the distributed weight. The correct forces are seventeen and eleven. The program uses real math to check this, not an AI guess.")
        page.locator("#continue-explain").click()
        page.locator("#student-explanation").fill("I use the sum of forces and moments. The distance from the support changes the lever arm and reaction.")
        page.locator("#submit-explanation").click()
        expect(page.locator("#explanation-feedback")).to_be_visible()
        wait_for(page,"!state.labBusy")
        mark(page,"04-explanation")
        say(page,"05-explain","Next, I explain why the answer works in my own words. The program checks for key ideas, like forces, moments, and distance.")
        page.reload()
        wait_for(page,"state.challenge!==null && !state.labBusy")
        page.locator('[data-view="lab"]').click()
        expect(page.locator("#step-transfer")).to_be_visible()
        page.locator("#start-transfer").click()
        wait_for(page,"state.challenge.kind==='transfer' && !state.labBusy")
        b=page.evaluate("state.challenge")
        ra=b["load"]*(b["length"]-b["position"])/b["length"]+b["udl"]*b["length"]/2
        rb=b["load"]*b["position"]/b["length"]+b["udl"]*b["length"]/2
        mark(page,"05-new-exercise")
        say(page,"06-transfer","Now comes a new problem with different numbers. This checks whether I really learned the method, instead of copying the old answer.")
        answer="equal" if abs(ra-rb)<1e-8 else "left" if ra>rb else "right"
        page.locator('[data-pred="'+answer+'"]').click()
        expect(page.locator("#step-solve")).to_be_visible()
        wait_for(page,"!state.labBusy")
        page.locator("#answer-ra").fill(str(round(ra,3)))
        page.wait_for_timeout(700)
        page.locator("#answer-rb").fill(str(round(rb,3)))
        page.wait_for_timeout(700)
        page.locator("#submit-solution").click()
        expect(page.locator("#solution-feedback")).to_have_class("feedback success")
        wait_for(page,"!state.labBusy")
        page.locator("#solution-feedback").scroll_into_view_if_needed()
        mark(page,"06-correct-transfer")
        say(page,"07-success",f"This time I got it right. The forces are {ra:g} and {rb:g}. The green message confirms the calculation.")
        page.locator('[data-view="profile"]').click()
        page.locator("#plan-minutes").select_option("45")
        wait_for(page,"Array.from(document.querySelectorAll('#study-plan-tasks .plan-task')).reduce((n,b)=>n+parseInt(b.textContent),0)===45")
        mark(page,"07-plan")
        say(page,"08-plan","The learning profile remembers my practice and suggests what to study next. I can choose forty-five minutes, and the program makes a plan.")
        page.locator('[data-view="dashboard"]').click()
        mark(page,"08-dashboard")
        say(page,"09-end","That is the whole idea. Guess, try, understand your mistake, and try again. Declic uses your results to guide your next lesson.")
        assert not errors,errors
        (OUT/"results.json").write_text(json.dumps({"checks":checks,"browser_errors":errors,"transfer":{"ra":ra,"rb":rb},"voiceover":"Piper explanatory narration, not lab-generated speech"},indent=2))
        print("PASS: narrated Statics Lab",json.dumps({"checks":checks,"ra":ra,"rb":rb}),flush=True)
    finally:
        rec.communicate(b"q",timeout=30)
        ctx.close()
        browser.close()
