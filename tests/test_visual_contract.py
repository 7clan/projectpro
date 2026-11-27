import asyncio
import copy
import json
import math
import pytest
from app.visual_checks import validate_teaching,check_hydraulic,validate_declared,hydraulic_inputs
from app.whiteboard import validate_lesson
from app import voice

QUESTION="Explain how a hydraulic press works. An input force of 50 N applied to a piston of 5 cm² produces an output force on a piston of 100 cm²."

def fixture():
    def rect(id,x,y,w,h,**kw):return {"id":id,"k":"rect","p":[x,y,w,h],**kw}
    def arrow(id,x,y,x2,y2):return {"id":id,"k":"arrow","p":[x,y,x2,y2]}
    def text(id,x,y,v):return {"id":id,"k":"text","p":[x,y,15],"v":v}
    objects=[
      rect("fluid",70,170,460,135,f=.2),
      rect("input_piston",110,160,30,10,m="move",a=[0,60],t=.4,d=2),
      rect("output_piston",365,160,30*math.sqrt(20),10,m="move",a=[0,-3],t=.4,d=2),
      arrow("input_force",125,100,125,155),arrow("output_force",432,155,432,90),
      text("f1",125,65,"F1 = 50 N"),text("a1",125,245,"A1 = 5 cm²"),
      text("a2",432,245,"A2 = 100 cm²"),text("f2",432,65,"F2 = 1000 N"),
      text("pressure",300,205,"P = 100000 Pa"),text("d1",125,280,"d1 = 20 cm"),
      text("d2",432,280,"d2 = 1 cm")]
    formulas=["P = F / A","P = 50 / 0.0005 = 100000 Pa","F2 = 50 × (100/5) = 1000 N","A1 × d1 = A2 × d2"]
    return {"s":[{"h":h,"n":n,"e":e,"o":copy.deepcopy(objects)} for h,n,e in zip(
      ["Setup","Pressure","Force","Displacement"],
      ["Observe the connected fluid.","Convert the area to square meters.","Calculate the amplified force.","Equal volumes move as both pistons travel."],formulas)]}

def check(data):
    raw=json.dumps(data,ensure_ascii=False)
    steps,_=validate_lesson(raw)
    return validate_teaching(steps,raw,QUESTION)

def test_hydraulic_contract_validates_rendered_objects():
    assert hydraulic_inputs(QUESTION)==(50,5,100)
    assert check(fixture())[-1]["output_N"]==1000

@pytest.mark.parametrize("fault",["down","equal_width","wrong_pressure","missing_area","motion","distance","missing_calculation","two_stages","wrong_force","unlinked"])
def test_hydraulic_rejects_semantic_errors(fault):
    data=fixture()
    objs={o["id"]:o for o in data["s"][-1]["o"]}
    if fault=="down":objs["output_force"]["p"]=[432,90,432,155]
    elif fault=="equal_width":objs["output_piston"]["p"][2]=30
    elif fault=="wrong_pressure":objs["pressure"]["v"]="P = 100 Pa"
    elif fault=="missing_area":data["s"][-1]["o"].remove(objs["a2"])
    elif fault=="motion":objs["output_piston"]["a"]=[0,-30]
    elif fault=="distance":objs["d2"]["v"]="d2 = 10 cm"
    elif fault=="missing_calculation":data["s"][1]["e"]="P = F / A"
    elif fault=="two_stages":data["s"]=data["s"][:2]
    elif fault=="wrong_force":objs["f2"]["v"]="F2 = 100 N"
    elif fault=="unlinked":objs["output_piston"]["t"]=.7
    with pytest.raises(ValueError):check(data)

def test_generic_visual_checks_reference_real_objects():
    raw=json.dumps(fixture())
    steps,_=validate_lesson(raw)
    valid=[{"scene":3,"op":"direction","a":"output_force","direction":"up"},
           {"scene":3,"op":"width_ratio","a":"input_piston","b":"output_piston","ratio":math.sqrt(20)}]
    assert len(validate_declared(steps,valid))==2
    valid[0]["direction"]="down"
    with pytest.raises(ValueError):validate_declared(steps,valid)
    valid[0]["a"]="nonexistent"
    with pytest.raises(ValueError):validate_declared(steps,valid)

def test_fish_voice_only_after_cloud_failures_and_consent(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY","dummy")
    monkeypatch.delenv("DECLIC_LOCAL_ONLY",raising=False)
    for name in ("_cloud_retry_at","_router_voice_retry_at","_fish_voice_retry_at"):
        monkeypatch.setattr(voice,name,0)
    calls=[]
    async def limited(*a):raise voice.CloudRateLimited(60)
    async def fish(*a):
        calls.append("fish")
        return b"audio",[]
    monkeypatch.setattr(voice,"_gemini_render",limited)
    monkeypatch.setattr(voice,"_openrouter_render",limited)
    monkeypatch.setattr(voice,"_fish_render",fish)
    monkeypatch.setattr(voice,"_neural_render",lambda *a:(b"local",[]))
    assert asyncio.run(voice.synthesize_preferred("Hello","en",[0],cloud=False))[2]=="piper-neural"
    assert not calls
    assert asyncio.run(voice.synthesize_preferred("Hello","en",[0],cloud=True))[2]=="openrouter-fish-neural"
    assert calls==["fish"]
