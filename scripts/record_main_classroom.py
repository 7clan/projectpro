from acceptance_main_common import *
from playwright.sync_api import sync_playwright
import random

CLASS="RDM2 - Mechanics demonstration"
scores={}
audio=[]
seed=20261127
rng=random.Random(seed)
targets=rng.sample([2,3,4,5,6],3)
def open_classes(page):
    navigate(page,"classroom")
    expect(page.locator("#class-list")).to_contain_text("My classes")
def open_assignments(page):
    open_classes(page)
    expect(page.locator("#class-list")).to_contain_text(CLASS)
    page.locator("#class-list").get_by_role("button",name="Assignments",exact=True).click()
    expect(page.locator("#assignment-panel")).to_contain_text("Class assignments")
def publish(page,title):
    open_assignments(page)
    expect(page.locator("#assignment-panel")).to_contain_text("Teacher identity unverified")
    page.get_by_label("Assignment title").fill(title)
    page.get_by_label("Suggested due date").fill("2026-12-01")
    page.get_by_label("Difficulty").select_option("easy")
    a=response(page,"POST",base+"/assignments",lambda:page.get_by_role("button",name="Publish 6 MCQs").click(),201)
    expect(page.locator("#assignment-panel")).to_contain_text(title)
    assert a["count"]==6
    return a["id"]
def solve(q):
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
    return next(o for o in q["options"] if abs(float(o.split()[0])-v)<.0001)
def attempt(page,aid,title,target,tag,force_moment_error=False):
    open_assignments(page)
    row=page.locator("#assignment-panel .course-question").filter(has_text=title).first
    q=response(page,"GET",base+"/assignments/"+aid,lambda:row.get_by_role("button",name="Start",exact=True).click())
    assert len(q["questions"])==6 and all("answer" not in x for x in q["questions"])
    wrong=set(rng.sample(range(6),6-target))
    if force_moment_error and wrong and 1 not in wrong:wrong.remove(next(iter(wrong)));wrong.add(1)
    for i,x in enumerate(q["questions"]):
        correct=solve(x)
        option=rng.choice([o for o in x["options"] if o!=correct]) if i in wrong else correct
        select=row.locator('select[name="'+x["id"]+'"]')
        select.scroll_into_view_if_needed()
        select.select_option(option)
        page.wait_for_timeout(600)
    result=response(page,"POST",base+"/assignments/"+aid+"/submit",lambda:row.get_by_role("button",name="Submit",exact=True).click())
    assert result["correct"]==target and result["total"]==6,result
    expect(row).to_contain_text(f"{target}/6")
    shot(page,tag)
    return result
with sync_playwright() as p:
    browser=launch(p)
    contexts=[browser.new_context(no_viewport=True) for _ in range(4)]
    pages=[c.new_page() for c in contexts]
    teacher,*students=pages
    names=["Student Maya","Student Karim","Student Lina"]
    rec=None
    try:
        rec=start_recording("01-classroom-full-workflow.mp4")
        setup(teacher,"Demo Teacher")
        open_classes(teacher)
        teacher.locator("#class-name").fill(CLASS)
        c=response(teacher,"POST","/api/classrooms",lambda:teacher.locator("#class-create button").click(),201)
        base="/api/classrooms/"+c["id"]
        expect(teacher.locator("#class-code")).to_contain_text(c["join_code"])
        check("Teacher created class and invitation")
        shot(teacher,"01-teacher-invite")
        for page,name in zip(students,names):
            setup(page,name);open_classes(page)
            page.locator("#class-join-code").fill(c["join_code"])
            page.locator("#class-consent").check()
            response(page,"POST","/api/classrooms/join",lambda:page.locator("#class-join button").click())
            expect(page.locator("#class-list")).to_contain_text(CLASS)
            check(name+" joined with consent")
            shot(page,name.replace(" ","-")+"-joined")
        open_classes(teacher)
        teacher.locator("#class-list").get_by_role("button",name="Report",exact=True).click()
        for name in names:expect(teacher.locator("#class-report")).to_contain_text(name)
        check("Teacher sees all three learners")
        shot(teacher,"02-roster")
        aid=publish(teacher,"Assignment 1 - Statics")
        check("Teacher published six questions")
        shot(teacher,"03-assignment")
        lowest=targets.index(min(targets))
        for i,(page,name,target) in enumerate(zip(students,names,targets)):
            attempt(page,aid,"Assignment 1 - Statics",target,name.replace(" ","-")+"-result",i==lowest)
            scores[name]=target
            check(name+" independently graded",score=target,total=6)
        open_assignments(teacher)
        row=teacher.locator("#assignment-panel .course-question").filter(has_text="Assignment 1 - Statics").first
        expect(row).to_contain_text("Submissions (3)")
        report=response(teacher,"GET",base+"/assignments/"+aid+"/report",lambda:row.get_by_role("button",name="Submissions (3)").click())
        assert {x["name"]:x["correct"] for x in report["submissions"]}==scores
        for name,target in scores.items():expect(row).to_contain_text(f"{name} · {target}/6")
        check("Teacher sees all three real scores",scores=scores)
        shot(teacher,"04-teacher-scores")
        student=students[lowest];name=names[lowest]
        navigate(student,"coach")
        student.locator("#chat-input").fill("I got the moment question wrong on my statics assignment. I confuse the force with the lever arm. Teach me a simple way to calculate a moment and give me a different practice example, not the assignment answer.")
        coach=response(student,"POST","/api/coach",lambda:student.locator("#chat-form button").click(),timeout=100000)
        expect(student.locator(".coach-message").last).to_be_visible()
        (OUT/"coach-response.json").write_text(json.dumps(coach,ensure_ascii=False,indent=2))
        check("Lowest-scoring student receives actual AI coaching",coach.get("mode")=="live_ai" and bool(coach.get("model")),provider=coach.get("provider"),model=coach.get("model"))
        shot(student,"05-individual-coach")
        audio_observer(student,audio)
        studio_settings(student,True,False)
        student.locator("#studio-question").fill("Explain the moment of a force and its lever arm using the statics diagram.")
        prev=len(audio)
        lesson=response(student,"POST","/api/studio",lambda:student.locator("#studio-send").click(),timeout=150000)
        (OUT/"student-studio.json").write_text(json.dumps(lesson,ensure_ascii=False,indent=2))
        check("Student received live AI narrated statics explanation",lesson.get("mode")=="live_ai",provider=lesson.get("provider"),model=lesson.get("model"))
        check("Classroom recording includes audible app narration",finish_audio(student,audio,prev),audio=audio)
        shot(student,"06-studio-after-coach")
        aid2=publish(teacher,"Assignment 2 - Follow-up practice")
        after=min(6,targets[lowest]+2)
        attempt(student,aid2,"Assignment 2 - Follow-up practice",after,"07-student-followup")
        open_assignments(teacher)
        row=teacher.locator("#assignment-panel .course-question").filter(has_text="Assignment 2 - Follow-up practice").first
        report=response(teacher,"GET",base+"/assignments/"+aid2+"/report",lambda:row.get_by_role("button",name="Submissions (1)").click())
        check("Teacher sees follow-up practice score",report["submissions"][0]["correct"]==after,student=name,before=targets[lowest],after=after,simulation=True)
        shot(teacher,"08-followup-teacher-report")
        check("No browser JavaScript errors",not errors)
    finally:
        end_recording(rec)
        for c in contexts:c.close()
        browser.close()
        save_results({"scores":scores,"seed":seed,"simulated_answer_choices":True,"audio":audio})
assert checks and all(c["passed"] for c in checks),checks
