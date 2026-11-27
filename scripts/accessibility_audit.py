"""Automated accessibility inspection; not a physical-device or screen-reader test."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

out=Path("accessibility-evidence");out.mkdir(exist_ok=True)
results={}
with sync_playwright() as p:
    browser=p.chromium.launch()
    for width,height in [(1440,900),(390,844)]:
        ctx=browser.new_context(viewport={"width":width,"height":height})
        page=ctx.new_page()
        page.goto("http://127.0.0.1:8000")
        expect(page.get_by_role("dialog")).to_be_visible()
        expect(page.get_by_role("textbox",name="Nom complet / Full name")).to_be_visible()
        expect(page.get_by_role("textbox",name="Adresse email / Email address")).to_be_visible()
        page.locator("#demo-login").click()
        expect(page.locator("#auth-overlay")).to_be_hidden()
        page.wait_for_function("state.challenge!==null && !state.labBusy")
        for view in ["dashboard","lab","library","profile","coach","studio","discover"]:
            page.locator('[data-view="'+view+'"]').click()
            section=page.locator("#view-"+view)
            expect(section).to_be_visible()
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
