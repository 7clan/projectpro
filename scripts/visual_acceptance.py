"""Recorded real cloud Studio acceptance; no fixtures, interception or mocked inference.

Records silent Chromium video (speech is deliberately disabled). JSON, geometry
assertions and screenshots accompany each case, even when a case fails.
"""
import json
import math
import os
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUT=Path("visual-evidence")
OUT.mkdir(exist_ok=True)
CASES=[
    ("triangle-5-12","en","Explain the Pythagorean theorem using a right triangle with sides of 5 and 12 units. Animate the construction of the three squares and demonstrate why their areas satisfy the theorem.",(5,12)),
    ("triangle-8-15-fr","fr","Explique visuellement le théorème de Pythagore avec les côtés perpendiculaires de 8 et 15 unités. Construis les trois carrés.",(8,15)),
    ("newton-double","en","Explain Newton's second law using a 4 kg object subjected to a force of 20 N. Animate the object accelerating and demonstrate what happens when the force doubles.",None)
]

def geometry(points,legs):
    # Independently check exact shape topology, side ratio and outward squares.
    a,b=legs
    assert sorted(map(len,points))==[3,4,4,4], "Expected a triangle and three squares"
    tri=next(p for p in points if len(p)==3)
    squares=[p for p in points if len(p)==4]
    def v(p,q):return(q[0]-p[0],q[1]-p[1])
    def dot(x,y):return x[0]*y[0]+x[1]*y[1]
    def cross(x,y):return x[0]*y[1]-x[1]*y[0]
    assert math.isclose(math.dist(tri[0],tri[1])/math.dist(tri[0],tri[2]),a/b,rel_tol=.0001)
    assert abs(dot(v(tri[0],tri[1]),v(tri[0],tri[2])))<.03
    for i in range(3):
        p,q=tri[i],tri[(i+1)%3]
        sq=next((s for s in squares if s[:2]==[p,q]),None)
        assert sq is not None, "Detached square"
        edges=[v(sq[j],sq[(j+1)%4]) for j in range(4)]
        lengths=[math.hypot(*e) for e in edges]
        assert min(lengths)>0 and max(lengths)-min(lengths)<.03
        assert abs(dot(edges[0],edges[1]))<.03
        assert cross(edges[0],v(p,sq[2]))*cross(edges[0],v(p,tri[(i+2)%3]))<0

def check_response(lesson,legs):
    assert lesson["mode"]=="live_ai" and lesson["visual_mode"]=="generated",lesson.get("notice")
    assert lesson.get("provider") in ("openrouter","gemini","bazaarlink")
    assert lesson.get("model")
    assert len(lesson["steps"])==2
    last=lesson["steps"][-1]
    labels={o["text"] for o in last["objects"] if o["kind"]=="text"}
    if legs:
        a,b=legs
        assert labels=={str(a*a),str(b*b),str(a*a+b*b)},labels
        assert last["formula"]==f"{a*a} + {b*b} = {a*a+b*b}"
        geometry([o["points"] for o in last["objects"] if o["kind"]=="polygon"],legs)
        assert not any(o["kind"]=="circle" for o in last["objects"])
        assert any(c.get("op")=="pythagoras" and c.get("operands")==[a,b] and c.get("result")==math.hypot(a,b) for c in lesson["numerical_checks"])
    else:
        assert lesson["steps"][0]["formula"]=="a = 20 / 4 = 5 m/s²"
        assert last["formula"]=="a = 40 / 4 = 10 m/s²"
        assert {"m = 4 kg","F = 40 N","a = 10 m/s²"}<=labels,labels
        arrows=[next(o for o in s["objects"] if o["kind"]=="arrow") for s in lesson["steps"]]
        assert arrows[1]["x2"]-arrows[1]["x"]==2*(arrows[0]["x2"]-arrows[0]["x"])

def main():
    assert any(os.getenv(k) for k in ("GEMINI_API_KEY","OPENROUTER_API_KEY","BAZAARLINK_API_KEY")),"No configured cloud secret"
    results=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        for name,lang,question,legs in CASES:
            context=browser.new_context(viewport={"width":1440,"height":1000},record_video_dir=str(OUT),record_video_size={"width":1440,"height":1000})
            page=context.new_page()
            video=page.video
            errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            result={"case":name,"passed":False}
            try:
                page.goto("http://127.0.0.1:8000")
                page.locator("#demo-login").click()
                # Wait until setupUser has actually fetched /api/health and
                # configured available modes. A single available mode is locked
                # by design: do not attempt to select it when already chosen.
                expect(page.locator("#ai-mode")).to_contain_text(
                    re.compile(r"· (openrouter|gemini|bazaarlink)"),timeout=30000)
                page.locator('[data-view="studio"]').click()
                if page.locator("html").get_attribute("lang")!=lang:
                    page.locator("#language").click()
                mode=page.locator("#studio-ai-mode")
                if mode.input_value()!="cloud":
                    mode.select_option("cloud",timeout=30000)
                expect(mode).to_have_value("cloud")
                assert page.locator('#studio-ai-mode option[value="cloud"]').get_attribute("disabled") is None,"Cloud mode unavailable"
                page.locator("#studio-consent").check()
                page.locator("#studio-generative").check()
                page.locator("#studio-voice").uncheck()
                page.locator("#studio-question").fill(question)
                with page.expect_response(lambda r:r.url.endswith("/api/studio") and r.request.method=="POST",timeout=180000) as event:
                    page.locator("#studio-send").click()
                lesson=event.value.json()
                (OUT/(name+".json")).write_text(json.dumps(lesson,ensure_ascii=False,indent=2))
                result.update(provider=lesson.get("provider"),model=lesson.get("model"),status=event.value.status)
                expect(page.locator("#studio-send")).to_be_enabled(timeout=20000)
                # Finish playback before evaluating the actual SVG (not only payload).
                if lesson.get("steps"):
                    expect(page.locator("#studio-count")).to_have_text(f'{len(lesson["steps"])} / {len(lesson["steps"])}',timeout=90000)
                    expect(page.locator("#studio-play")).to_contain_text("Play",timeout=90000)
                page.locator("#studio-svg").scroll_into_view_if_needed()
                page.screenshot(path=str(OUT/(name+"-final.png")))
                check_response(lesson,legs)
                svg=page.locator("#studio-svg")
                if legs:
                    points=svg.locator("polygon").evaluate_all("(nodes)=>nodes.map(n=>Array.from(n.points,p=>[p.x,p.y]))")
                    # SVG float32 coordinates have tiny rounding differences;
                    # topology uses same shared vertices, tolerance for dot products.
                    geometry(points,legs)
                    assert svg.locator("circle").count()==0
                else:
                    expect(svg).to_contain_text("a = 10 m/s²")
                expect(page.locator("#studio-formula")).to_be_visible()
                assert svg.locator('[data-label-collision="true"]').count()==0,"Label collision"
                assert not errors,errors
                result["passed"]=True
                print("PASS",name,result,flush=True)
            except Exception as exc:
                result["error"]=str(exc)[:400]
                print("FAIL",name,result,flush=True)
                page.screenshot(path=str(OUT/(name+"-failure.png")))
            finally:
                context.close()
                if video:
                    video.save_as(str(OUT/(name+".webm")))
                    video.delete()
                results.append(result)
                (OUT/"results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2))
        browser.close()
    assert all(r["passed"] for r in results),results

if __name__=="__main__":main()
