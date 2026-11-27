"""Teacher-created deterministic practice assignments. No private student content."""
import os
import json
import uuid
from datetime import date
from fastapi import Depends,HTTPException
from pydantic import BaseModel,Field
from .storage import db,one,all_rows,now
from .concept_quiz import conceptual_questions
from .quizzes import grade

def approved(uid):
    return uid in {x.strip() for x in os.getenv("DECLIC_APPROVED_TEACHER_IDS","").split(",") if x.strip()}

class AssignmentRequest(BaseModel):
    title:str=Field(min_length=2,max_length=100)
    count:int=Field(6,ge=1,le=20)
    difficulty:str=Field("easy",pattern="^(easy|hard)$")
    lang:str=Field("fr",pattern="^(fr|en)$")
    due_date:date|None=None

class Answers(BaseModel):
    answers:dict[str,str]=Field(max_length=20)

def install(app,user_from_token):
    def teacher(cid,uid):
        c=one("SELECT id,name,teacher_id FROM classrooms WHERE id=? AND teacher_id=?",(cid,uid))
        if not c:raise HTTPException(404,"Class not found")
        return c
    def member(cid,uid):
        if not one("SELECT user_id FROM classroom_members WHERE classroom_id=? AND user_id=?",(cid,uid)):
            raise HTTPException(404,"Class membership required")
    @app.get("/api/teacher/status")
    def status(user=Depends(user_from_token)):
        return {"account_id":user["id"],"operator_approved":approved(user["id"]),"note":"Approval is configured by the operator after an external identity check; no automated institutional verification."}
    @app.post("/api/classrooms/{cid}/assignments",status_code=201)
    def create(cid:str,payload:AssignmentRequest,user=Depends(user_from_token)):
        teacher(cid,user["id"])
        if os.getenv("DECLIC_REQUIRE_APPROVED_TEACHER")=="1" and not approved(user["id"]):raise HTTPException(403,"Operator approval required")
        title=payload.title.strip()
        if len(title)<2:raise HTTPException(422,"Title required")
        due=payload.due_date.isoformat() if payload.due_date else None
        questions=conceptual_questions(payload.count,payload.difficulty,lang=payload.lang)
        aid=uuid.uuid4().hex
        with db() as con:con.execute("INSERT INTO class_assignments VALUES(?,?,?,?,?,?)",(aid,cid,title,json.dumps(questions,ensure_ascii=False),now(),due))
        return {"id":aid,"title":title,"due_date":due,"count":len(questions)}
    @app.get("/api/classrooms/{cid}/assignments")
    def assignments(cid:str,user=Depends(user_from_token)):
        owner=bool(one("SELECT id FROM classrooms WHERE id=? AND teacher_id=?",(cid,user["id"])))
        if not owner:member(cid,user["id"])
        rows=all_rows("SELECT id,title,due_date,created_at FROM class_assignments WHERE classroom_id=? ORDER BY created_at DESC",(cid,))
        for a in rows:
            if owner:
                a["submitted"]=one("SELECT COUNT(*) AS n FROM class_submissions WHERE assignment_id=?",(a["id"],))["n"]
            else:
                a["score"]=one("SELECT correct,total,submitted_at FROM class_submissions WHERE assignment_id=? AND user_id=?",(a["id"],user["id"]))
        return {"owner":owner,"assignments":rows}
    @app.get("/api/classrooms/{cid}/assignments/{aid}")
    def assignment(cid:str,aid:str,user=Depends(user_from_token)):
        member(cid,user["id"])
        a=one("SELECT * FROM class_assignments WHERE id=? AND classroom_id=?",(aid,cid))
        if not a:raise HTTPException(404,"Assignment not found")
        score=one("SELECT correct,total,submitted_at FROM class_submissions WHERE assignment_id=? AND user_id=?",(aid,user["id"]))
        questions=json.loads(a["questions"])
        return {"id":aid,"title":a["title"],"due_date":a["due_date"],"score":score,"questions":[{k:v for k,v in q.items() if k not in ("answer","excerpt")} for q in questions] if not score else []}
    @app.post("/api/classrooms/{cid}/assignments/{aid}/submit")
    def submit(cid:str,aid:str,payload:Answers,user=Depends(user_from_token)):
        member(cid,user["id"])
        with db() as con:
            a=con.execute("SELECT * FROM class_assignments WHERE id=? AND classroom_id=?",(aid,cid)).fetchone()
            if not a:raise HTTPException(404,"Assignment not found")
            if not con.execute("SELECT 1 FROM classroom_members WHERE classroom_id=? AND user_id=?",(cid,user["id"])).fetchone():raise HTTPException(404,"Class membership required")
            questions=json.loads(a["questions"])
            if set(payload.answers)!=set(q["id"] for q in questions) or any(payload.answers[q["id"]] not in q["options"] for q in questions):raise HTTPException(422,"Choose an answer for each question")
            results=grade(questions,payload.answers)
            correct=sum(r["correct"] for r in results)
            if not con.execute("INSERT OR IGNORE INTO class_submissions VALUES(?,?,?,?,?,?)",(aid,cid,user["id"],correct,len(results),now())).rowcount:raise HTTPException(409,"Already submitted")
        return {"correct":correct,"total":len(results),"results":results}
    @app.get("/api/classrooms/{cid}/assignments/{aid}/report")
    def report(cid:str,aid:str,user=Depends(user_from_token)):
        teacher(cid,user["id"])
        a=one("SELECT id,title FROM class_assignments WHERE id=? AND classroom_id=?",(aid,cid))
        if not a:raise HTTPException(404,"Assignment not found")
        rows=all_rows("SELECT u.name,s.correct,s.total,s.submitted_at FROM class_submissions s JOIN users u ON u.id=s.user_id WHERE s.assignment_id=? ORDER BY s.submitted_at",(aid,))
        return {"assignment":a,"submissions":rows}
    @app.get("/api/classrooms/{cid}/trends")
    def trends(cid:str,user=Depends(user_from_token)):
        teacher(cid,user["id"])
        return {"weeks":all_rows("""SELECT strftime('%Y-%W',a.created_at) AS week,COUNT(*) AS attempts,SUM(a.correct) AS correct
        FROM attempts a JOIN classroom_members m ON a.user_id=m.user_id WHERE m.classroom_id=? AND a.created_at>=m.joined_at
        GROUP BY week ORDER BY week DESC LIMIT 12""",(cid,))}
