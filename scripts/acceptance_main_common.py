import json, os, subprocess, time, wave, io, re, math
from pathlib import Path
from playwright.sync_api import expect
BASE="http://127.0.0.1:8000"
OUT=Path(os.environ["CLASSROOM_EVIDENCE"]).resolve()
OUT.mkdir(parents=True,exist_ok=True)
checks=[]
errors=[]
def wait(page,expr,timeout=30000):
    deadline=time.monotonic()+timeout/1000
    while time.monotonic()<deadline:
        if page.evaluate(expr):return
        page.wait_for_timeout(100)
    raise AssertionError("Browser condition timed out: "+expr)
def check(name,condition=True,**metadata):
    checks.append({"name":name,"passed":bool(condition),**metadata})
    print("PASS" if condition else "FAIL",name,json.dumps(metadata),flush=True)
    return condition
def shot(page,name):
    page.screenshot(path=str(OUT/(name+".png")))
    page.wait_for_timeout(1500)
def response(page,method,suffix,action,status=200,timeout=20000):
    with page.expect_response(lambda r:r.request.method==method and r.url.endswith(suffix),timeout=timeout) as event:action()
    r=event.value
    assert r.status==status,(method,suffix,r.status)
    return r.json()
def setup(page,name):
    page.on("pageerror",lambda e:errors.append(str(e)))
    page.on("dialog",lambda d:d.accept())
    page.bring_to_front()
    page.goto(BASE)
    page.locator('#auth-form [name=name]').fill(name)
    page.locator('#auth-form [name=email]').fill(name.lower().replace(" ",".")+"@example.com")
    page.locator('#auth-form [name=password]').fill("DisposableTest2026!")
    response(page,"POST","/api/auth/register",lambda:page.locator('#auth-submit').click(),201)
    expect(page.locator('#auth-overlay')).to_be_hidden()
    wait(page,"state.dashboard!==null && state.challenge!==null && !state.labBusy")
    if page.evaluate("state.language")!="en":page.locator("#language").click()
    wait(page,"state.aiEnabled===true")
def navigate(page,view):
    page.bring_to_front()
    page.locator('[data-view="'+view+'"]').click()
    page.wait_for_timeout(400)
def token(page):
    return {"Authorization":"Bearer "+page.evaluate("localStorage.getItem('declic_token')")}
def start_recording(name,with_mic=False):
    args=["ffmpeg","-hide_banner","-loglevel","error","-y","-thread_queue_size","512","-f","x11grab","-framerate","20","-video_size","1440x900","-i",os.environ["DISPLAY"],"-thread_queue_size","512","-f","pulse","-i","declic.monitor"]
    if with_mic:args+=["-thread_queue_size","512","-f","pulse","-i","studentmic.monitor","-filter_complex","[1:a][2:a]amix=inputs=2:duration=longest:normalize=0[a]","-map","0:v","-map","[a]"]
    else:args+=["-map","0:v","-map","1:a"]
    args+=["-c:v","libx264","-preset","ultrafast","-crf","23","-pix_fmt","yuv420p","-c:a","aac","-movflags","+faststart",str(OUT/name)]
    rec=subprocess.Popen(args,stdin=subprocess.PIPE)
    time.sleep(1)
    assert rec.poll() is None,"Recorder stopped"
    return rec
def end_recording(rec):
    if rec and rec.poll() is None:
        try:rec.communicate(b"q",timeout=20)
        except subprocess.TimeoutExpired:rec.terminate();rec.wait(timeout=10)
def audio_observer(page,records):
    def observe(r):
        if not r.url.endswith("/api/studio/audio"):return
        item={"status":r.status,"backend":r.headers.get("x-studio-voice")}
        if r.status==200:
            try:
                data=r.body()
                with wave.open(io.BytesIO(data)) as f:
                    import array
                    samples=array.array("h",f.readframes(f.getnframes()))
                    item["duration"]=len(samples)/max(1,f.getframerate()*f.getnchannels())
                    item["peak"]=max(map(abs,samples),default=0)
            except Exception as e:item["audio_read_error"]=str(e)[:100]
        records.append(item)
    page.on("response",observe)
def studio_settings(page,voice=True,generative=True):
    navigate(page,"studio")
    if page.locator("#studio-ai-mode").input_value()!="cloud":
        page.locator("#studio-ai-mode").select_option("cloud")
    page.locator("#studio-consent").check()
    page.locator("#studio-generative").set_checked(generative)
    page.locator("#studio-voice").set_checked(voice)
    if voice:page.locator("#studio-voice-engine").select_option("cloud")
def finish_audio(page,records,previous):
    wait(page,"document.querySelector('#studio-play').textContent.includes('Play')",timeout=200000)
    new=records[previous:]
    return bool(new) and any(x.get("status")==200 and x.get("peak",0)>50 and x.get("duration",0)>.3 for x in new) and page.locator("#studio-svg").get_attribute("data-audio")=="ended"
def save_results(extra=None):
    (OUT/"results.json").write_text(json.dumps({"main_commit":os.environ["TESTED_MAIN_SHA"],"checks":checks,"browser_errors":errors,**(extra or {})},indent=2,ensure_ascii=False))
def launch(p):
    return p.chromium.launch(headless=False,ignore_default_args=["--mute-audio"],args=["--no-sandbox","--window-size=1440,900","--window-position=0,0","--start-maximized","--autoplay-policy=no-user-gesture-required","--use-fake-ui-for-media-stream"])
