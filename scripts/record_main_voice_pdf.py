from acceptance_main_common import *
from playwright.sync_api import sync_playwright
import fitz

# A synthetic source with a unique fact, unavailable from general model knowledge.
PDF=OUT/"pendulum-course-test.pdf"
CODE="violet cedar seven"
with fitz.open() as d:
    for text in [
        "Mechanics Laboratory - Pendulum Experiment\n\nA pendulum oscillates around its equilibrium position.\nIts period is the time required to complete one oscillation.",
        "Pendulum laboratory calibration protocol\n\nThe calibration code for the pendulum experiment is violet cedar seven.\nRecord this code before measuring the period.\nFor this experiment the reference pendulum length is 0.81 meters.\nA pendulum of this length has an approximate period of 1.8 seconds."]:
        page=d.new_page()
        page.insert_textbox(fitz.Rect(50,50,550,650),text,fontsize=14)
    d.save(PDF)
audio=[];events=[];rec=None;questions=[]
def speak(page,path):
    count=len(events)
    page.locator("#studio-speech-engine").select_option("vosk")
    page.locator("#studio-auto-send").check()
    page.locator("#studio-mic").click()
    expect(page.locator("#studio-status")).to_contain_text("Vosk",timeout=25000)
    with page.expect_response(lambda r:r.request.method=="POST" and r.url.endswith("/api/studio"),timeout=150000) as event:
        play=subprocess.Popen(["paplay","--device=studentmic",str(path)])
        play.wait(timeout=25)
        # Vosk finalizes after silence; manual stop if necessary, never type the prompt.
        page.wait_for_timeout(2500)
        if "Stop" in page.locator("#studio-mic").inner_text():page.locator("#studio-mic").click()
    r=event.value
    assert r.status==200
    request=r.request.post_data_json
    transcript=request["question"]
    new=events[count:]
    check("Real Vosk final transcript auto-submitted",any(e.get("type")=="final" and e.get("text") for e in new) and request["consent_external"] is True,transcript=transcript)
    questions.append(transcript)
    return r.json()
with sync_playwright() as p:
    browser=launch(p)
    ctx=browser.new_context(no_viewport=True,permissions=["microphone"])
    page=ctx.new_page()
    audio_observer(page,audio)
    def observe(ws):
        if ws.url.endswith("/api/studio/listen"):
            def received(m):
                if isinstance(m,str):
                    try:events.append(json.loads(m))
                    except ValueError:pass
            ws.on("framereceived",received)
    page.on("websocket",observe)
    try:
        rec=start_recording("02-voice-and-pdf-full-workflow.mp4",with_mic=True)
        setup(page,"Voice Test Student")
        wait(page,"state.speech?.en===true")
        navigate(page,"library")
        page.locator("#course-file").set_input_files(str(PDF))
        doc=response(page,"POST","/api/documents",lambda:page.locator("#upload-form button").click(),201)
        expect(page.locator("#reader")).to_be_visible()
        wait(page,"state.reader && !state.readerLoading && document.querySelector('#reader-image').naturalWidth>0")
        check("Actual PDF uploaded through browser",doc.get("id") is not None)
        shot(page,"01-pdf-uploaded")
        studio_settings(page,True,True)
        prev=len(audio)
        lesson=speak(page,OUT/"student-question-1.wav")
        (OUT/"voice-lesson-1.json").write_text(json.dumps(lesson,ensure_ascii=False,indent=2))
        check("Spoken question received live AI response",lesson.get("mode")=="live_ai",provider=lesson.get("provider"),model=lesson.get("model"),visual_mode=lesson.get("visual_mode"))
        answer=" ".join(s["narration"]+" "+s["formula"]+" "+" ".join(o.get("text","") for o in s.get("objects",[])) for s in lesson["steps"]).casefold()
        check("AI used unique uploaded PDF fact",CODE in answer and any(s["document_id"]==doc["id"] and s["page"]==1 and CODE in s["excerpt"].casefold() for s in lesson.get("sources",[])),source_page=2)
        check("First spoken answer played audible app audio",finish_audio(page,audio,prev),audio=audio[prev:])
        shot(page,"02-voice-pdf-answer")
        if lesson.get("sources"):
            page.locator("#studio-sources button").first.click()
            wait(page,"state.currentView==='library' && state.reader && !state.readerLoading")
            check("Citation opens matching uploaded page",page.evaluate("state.reader.id")==doc["id"] and page.evaluate("state.reader.page")==1)
            shot(page,"03-citation-page")
        studio_settings(page,True,True)
        prev=len(audio)
        follow=speak(page,OUT/"student-question-2.wav")
        (OUT/"voice-lesson-2.json").write_text(json.dumps(follow,ensure_ascii=False,indent=2))
        check("Second spoken question received live AI response",follow.get("mode")=="live_ai",provider=follow.get("provider"),model=follow.get("model"),visual_mode=follow.get("visual_mode"))
        check("Second spoken answer played audible app audio",finish_audio(page,audio,prev),audio=audio[prev:])
        shot(page,"04-voice-followup")
        # Separate test of document-aware Learning Coach, not just citation UI.
        navigate(page,"coach")
        page.locator("#chat-input").fill("According to my uploaded pendulum laboratory calibration protocol, what is the calibration code and why must it be recorded?")
        coach=response(page,"POST","/api/coach",lambda:page.locator("#chat-form button").click(),timeout=100000)
        (OUT/"pdf-coach.json").write_text(json.dumps(coach,ensure_ascii=False,indent=2))
        check("Learning Coach answers unique PDF fact with matching citation",coach.get("mode")=="live_ai" and CODE in coach.get("answer","").casefold() and any(s["document_id"]==doc["id"] and s["page"]==1 for s in coach.get("sources",[])),provider=coach.get("provider"),model=coach.get("model"))
        shot(page,"05-pdf-coach")
        check("No browser JavaScript errors",not errors)
    finally:
        end_recording(rec)
        ctx.close();browser.close()
        save_results({"audio":audio,"speech_events":events,"transcripts":questions,"microphone":"synthetic Piper speech routed through actual PulseAudio virtual microphone, not typed","pdf":"synthetic test PDF, not user document"})
assert checks and all(c["passed"] for c in checks),checks
