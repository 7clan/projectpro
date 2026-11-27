from browser_wait import wait_for
import io
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get("DECLIC_URL","http://127.0.0.1:8000")
OUT=Path("statics-evidence")
OUT.mkdir(exist_ok=True)
checks=[]
def checkpoint(page,name):
    page.screenshot(path=str(OUT/(name+".png")),full_page=True)
    checks.append({"check":name,"passed":True})
    print("PASS",name,flush=True)
    page.wait_for_timeout(2500)

with sync_playwright() as p:
    browser=p.chromium.launch(args=["--no-sandbox"])
    ctx=browser.new_context(viewport={"width":1440,"height":900},record_video_dir=str(OUT/"video"),record_video_size={"width":1440,"height":900})
    page=ctx.new_page()
    errors=[]
    page.on("pageerror",lambda e:errors.append(str(e)))
    page.on("dialog",lambda d:d.accept())
    page.goto(BASE)
    page.locator("#demo-login").click()
    expect(page.locator("#auth-overlay")).to_be_hidden()
    page.locator('[data-view="lab"]').click()
    wait_for(page,"state.challenge!==null")
    checkpoint(page,"00-statics-lab")
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
    checks.append({"check":"transfer-calculation","passed":True,"beam":{k:b[k] for k in ("length","load","position","udl")},"expected_ra":ra,"expected_rb":rb})
    page.locator('[data-view="profile"]').click()
    page.locator("#plan-minutes").select_option("45")
    wait_for(page,"Array.from(document.querySelectorAll('#study-plan-tasks .plan-task')).reduce((n,b)=>n+parseInt(b.textContent),0)===45")
    checkpoint(page,"05-adaptive-study-plan")
    page.locator('[data-view="dashboard"]').click()
    checkpoint(page,"06-dashboard-after-practice")
    ctx.close()
    browser.close()
(OUT/"results.json").write_text(json.dumps({"checks":checks,"browser_errors":errors},indent=2))
print("STATICS RESULTS",json.dumps(checks),flush=True)
assert not errors,errors
print("PASS: actual statics browser journey",flush=True)
