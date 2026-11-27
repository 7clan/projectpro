"""Evidence-based, intentionally simple rules: no unsupported risk prediction."""
from collections import defaultdict
from datetime import date
from .engine import CONCEPTS
from .storage import all_rows

RESOURCES = [
    {"id":"mit", "topic":"support_reactions", "title":"MIT OpenCourseWare — Engineering Mechanics: Statics", "publisher":"MIT OpenCourseWare", "type":"Cours universitaire", "url":"https://ocw.mit.edu/courses/1-050-solid-mechanics-fall-2004/", "desc":"Bases de l'équilibre et de la mécanique des structures.", "lang":"en"},
    {"id":"openstax", "topic":"force_balance", "title":"OpenStax University Physics — Static Equilibrium", "publisher":"OpenStax", "type":"Manuel libre", "url":"https://openstax.org/books/university-physics-volume-1/pages/12-1-conditions-for-static-equilibrium", "desc":"Conditions d'équilibre des forces et des moments.", "lang":"en"},
    {"id":"phET", "topic":"moment_equilibrium", "title":"PhET — Balancing Act", "publisher":"University of Colorado Boulder", "type":"Simulation", "url":"https://phet.colorado.edu/en/simulations/balancing-act", "desc":"Explorer visuellement l'influence des bras de levier.", "lang":"multi"},
    {"id":"mechanics", "topic":"load_transfer", "title":"MIT OpenCourseWare — Mechanics of Materials", "publisher":"MIT OpenCourseWare", "type":"Cours universitaire", "url":"https://ocw.mit.edu/courses/1-050-solid-mechanics-fall-2004/", "desc":"Approfondir le raisonnement mécanique avec de nouveaux cas.", "lang":"en"},
]


def profile(user_id, exam_date=None):
    rows = all_rows("SELECT stage,concept,correct,misconception,created_at FROM attempts WHERE user_id=? ORDER BY created_at DESC", (user_id,))
    by_concept = defaultdict(list)
    mistakes = defaultdict(int)
    for row in rows:
        by_concept[row["concept"]].append(row)
        if row["misconception"]:
            mistakes[row["misconception"]] += 1
    concepts=[]
    for item in CONCEPTS:
        subset=by_concept.get(item["id"], [])[:8]
        if subset:
            weights=[3 if r["stage"]=="transfer" else 1 for r in subset]
            score=round(100*(sum(w * r["correct"] for w,r in zip(weights, subset))+1)/(sum(weights)+2))
        else:
            score=None
        concepts.append({**item, "mastery":score, "attempts":len(by_concept.get(item["id"], [])), "status": "new" if score is None else "strong" if score>=80 else "developing" if score>=55 else "review"})
    primary=sorted(concepts,key=lambda c:(c["mastery"] if c["mastery"] is not None else 42, -c["importance"]))[0]
    repeat=[{"key":k,"count":v} for k,v in sorted(mistakes.items(),key=lambda kv:-kv[1]) if v>=2]
    days=None
    if exam_date:
        try: days=(date.fromisoformat(exam_date)-date.today()).days
        except ValueError: pass
    priority_kind="urgent" if days is not None and 0<=days<=3 else "normal"
    measured=[c for c in concepts if c["mastery"] is not None]
    return {
        "concepts":concepts,"attempt_count":len(rows),"average_mastery":round(sum(c["mastery"] for c in measured)/len(measured)) if measured else None,
        "strong_count":sum(c["status"]=="strong" for c in concepts),
        "repeat_mistakes":repeat,"days_until_exam":days,
        "priority": {"concept":primary["id"],"name_fr":primary["fr"],"name_en":primary["en"],"urgency":priority_kind,
            "steps_fr":[f"Revoir : {primary['fr']}","Prédire les réactions sans afficher la solution","Résoudre un nouveau cas indépendant"],
            "steps_en":[f"Review: {primary['en']}","Predict reactions before seeing the solution","Solve a new case independently"]},
        "alerts": [{"kind":"recurring","misconception":m["key"],"count":m["count"]} for m in repeat],
    }


def resources_for(profile_data):
    target=profile_data["priority"]["concept"]
    return sorted(RESOURCES,key=lambda r: 0 if r["topic"]==target else 1)

def study_plan(profile_data, minutes=30):
    """Allocate a bounded daily session from observed evidence, not a grade forecast."""
    minutes=max(10,min(120,int(minutes)))
    ordered=sorted(profile_data["concepts"],key=lambda c:(c["mastery"] if c["mastery"] is not None else 42,-c["importance"],c["id"]))
    urgent=profile_data["priority"]["urgency"]=="urgent"
    first,second=ordered[:2]
    review=max(3,round(minutes*.3))
    practice=max(4,round(minutes*(.5 if urgent else .4)))
    recall=minutes-review-practice
    return {"minutes":minutes,"urgent":urgent,"tasks":[
      {"concept":first["id"],"minutes":review,"fr":"Revoir : "+first["fr"],"en":"Review: "+first["en"],"view":"discover"},
      {"concept":first["id"],"minutes":practice,"fr":"Pratiquer : "+first["fr"],"en":"Practice: "+first["en"],"view":"lab"},
      {"concept":second["id"],"minutes":recall,"fr":"Expliquer et se tester : "+second["fr"],"en":"Explain and self-test: "+second["en"],"view":"studio"}
    ],"note_fr":"Plan indicatif fondé sur les essais récents, pas une prédiction de note.","note_en":"Suggested plan based on recent attempts, not a grade prediction."}
