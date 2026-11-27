"""Real browser classroom test against unchanged main code; synthetic accounts only."""
from pathlib import Path
import json, re, os
from playwright.sync_api import sync_playwright, expect

OUT=Path(os.environ["CLASSROOM_EVIDENCE"]).resolve()
OUT.mkdir(parents=True,exist_ok=True)
BASE="http://127.0.0.1:8000"
checks=[]
errors=[]
def check(name,condition=True):
    assert condition,name
    checks.append(name)
    print("PASS",name,flush=True)
def shot(page,name):
    page.screenshot(path=str(OUT/(name+".png")))
    page.wait_for_timeout(1400)
def response(page,method,suffix,action,status):
    with page.expect_response(lambda r:r.request.method==method and r.url.endswith(suffix),timeout=15000) as event:
        action()
    r=event.value
    assert r.status==status,(method,suffix,r.status)
    return r.json()
def login(page,name):
    page.goto(BASE)
    page.locator('#auth-form [name=name]').fill(name)
    page.locator('#auth-form [name=email]').fill(name.lower().replace(" ",".")+"@example.com")
    page.locator('#auth-form [name=password]').fill("TestClass2026!")
    response(page,"POST","/api/auth/register",lambda:page.locator('#auth-submit').click(),201)
    expect(page.locator('#auth-overlay')).to_be_hidden()
    page.wait_for_function("state.dashboard!==null && !state.labBusy")
    if page.evaluate("state.language")!="en":page.locator("#language").click()
    page.locator('[data-view=classroom]').click()
    expect(page.locator('#class-list')).to_contain_text("My classes")
def token(page):
    return {"Authorization":"Bearer "+page.evaluate("localStorage.getItem('declic_token')")}
def solve(q):
    # Independent statics formulas, not reading a database or answer key.
    prompt=q["prompt"]
    m=re.search(r"L=(\d+(?:\.\d+)?) m, P=(\d+(?:\.\d+)?) kN at (\d+(?:\.\d+)?) m from A, q=(\d+(?:\.\d+)?) kN/m",prompt)
    assert m,prompt
    L,P,a,w=map(float,m.groups())
    if "RA + RB" in prompt:v=P+w*L
    elif "absolute load moment" in prompt:v=P*a+w*L*L/2
    elif "reaction RB" in prompt:v=(P*a+w*L*L/2)/L
    else:
        assert "moves toward B" in prompt,prompt
        return "It increases"
    for o in q["options"]:
        if abs(float(o.split()[0])-v)<.0001:return o
    raise AssertionError("Correct independent result absent from options")
