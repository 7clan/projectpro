from browser_wait import wait_for
import io
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get("DECLIC_URL","http://127.0.0.1:8000")
OUT=Path("quality-evidence")
OUT.mkdir(exist_ok=True)
checks=[]
def checkpoint(page,name):
    page.screenshot(path=str(OUT/(name+".png")),full_page=True)
    checks.append({"check":name,"passed":True})
    print("PASS",name,flush=True)

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
    assert not errors,errors
    ctx.close()
    mobile=browser.new_context(viewport={"width":390,"height":844},is_mobile=True,has_touch=True)
    m=mobile.new_page()
    m.on("pageerror",lambda e:errors.append(str(e)))
    m.goto(BASE)
    m.locator("#demo-login").click()
    expect(m.locator("#auth-overlay")).to_be_hidden()
    wait_for(m,"state.challenge!==null && !state.labBusy")
    for view in ["dashboard","lab","library","profile","studio"]:
        m.locator('[data-view="'+view+'"]').click()
        assert m.evaluate("document.documentElement.scrollWidth <= innerWidth+2"),view
        checkpoint(m,"mobile-"+view)
    m.locator('[data-view="lab"]').click()
    m.locator("#tab-predict").focus()
    m.keyboard.press("Enter")
    expect(m.locator("#step-predict")).to_be_visible()
    assert m.locator("#tab-predict").get_attribute("aria-current")=="step"
    checkpoint(m,"mobile-keyboard-stage")
    mobile.close()
    assert not errors,errors
    browser.close()
(OUT/"results.json").write_text(json.dumps({"checks":checks,"browser_errors":errors},indent=2))
print("PASS: complete real-browser learner journey",flush=True)
