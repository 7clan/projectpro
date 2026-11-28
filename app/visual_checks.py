"""Reusable checks on rendered scene objects, not on the model's self-reported score.

These constraints establish specific geometric and numerical properties only.
They cannot establish the general scientific correctness of arbitrary narration.
"""
import math
import re

ID = re.compile(r"[a-z][a-z0-9_]{0,39}\Z")
DEC = r"(\d+(?:[.,]\d+)?)"

def close(actual, expected, tolerance=.02):
    return math.isclose(actual, expected, rel_tol=tolerance, abs_tol=1e-7)

def object_map(step):
    out={}
    for obj in step["objects"]:
        if "id" not in obj:
            continue
        name=obj["id"]
        if name in out:
            raise ValueError("Duplicate visual object ID")
        out[name]=obj
    return out

def lookup(objects, name, kind=None):
    if not isinstance(name,str) or name not in objects:
        raise ValueError("Missing visual object")
    obj=objects[name]
    if kind and obj["kind"]!=kind:
        raise ValueError("Wrong visual object type")
    return obj

def direction(obj, expected, motion=False):
    if expected not in ("up","down","left","right"):
        raise ValueError("Unsupported direction")
    if motion:
        if obj["motion"]!="move":raise ValueError("Missing physical movement")
        dx,dy=obj["dx"],obj["dy"]
    else:
        if obj["kind"]!="arrow":raise ValueError("Expected vector arrow")
        dx,dy=obj["x2"]-obj["x"],obj["y2"]-obj["y"]
    along,across={"up":(-dy,dx),"down":(dy,dx),"left":(-dx,dy),"right":(dx,dy)}[expected]
    if along<1 or abs(across)>along*.2:
        raise ValueError("Incorrect vector or motion direction")

def width_ratio(a,b,ratio):
    if a["kind"]!="rect" or b["kind"]!="rect" or not close(b["w"]/a["w"],ratio,.15):
        raise ValueError("Incorrect relative width")

def motion_ratio(a,b,ratio):
    if any(o["motion"]!="move" for o in (a,b)):
        raise ValueError("Missing linked movement")
    da,db=[math.hypot(o["dx"],o["dy"]) for o in (a,b)]
    if min(da,db)<.2 or not close(da/db,ratio,.15):
        raise ValueError("Incorrect displacement ratio")

def label_value(obj,symbol,expected,units,tolerance=.002):
    if obj["kind"]!="text":raise ValueError("Missing numeric label")
    match=re.fullmatch(re.escape(symbol)+r"\s*=\s*"+DEC+r"\s*(.+)",obj["text"].strip())
    if not match or match[2] not in units or not close(float(match[1].replace(",","."))*units[match[2]],expected,tolerance):
        raise ValueError("Incorrect or missing label: "+symbol)

def validate_declared(steps,rules):
    """Check optional model-declared relations against actual rendered geometry."""
    if not isinstance(rules,list) or len(rules)>20:
        raise ValueError("Invalid visual checks")
    result=[]
    for rule in rules:
        if not isinstance(rule,dict):raise ValueError("Invalid visual rule")
        i=rule.get("scene")
        if type(i)!=int or not 0<=i<len(steps):raise ValueError("Invalid visual scene reference")
        objs=object_map(steps[i])
        a=lookup(objs,rule.get("a"))
        op=rule.get("op")
        if op in ("direction","motion_direction"):
            direction(a,rule.get("direction"),op=="motion_direction")
        elif op in ("width_ratio","motion_ratio"):
            ratio=rule.get("ratio")
            if type(ratio) not in (int,float) or not math.isfinite(ratio) or not .01<=ratio<=100:
                raise ValueError("Invalid visual ratio")
            b=lookup(objs,rule.get("b"))
            if a is b:raise ValueError("Self-referential visual ratio")
            (width_ratio if op=="width_ratio" else motion_ratio)(a,b,ratio)
        else:raise ValueError("Unsupported visual relation")
        result.append({"scope":"declared visual relationship only","scene":i,"operation":op})
    return result

def hydraulic_inputs(question):
    """Narrow profile for an explicitly specified two-piston input/output example.
    Do not infer parameters when the question is ambiguous.
    """
    q=question.casefold()
    if not any(word in q for word in ("hydraulic press","hydraulic pistons","presse hydraulique","pascal's principle","principe de pascal")):
        return None
    forces=re.findall(DEC+r"\s*n\b",q)
    areas=re.findall(DEC+r"\s*cm(?:²|\^2|2)(?!\w)",q)
    if len(forces)!=1 or len(areas)!=2:return None
    f,a,b=[float(v.replace(",",".")) for v in forces+areas]
    if not (0<f<=10000 and 0<a<b<=10000 and 1.5<=b/a<=40):return None
    return f,a,b

