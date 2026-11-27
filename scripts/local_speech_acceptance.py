"""Real Vosk audio-stream and browser capture smoke test. Synthetic microphone only."""
import json,os,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from browser_wait import wait_for
out=Path("speech-evidence")
out.mkdir(exist_ok=True)
audio=str((out/"fake-microphone.wav").resolve())
with sync_playwright() as p:
    browser=p.chromium.launch(args=["--use-fake-device-for-media-stream","--use-fake-ui-for-media-stream","--use-file-for-fake-audio-capture="+audio])
    ctx=browser.new_context(permissions=["microphone"],viewport={"width":1440,"height":900})
    page=ctx.new_page();errors=[];messages=[]
    page.on("pageerror",lambda e:errors.append(str(e)))
    def observe(ws):
        if ws.url.endswith("/api/studio/listen"):ws.on("framereceived",lambda m:messages.append(m if isinstance(m,str) else "binary"))
    page.on("websocket",observe)
    page.goto("http://127.0.0.1:8000")
    page.locator("#demo-login").click()
    wait_for(page,"state.user && state.speech?.fr && state.currentView")
    page.locator('[data-view="studio"]').click()
    page.locator("#studio-speech-engine").select_option("vosk")
    page.locator("#studio-auto-send").uncheck()
    page.locator("#studio-mic").click()
    expect(page.locator("#studio-status")).to_contain_text("Vosk",timeout=20000)
    wait_for(page,"document.querySelector('#studio-question').value.trim().length>2",timeout=25000)
    page.screenshot(path=str(out/"partial-transcript.png"))
    # Finish naturally or manually after enough virtual microphone speech.
    page.wait_for_timeout(7000)
    if "Stop" in page.locator("#studio-mic").inner_text():page.locator("#studio-mic").click()
    expect(page.locator("#studio-mic")).to_contain_text("Micro",timeout=15000)
    final=page.locator("#studio-question").input_value()
    events=[]
    for m in messages:
        try:events.append(json.loads(m))
        except (ValueError,TypeError):pass
    assert any(e.get("type")=="ready" for e in events),events
    assert any(e.get("type")=="partial" and e.get("text") for e in events),events
    assert any(e.get("type")=="final" and e.get("text") for e in events),events
    assert "bonjour" in final.casefold(),final
    assert not errors,errors
    page.screenshot(path=str(out/"final-transcript.png"))
    (out/"browser.json").write_text(json.dumps({"transcript":final,"events":events,"errors":errors,"microphone":"synthetic WAV through Chromium virtual device"},ensure_ascii=False,indent=2))
    print("PASS real Vosk browser PCM stream and final transcript",final,flush=True)
    ctx.close();browser.close()
