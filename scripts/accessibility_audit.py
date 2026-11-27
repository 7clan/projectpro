from browser_wait import wait_for
"""Automated accessibility inspection; not a physical-device or screen-reader test."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

out=Path("accessibility-evidence");out.mkdir(exist_ok=True)
results={}
with sync_playwright() as p:
    browser=p.chromium.launch()
    for width,height in [(1440,900),(390,844)]:
        ctx=browser.new_context(viewport={"width":width,"height":height},reduced_motion="reduce")
        page=ctx.new_page()
        page.goto("http://127.0.0.1:8000")
        expect(page.get_by_role("dialog")).to_be_visible()
        expect(page.get_by_role("textbox",name="Nom complet / Full name")).to_be_visible()
        expect(page.get_by_role("textbox",name="Adresse email / Email address")).to_be_visible()
        page.locator("#demo-login").click()
        expect(page.locator("#auth-overlay")).to_be_hidden()
        wait_for(page,"state.challenge!==null && !state.labBusy")
        for view in ["dashboard","lab","library","profile","coach","studio","discover"]:
            page.locator('[data-view="'+view+'"]').click()
            section=page.locator("#view-"+view)
            expect(section).to_be_visible()
            page.wait_for_timeout(350)
            # Browser-native accessible roles, names, and text, not simulated speech.
            snapshot=section.aria_snapshot()
            (out/(str(width)+"-"+view+".aria.txt")).write_text(snapshot,encoding="utf-8")
            page.add_script_tag(path="node_modules/axe-core/axe.min.js")
            audit=page.evaluate("""async () => {
                const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});
                return {violations:r.violations.map(v=>({id:v.id,impact:v.impact,description:v.description,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),passes:r.passes.length};
            }""")
            results[str(width)+"-"+view]=audit
            print("AUDIT",width,view,"passes",audit["passes"],"violations",[(v["id"],len(v["nodes"])) for v in audit["violations"]],flush=True)
        page.locator('[data-view="studio"]').click()
        page.locator("#studio-voice").uncheck()
        # Intentionally crowded synthetic lesson: tests renderer, not live AI generation.
        steps=[{"scene":"generated","title":"Collision test","formula":"6 / 2 = 3","narration":"Six divided by two equals three.","objects":[]}]
        steps[0]["objects"]=[{"kind":"rect","x":100,"y":100,"w":100,"h":60,"color":"blue","motion":"none","at":0}]+[{"kind":"text","text":label,"x":300,"y":160,"size":18,"color":"ink","motion":"fade","at":0} for label in ["Force = 6 N","Mass = 2 kg","Acceleration = 3 m/s²","Net force"]]
        page.route("**/api/studio",lambda route:route.fulfill(json={"mode":"guided_offline","visual_mode":"generated","steps":steps,"sources":[],"notice":"Synthetic renderer regression"}))
        page.locator("#studio-question").fill("Test renderer")
        page.locator("#studio-send").click()
        expect(page.locator('#studio-svg [data-generated="text"]')).to_have_count(4)
        assert page.locator('#studio-svg [data-label-collision="true"]').count()==0
        expect(page.get_by_role("img",name="Collision test. Six divided by two equals three.")).to_be_visible()
        page.screenshot(path=str(out/(str(width)+"-collision-test.png")))
        results[str(width)+"-crowded-labels"]={"passed":True,"labels":4,"collisions":0}
        print("PASS crowded labels and accessible diagram",width,flush=True)
        page.locator('[data-view="lab"]').click()
        page.locator("#tab-predict").focus()
        page.keyboard.press("Enter")
        expect(page.locator("#step-predict")).to_be_visible()
        assert page.locator("#tab-predict").get_attribute("aria-current")=="step"
        page.locator('[data-view="library"]').click()
        expect(page.get_by_label("Choisir un PDF / Choose a PDF")).to_be_visible()
        page.locator('[data-view="profile"]').click()
        expect(page.get_by_label("Date du prochain examen / Exam date")).to_be_visible()
        ctx.close()
    browser.close()
(out/"axe-results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2))
print("PASS: role/name and keyboard assertions; axe violations reported separately",flush=True)
