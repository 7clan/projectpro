"""Best-effort AI lesson adapter. Strict renderer remains the security boundary.

Only recoverable model output is displayed. No generated code is executed.
Scientific checks are advisory; never silently change an AI's calculation.
"""
import json
import math
import re
from pydantic_core import from_json

def bounded(value,lo,hi,default):
    if isinstance(value,str):
        try:value=float(value)
        except ValueError:value=default
    if type(value) not in (int,float) or not math.isfinite(value):value=default
    return min(hi,max(lo,value))

def clean_text(value,limit):
    return value.strip()[:limit] if isinstance(value,str) else ""

def recover_lesson(raw,question,lang):
    from .whiteboard import validate_compact,validate_board,KINDS,COLORS,MOTIONS,validate_lesson
    from .numerical_checks import validate_checks,verify_formula,verify_subject_labels
    if not isinstance(raw,str) or not raw.strip() or len(raw)>45000:raise ValueError("No usable model response")
    fr=lang=="fr"
    words={
        "layout": "Mise en page adaptée" if fr else "Layout adapted",
        "omitted":"Éléments graphiques incomplets omis" if fr else "Incomplete graphic elements omitted",
        "partial":"Réponse partielle" if fr else "Partial AI response",
        "math":"Calcul à vérifier" if fr else "Calculation needs review",
        "text":"Schéma indisponible · explication IA conservée" if fr else "Diagram unavailable · AI explanation preserved"
    }
    warnings=[]
    def warn(k):
        if words[k] not in warnings:warnings.append(words[k])
    start=raw.find("{")
    if start<0:
        # Plain explanation can still be read and narrated.
        text=clean_text(raw,450)
        if not text:raise ValueError("No usable explanation")
        data={"steps":[{"title":"Explication" if fr else "Explanation","narration":text,"objects":[]}]}
        warn("text")
    else:
        try:
            end=raw.rfind("}")
            if end<start:raise json.JSONDecodeError("Incomplete JSON",raw,start)
            data=json.loads(raw[start:end+1])
        except (ValueError,RecursionError):
            try:data=from_json(raw[start:].encode(),allow_partial=True)
            except (ValueError,RecursionError):raise ValueError("No recoverable lesson JSON") from None
            warn("partial")
    if not isinstance(data,dict):raise ValueError("No usable lesson")
    # Fast path keeps complete well-formed AI geometry exactly as authored.
    try:
        steps=validate_compact(json.dumps(data,ensure_ascii=False),min_steps=1)
    except (ValueError,KeyError,TypeError,IndexError,AttributeError,RecursionError):
        steps=[]
        compact="steps" not in data
        scenes=data.get("s" if compact else "steps",[])
        if not isinstance(scenes,list):raise ValueError("No usable scenes")
        library=data.get("library",[])
        shared={o["id"]:o for o in library[:32] if isinstance(o,dict) and isinstance(o.get("id"),str)} if isinstance(library,list) else {}
        for scene in scenes[:5]:
            if not isinstance(scene,dict):warn("partial");continue
            title=clean_text(scene.get("h" if compact else "title"),80) or ("Explication" if fr else "Explanation")
            speech=clean_text(scene.get("n" if compact else "narration"),450)
            if not speech:warn("partial");continue
            formula=clean_text(scene.get("e" if compact else "formula"),120) or "—"
            source=scene.get("o" if compact else "objects",[])
            refs=scene.get("use",[]) if compact else []
            if not isinstance(source,list):source=[];warn("omitted")
            if not isinstance(refs,list):refs=[]
            source=[shared[r] for r in refs[:32] if isinstance(r,str) and r in shared]+source[:32]
            normalized=[]
            for obj in source[:32]:
                if not isinstance(obj,dict):warn("omitted");continue
                o=dict(obj)
                kind=o.get("k" if compact else "kind")
                if not isinstance(kind,str) or kind not in KINDS|{"right_triangle","square_on_segment","right_triangle_squares"}:
                    warn("omitted");continue
                before=dict(o)
                if compact:
                    p=o.get("p")
                    if kind=="text" and isinstance(p,list) and len(p)==2:o["p"]=p+[18]
                    elif kind=="text" and isinstance(p,list) and len(p)>=3:o["p"]=p[:2]+[bounded(p[2],12,32,18)]
                    # A line/arrow needs two endpoints; a circle needs center and radius.
                    # Ignore surplus fields only when all required geometry is present.
                    sizes={"line":4,"arrow":4,"rect":4,"circle":3,"ellipse":4}
                    if kind in sizes and isinstance(p,list) and len(p)>sizes[kind]:o["p"]=p[:sizes[kind]]
                    if kind=="text":o["v"]=clean_text(o.get("v"),100)
                    for name,lo,hi,default in (("t",0,.9,0),("f",0,1,0),("w",1,10,3),("d",.2,4,1)):
                        if name in o:o[name]=bounded(o[name],lo,hi,default)
                    if not isinstance(o.get("c","ink"),str) or o.get("c","ink") not in COLORS:o["c"]="ink"
                    if not isinstance(o.get("m","draw"),str) or o.get("m","draw") not in MOTIONS:o["m"]="draw"
                else:
                    if kind=="text":
                        o["size"]=bounded(o.get("size",18),12,32,18)
                        o["text"]=clean_text(o.get("text"),100)
                    for name,lo,hi,default in (("at",0,.9,0),("fill",0,1,0),("width",1,10,3),("duration",.2,4,1)):
                        if name in o:o[name]=bounded(o[name],lo,hi,default)
                    if not isinstance(o.get("color","ink"),str) or o.get("color","ink") not in COLORS:o["color"]="ink"
                    if not isinstance(o.get("motion","draw"),str) or o.get("motion","draw") not in MOTIONS:o["motion"]="draw"
                if "id" in o:
                    from .visual_checks import ID
                    if not isinstance(o["id"],str) or not ID.fullmatch(o["id"]):o.pop("id")
                if o!=before:warn("layout")
                normalized.append(o)
            def render(objs):
                payload={"s":[{"h":title,"n":speech,"e":formula,"o":objs}]} if compact else {"steps":[{"title":title,"narration":speech,"formula":formula,"objects":objs}]}
                return validate_compact(json.dumps(payload,ensure_ascii=False),min_steps=1)[0]
            try:
                step=render(normalized)
            except (ValueError,KeyError,TypeError,IndexError,AttributeError,RecursionError):
                # Keep valid objects, never invent missing endpoints or dimensions.
                usable=[]
                for o in normalized:
                    try:render([o]);usable.append(o)
                    except (ValueError,KeyError,TypeError,IndexError,AttributeError,RecursionError):warn("omitted")
                try:step=render(usable)
                except (ValueError,KeyError,TypeError,IndexError,AttributeError,RecursionError):
                    # Do not independently reposition shapes and imply a false relationship.
                    warn("text")
                    step=validate_board(json.dumps({"steps":[{"title":title,"narration":speech,"formula":formula,"objects":[{"kind":"text","x":300,"y":160,"size":20,"text":"Schéma indisponible" if fr else "Diagram unavailable"}]}]},ensure_ascii=False),min_steps=1)[0]
            steps.append(step)
        if not steps:raise ValueError("No recoverable narration")
    if len(steps)==1:warn("partial")
    # Check each independent calculation. Failed checks produce a visible warning,
    # not a false positive or discarded lesson.
    checks=[]
    declared=data.get("checks",[])
    if isinstance(declared,list):
        for check in declared[:8]:
            try:checks.extend(validate_checks([check]))
            except (ValueError,KeyError,TypeError,OverflowError):warn("math")
    for step in steps:
        for text in [step["formula"]]+[o["text"] for o in step["objects"] if o["kind"]=="text"]:
            try:
                value=verify_formula(text)
                if value:checks.append(value)
            except (ValueError,KeyError,TypeError,OverflowError,ZeroDivisionError,RecursionError):warn("math")
    try:checks.extend(verify_subject_labels(steps,question))
    except (ValueError,KeyError,TypeError,OverflowError,ZeroDivisionError):warn("math")
    return steps,checks,warnings