def hydraulic_prompt(values):
    f,a,b=values
    ratio=b/a
    p=f/(a*1e-4)
    fmt=lambda x:format(x,".8g")
    return (
      "For this explicit ideal hydraulic example, draw FOUR different stages: setup, pressure calculation, output-force calculation, and movement/volume conservation. "
      "Draw two circular-cross-section pistons as horizontal rectangle plates (width proportional to diameter, not to area), touching a shared fluid chamber. "
      "In the FINAL scene use id on compact objects: input_piston and output_piston (rect); input_force and output_force (arrow); fluid (rect or polygon); "
      "f1,a1,a2,f2,pressure,d1,d2 (text). Put force arrows vertically near the piston centers: input arrow down, output up. "
      f"Plate width ratio output/input = {fmt(math.sqrt(ratio))}. Exact visible text values: "
      f"F1 = {fmt(f)} N; A1 = {fmt(a)} cm²; A2 = {fmt(b)} cm²; F2 = {fmt(f*ratio)} N; P = {fmt(p)} Pa. "
      f"For motion choose e.g. d1 = {fmt(ratio)} cm and d2 = 1 cm; final labels d1 and d2 must give positive distances in cm with ratio {fmt(ratio)}. "
      "In final scene both plates must move vertically from their start positions, using m:move and a:[0,dy]: input downward, output upward, same scale, with input/output travel ratio equal to area ratio. "
      "Keep both plates and arrows visible, no overlap of labels, leave space for movement. "
      f"Use formula P = {fmt(f)} / {fmt(a*1e-4)} = {fmt(p)} Pa in pressure stage and F2 = {fmt(f)} × ({fmt(b)}/{fmt(a)}) = {fmt(f*ratio)} N in output stage. "
      "Mention equal pressure at equal elevations, ideal incompressible fluid, force-distance tradeoff and conservation of displaced volume. No free energy claim. "
      "Use conventional symbols exactly for the specified text labels in either language. Narration and titles must be in requested language."
    )

def check_hydraulic(steps,values):
    f,a,b=values
    ratio=b/a
    p=f/(a*1e-4)
    if len(steps)<4:raise ValueError("Missing hydraulic explanation stages")
    final=object_map(steps[-1])
    x=lookup(final,"input_piston","rect");y=lookup(final,"output_piston","rect")
    if any(o["w"]<=o["h"] for o in (x,y)):raise ValueError("Pistons must be horizontal plates")
    if x["x"]+x["w"]>=y["x"]:raise ValueError("Pistons overlap")
    width_ratio(x,y,math.sqrt(ratio))
    for role,piston,way in (("input_force",x,"down"),("output_force",y,"up")):
        arrow=lookup(final,role,"arrow")
        direction(arrow,way)
        if abs((arrow["x"]+arrow["x2"])/2-(piston["x"]+piston["w"]/2))>piston["w"]/2+10:
            raise ValueError("Force not aligned with piston")
        if min(abs(arrow[k]-piston["y"]) for k in ("y","y2"))>35:
            raise ValueError("Force arrow disconnected from piston")
    fluid=lookup(final,"fluid")
    if fluid["kind"] not in ("rect","polygon"):raise ValueError("Missing common fluid chamber")
    from .whiteboard import bounds
    l,t,r,bot=bounds(fluid)
    for piston in (x,y):
        if not l<=piston["x"]+piston["w"]/2<=r or not t-12<=piston["y"]+piston["h"]<=bot:
            raise ValueError("Piston not connected to fluid")
    for name,sym,val,units in (
       ("f1","F1",f,{"N":1}),("a1","A1",a,{"cm²":1,"cm^2":1,"cm2":1}),
       ("a2","A2",b,{"cm²":1,"cm^2":1,"cm2":1}),("f2","F2",f*ratio,{"N":1}),
       ("pressure","P",p,{"Pa":1,"kPa":1000})):
        label_value(lookup(final,name),sym,val,units)
    distances=[]
    for name in ("d1","d2"):
        obj=lookup(final,name,"text")
        m=re.fullmatch(name+r"\s*=\s*"+DEC+r"\s*cm",obj["text"])
        if not m or float(m[1].replace(",","."))<=0:raise ValueError("Missing displacement distance")
        distances.append(float(m[1].replace(",",".")))
    if not close(distances[0]/distances[1],ratio):raise ValueError("Displaced volume not conserved")
    direction(x,"down",True);direction(y,"up",True);motion_ratio(x,y,ratio)
    if not close(x["at"],y["at"],.02) or not close(x["duration"],y["duration"],.02):
        raise ValueError("Pistons must move together")
    # Require the actual pressure and output-force calculations, not just a number in the final graphic.
    numeric=lambda s:float(s.replace(",","."))
    press=force=False
    for step in steps:
        e=step["formula"].replace(" ","")
        m=re.fullmatch(r"P="+DEC+r"[/÷]"+DEC+r"="+DEC+r"Pa",e)
        if m and all(close(numeric(v),z,.002) for v,z in zip(m.groups(),(f,a*1e-4,p))):press=True
        m=re.fullmatch(r"F2="+DEC+r"[×*]\("+DEC+r"[/÷]"+DEC+r"\)="+DEC+r"N",e)
        if m and all(close(numeric(v),z,.002) for v,z in zip(m.groups(),(f,b,a,f*ratio))):force=True
    if not press or not force:raise ValueError("Missing pressure or output force calculation")
    return [{"scope":"ideal hydraulic diagram: force directions, diameter ratio, pressure and volume conservation","pressure_Pa":p,"output_N":f*ratio,"area_ratio":ratio}]

def validate_teaching(steps,raw,question):
    if not 3<=len(steps)<=5:raise ValueError("Need at least three teaching stages")
    for step in steps:
        if sum(o["kind"]!="text" for o in step["objects"])<2:
            raise ValueError("Insufficient graphical explanation")
        object_map(step)
    for key in ("title","narration"):
        if len({s[key].casefold().strip() for s in steps})!=len(steps):
            raise ValueError("Repeated teaching stages")
    import json
    data=json.loads(raw[raw.find("{"):raw.rfind("}")+1])
    checks=validate_declared(steps,data.get("visual_checks",[]))
    values=hydraulic_inputs(question)
    if values:checks.extend(check_hydraulic(steps,values))
    return checks
