"""Course quizzes and opt-in teacher views; no access to student PDFs or chat."""
import hashlib
import json
import secrets
import uuid
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from .storage import db,one,all_rows,now
from .quizzes import build_questions,grade

class QuizRequest(BaseModel):
    document_id: str | None = None
    count: int = Field(12,ge=1,le=30)
    kind: str = Field('recall',pattern='^(recall|conceptual|course_ai)$')
    difficulty: str = Field('adaptive',pattern='^(easy|hard|adaptive)$')
    lang: str = Field('fr',pattern='^(fr|en)$')
    ai_mode: str = Field('hybrid',pattern='^(local|cloud|hybrid)$')
    consent_external: bool = False

class QuizAnswers(BaseModel):
    answers: dict[str,str] = Field(max_length=30)

class ClassroomRequest(BaseModel):
    name: str = Field(min_length=2,max_length=80)

class JoinRequest(BaseModel):
    code: str = Field(min_length=12,max_length=80)
    consent: bool = False

def install(app,user_from_token):
    @app.post("/api/quizzes",status_code=201)
    async def new_quiz(payload:QuizRequest,user=Depends(user_from_token)):
        sql="SELECT p.document_id,d.title,p.page,p.content FROM document_pages p JOIN documents d ON d.id=p.document_id WHERE d.user_id=?"
        params=[user["id"]]
        if payload.document_id:
            if not one("SELECT id FROM documents WHERE id=? AND user_id=?",(payload.document_id,user["id"])):raise HTTPException(404,"Document not found")
            sql+=" AND d.id=?";params.append(payload.document_id)
        pages=all_rows(sql+" ORDER BY d.created_at,d.id,p.page LIMIT 900",params)
        metadata={}
        if payload.kind=="course_ai":
            from .providers import use_mode
            from .course_ai import generate
            with use_mode(payload.ai_mode,payload.consent_external) as effective:
                if effective=="disabled":raise HTTPException(403,"Choose local AI or consent to cloud course processing")
                result=await generate(pages,payload.count,"medium" if payload.difficulty=="adaptive" else payload.difficulty,payload.lang)
            if not result:raise HTTPException(503,"No acceptable AI quiz generated. Try a shorter course or source recall.")
            questions,metadata=result
            for q in questions:
                if not one("SELECT id FROM documents WHERE id=? AND user_id=?",(q["document_id"],user["id"])):raise HTTPException(409,"Course changed during generation")
        elif payload.kind=="conceptual":
            from .concept_quiz import conceptual_questions
            scores=all_rows("SELECT concept,100.0*AVG(correct) AS score FROM attempts WHERE user_id=? GROUP BY concept",(user["id"],))
            questions=conceptual_questions(payload.count,payload.difficulty,{x["concept"]:x["score"] for x in scores},payload.lang)
        else:questions=build_questions(pages,payload.count)
        if not questions:raise HTTPException(422,"No suitable indexed course sentences. Import a readable PDF.")
        qid=uuid.uuid4().hex
        with db() as con:
            con.execute("INSERT INTO quizzes(id,user_id,questions,created_at) VALUES(?,?,?,?)",(qid,user["id"],json.dumps(questions,ensure_ascii=False),now()))
        return {"id":qid,"questions":[{k:v for k,v in q.items() if k not in ("answer","excerpt")} for q in questions],"eligible_pages":sum(bool(p["content"].strip()) for p in pages),"metadata":metadata,"note":"AI practice: exact source evidence, not guaranteed conceptual accuracy." if payload.kind=="course_ai" else "Verified statics practice; not a validated mastery score." if payload.kind=="conceptual" else "Source-exact recall, not conceptual mastery."}

    @app.post("/api/quizzes/{qid}/submit")
    def submit_quiz(qid:str,payload:QuizAnswers,user=Depends(user_from_token)):
        if any(len(v)>200 for v in payload.answers.values()):raise HTTPException(422,"Answer too long")
        with db() as con:
            row=con.execute("SELECT * FROM quizzes WHERE id=? AND user_id=?",(qid,user["id"])).fetchone()
            if not row:raise HTTPException(404,"Quiz not found")
            if row["results"] is not None:raise HTTPException(409,"Quiz already submitted")
            questions=json.loads(row["questions"])
            if set(payload.answers)!=set(q["id"] for q in questions):raise HTTPException(422,"Submit each question")
            if any(q.get("options") and payload.answers[q["id"]] not in q["options"] for q in questions):raise HTTPException(422,"Choose a listed option")
            results=grade(questions,payload.answers)
            report={"correct":sum(x["correct"] for x in results),"total":len(results),"results":results}
            if not con.execute("UPDATE quizzes SET results=? WHERE id=? AND results IS NULL",(json.dumps(report,ensure_ascii=False),qid)).rowcount:raise HTTPException(409,"Quiz already submitted")
        return report

    @app.get("/api/classrooms")
    def classrooms(user=Depends(user_from_token)):
        return {"owned":all_rows("SELECT id,name,created_at FROM classrooms WHERE teacher_id=? ORDER BY created_at",(user["id"],)),"joined":all_rows("SELECT c.id,c.name FROM classrooms c JOIN classroom_members m ON m.classroom_id=c.id WHERE m.user_id=?",(user["id"],))}

    @app.post("/api/classrooms",status_code=201)
    def create_class(payload:ClassroomRequest,user=Depends(user_from_token)):
        name=payload.name.strip()
        if len(name)<2:raise HTTPException(422,"Class name required")
        cid=uuid.uuid4().hex;code=secrets.token_urlsafe(18)
        with db() as con:
            con.execute("INSERT INTO classrooms VALUES(?,?,?,?,?)",(cid,user["id"],name,hashlib.sha256(code.encode()).hexdigest(),now()))
        return {"id":cid,"name":name,"join_code":code}

    @app.post("/api/classrooms/join")
    def join(payload:JoinRequest,user=Depends(user_from_token)):
        if not payload.consent:raise HTTPException(403,"Explicit sharing consent required")
        classroom=one("SELECT id,teacher_id,name FROM classrooms WHERE code_hash=?",(hashlib.sha256(payload.code.strip().encode()).hexdigest(),))
        if not classroom:raise HTTPException(404,"Class not found")
        if classroom["teacher_id"]==user["id"]:raise HTTPException(409,"Already class owner")
        with db() as con:
            con.execute("INSERT OR IGNORE INTO classroom_members VALUES(?,?,?)",(classroom["id"],user["id"],now()))
        return {"id":classroom["id"],"name":classroom["name"]}

    @app.get("/api/classrooms/{cid}/report")
    def report(cid:str,user=Depends(user_from_token)):
        classroom=one("SELECT id,name FROM classrooms WHERE id=? AND teacher_id=?",(cid,user["id"]))
        if not classroom:raise HTTPException(404,"Class not found")
        # Only attempts since explicit opt-in. No email, documents, raw answers or transcripts.
        rows=all_rows("""SELECT u.name,m.joined_at,COUNT(a.id) AS attempts,
         SUM(CASE WHEN a.stage='transfer' THEN 1 ELSE 0 END) AS transfer_attempts,
         SUM(CASE WHEN a.stage='transfer' AND a.correct=1 THEN 1 ELSE 0 END) AS transfer_correct
         FROM classroom_members m JOIN users u ON u.id=m.user_id
         LEFT JOIN attempts a ON a.user_id=m.user_id AND a.created_at>=m.joined_at
         WHERE m.classroom_id=? GROUP BY m.user_id ORDER BY u.name""",(cid,))
        return {"classroom":classroom,"learners":rows,"note":"Opt-in learning activity; not official grades."}

    @app.delete("/api/classrooms/{cid}/membership")
    def leave(cid:str,user=Depends(user_from_token)):
        with db() as con:con.execute("DELETE FROM classroom_members WHERE classroom_id=? AND user_id=?",(cid,user["id"]))
        return {"left":True}

    @app.delete("/api/classrooms/{cid}")
    def delete_class(cid:str,user=Depends(user_from_token)):
        with db() as con:
            if not con.execute("DELETE FROM classrooms WHERE id=? AND teacher_id=?",(cid,user["id"])).rowcount:raise HTTPException(404,"Class not found")
        return {"deleted":True}