with sync_playwright() as p:
    browser=p.chromium.launch()
    teacher_context=browser.new_context(viewport={"width":1440,"height":900},record_video_dir=str(OUT/"teacher"),record_video_size={"width":1440,"height":900})
    student_context=browser.new_context(viewport={"width":1440,"height":900},record_video_dir=str(OUT/"student"),record_video_size={"width":1440,"height":900})
    teacher=teacher_context.new_page()
    student=student_context.new_page()
    for page in (teacher,student):
        page.on("pageerror",lambda e:errors.append(str(e)))
    try:
        login(teacher,"Demo Teacher")
        login(student,"Demo Student")
        teacher.locator('#class-name').fill("RDM2 - Mechanics demonstration")
        classroom=response(teacher,"POST","/api/classrooms",lambda:teacher.locator('#class-create button').click(),201)
        cid=classroom["id"];code=classroom["join_code"];base="/api/classrooms/"+cid
        expect(teacher.locator('#class-code')).to_contain_text(code)
        expect(teacher.locator('#class-list')).to_contain_text("RDM2 - Mechanics demonstration")
        check("Teacher created class and received invitation code")
        shot(teacher,"01-teacher-class-created")
        student.locator('#class-join-code').fill(code)
        # Direct API negative test: no consent means no membership.
        denied=student.request.post(BASE+"/api/classrooms/join",headers=token(student),data={"code":code,"consent":False})
        check("Joining without consent blocked",denied.status==403)
        student.locator('#class-consent').check()
        response(student,"POST","/api/classrooms/join",lambda:student.locator('#class-join button').click(),200)
        expect(student.locator('#class-list')).to_contain_text("RDM2 - Mechanics demonstration")
        check("Student joined with consent")
        shot(student,"02-student-joined")
        teacher.locator('#class-list').get_by_role("button",name="Report",exact=True).click()
        expect(teacher.locator('#class-report')).to_contain_text("Demo Student")
        check("Teacher sees opted-in learner")
        shot(teacher,"03-teacher-learner-report")
        teacher.locator('#class-list').get_by_role("button",name="Assignments",exact=True).click()
        expect(teacher.locator('#assignment-panel')).to_contain_text("Teacher identity unverified")
        teacher.locator('#assignment-panel').get_by_label("Assignment title").fill("Statics practice - equilibrium")
        teacher.locator('#assignment-panel').get_by_label("Suggested due date").fill("2026-12-01")
        teacher.locator('#assignment-panel').get_by_label("Difficulty").select_option("easy")
        assignment=response(teacher,"POST",base+"/assignments",lambda:teacher.get_by_role("button",name="Publish 6 MCQs").click(),201)
        aid=assignment["id"]
        expect(teacher.locator('#assignment-panel')).to_contain_text("Statics practice - equilibrium")
        expect(teacher.locator('#assignment-panel')).to_contain_text("Submissions (0)")
        check("Teacher published six statics MCQs",assignment["count"]==6)
        shot(teacher,"04-teacher-published-assignment")
        student.locator('#class-list').get_by_role("button",name="Assignments",exact=True).click()
        expect(student.locator('#assignment-panel')).to_contain_text("Statics practice - equilibrium")
        quiz=response(student,"GET",base+"/assignments/"+aid,lambda:student.locator('#assignment-panel').get_by_role("button",name="Start",exact=True).click(),200)
        check("Student received six questions without answer key",len(quiz["questions"])==6 and all("answer" not in q and "excerpt" not in q for q in quiz["questions"]))
        check("Student cannot read teacher report",student.request.get(BASE+base+"/assignments/"+aid+"/report",headers=token(student)).status==404)
        shot(student,"05-student-opens-assignment")
        answers={}
        for i,q in enumerate(quiz["questions"]):
            correct=solve(q)
            answer=next(o for o in q["options"] if o!=correct) if i==0 else correct
            answers[q["id"]]=answer
            select=student.locator('#assignment-panel select[name="'+q["id"]+'"]')
            select.select_option(answer)
            select.scroll_into_view_if_needed()
            student.wait_for_timeout(500)
        score=response(student,"POST",base+"/assignments/"+aid+"/submit",lambda:student.locator('#assignment-panel').get_by_role("button",name="Submit",exact=True).click(),200)
        check("Independent calculation produced expected 5/6",score["correct"]==5 and score["total"]==6)
        expect(student.locator('#assignment-panel')).to_contain_text("5/6")
        shot(student,"06-student-graded-result")
        duplicate=student.request.post(BASE+base+"/assignments/"+aid+"/submit",headers=token(student),data={"answers":answers})
        check("Duplicate submission blocked",duplicate.status==409)
        teacher.locator('#class-list').get_by_role("button",name="Assignments",exact=True).click()
        expect(teacher.locator('#assignment-panel')).to_contain_text("Submissions (1)")
        report=response(teacher,"GET",base+"/assignments/"+aid+"/report",lambda:teacher.get_by_role("button",name="Submissions (1)").click(),200)
        expect(teacher.locator('#assignment-panel')).to_contain_text("Demo Student · 5/6")
        check("Teacher sees correct submission and score",len(report["submissions"])==1 and report["submissions"][0]["correct"]==5)
        check("Teacher report contains no student email or raw answers",all(set(x)=={"name","correct","total","submitted_at"} for x in report["submissions"]))
        shot(teacher,"07-teacher-score-report")
        student.reload()
        expect(student.locator('#auth-overlay')).to_be_hidden()
        student.locator('[data-view=classroom]').click()
        expect(student.locator('#class-list')).to_contain_text("RDM2 - Mechanics demonstration")
        student.locator('#class-list').get_by_role("button",name="Assignments",exact=True).click()
        expect(student.locator('#assignment-panel')).to_contain_text("5/6")
        check("Student score survives reload")
        shot(student,"08-student-persisted-score")
        response(student,"DELETE",base+"/membership",lambda:student.locator('#class-list').get_by_role("button",name="Leave and stop sharing").click(),200)
        expect(student.locator('#class-list')).to_contain_text("No classes")
        check("Student revoked class membership")
        check("Former student cannot open assignment",student.request.get(BASE+base+"/assignments/"+aid,headers=token(student)).status==404)
        shot(student,"09-student-left")
        teacher.locator('#class-list').get_by_role("button",name="Report",exact=True).click()
        expect(teacher.locator('#class-report')).to_contain_text("No participants")
        check("Teacher activity report no longer lists former member")
        shot(teacher,"10-teacher-membership-revoked")
        check("No browser JavaScript errors",not errors)
    finally:
        teacher_context.close()
        student_context.close()
        browser.close()
        (OUT/"results.json").write_text(json.dumps({"main_commit":os.environ["TESTED_MAIN_SHA"],"checks":checks,"browser_errors":errors},indent=2))
