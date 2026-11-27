"""Replay the reported conversation in the actual UI without API credentials."""
import pathlib,json
from playwright.sync_api import sync_playwright
from browser_wait import wait_for
out=pathlib.Path("topic-evidence");out.mkdir(exist_ok=True)
questions=["pythagore?","whats the latest update on gold worth?","whats the latest update on gold worth in us dollars?","could you explain more ? do you have current price of gold in us dollars?","could you explain more ? do you have current price of gold in us dollars?","im only talking about gold and not math"]
with sync_playwright() as p:
    browser=p.chromium.launch()
    ctx=browser.new_context(viewport={"width":1440,"height":1000},java_script_enabled=False)
    page=ctx.new_page()
    page.goto("http://127.0.0.1:8000")
    assert page.locator("#auth-form").get_attribute("method")=="post"
    assert page.locator("#auth-submit").is_disabled()
    ctx.close()
    ctx=browser.new_context(viewport={"width":1440,"height":1000})
    page=ctx.new_page()
    errors=[]
    page.on("pageerror",lambda e:errors.append(str(e)))
    page.goto("http://127.0.0.1:8000")
    assert page.locator("#auth-submit").is_enabled()
    page.locator("#demo-login").click()
    wait_for(page,"!!state.user && !!state.aiMode && document.querySelector('#auth-overlay').hidden")
    if page.evaluate("state.language")!="en":page.locator("#language").click()
    page.locator('[data-view="studio"]').click()
    page.locator("#studio-voice").uncheck()
    page.locator("#studio-generative").check()
    results=[]
    for i,q in enumerate(questions):
        page.locator("#studio-question").fill(q)
        with page.expect_response(lambda r:r.url.endswith("/api/studio") and r.request.method=="POST",timeout=20000) as event:
            page.locator("#studio-send").click()
        response=event.value
        assert response.status==200
        result=response.json()
        wait_for(page,"!document.querySelector('#studio-send').disabled")
        if i==0:
            assert result["numerical_checks"]
            assert "perpendicular" in result["steps"][0]["narration"]
        else:
            assert result["visual_mode"]=="information"
            assert "live data feed" in result["steps"][0]["narration"]
            assert "triangle" not in json.dumps(result).lower()
            assert "Live data unavailable" in page.locator("#studio-svg").text_content()
        results.append({"question":q,"result":result})
        page.screenshot(path=str(out/f"{i+1:02d}.png"))
        print("PASS",i+1,q,flush=True)
    assert not errors,errors
    (out/"results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2))
    browser.close()
