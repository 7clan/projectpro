import asyncio
import json
import pytest
from app.lesson_recovery import recover_lesson
from app.whiteboard import validate_board

def scene():
    return {"h":"Pressure","n":"Pressure acts on the fluid.","e":"50 / 5 = 10","o":[
        {"k":"rect","p":[80,120,400,100]},
        {"k":"arrow","p":[120,40,120,110]},
        {"k":"text","p":[200,180,44],"v":"Pressure"}]}

def recover(data):
    return recover_lesson(json.dumps(data),"Hydraulic press","en")

def test_font_size_is_repaired_without_rejecting_scene():
    steps,checks,warnings=recover({"s":[scene(),scene()]})
    assert len(steps)==2 and len(steps[0]["objects"])==3
    assert steps[0]["objects"][2]["size"]==32
    assert "Layout adapted" in warnings

def test_missing_font_size_and_excess_coordinate():
    s=scene()
    s["o"][2]["p"]=[200,180]
    s["o"][1]["p"].append(99)
    steps,_,warnings=recover({"s":[s,s]})
    assert len(steps[0]["objects"])==3
    assert steps[0]["objects"][2]["size"]==18
    assert warnings

def test_invalid_shape_does_not_discard_narration():
    s=scene();s["o"][0]["p"]=[10,20];s["o"].append({"k":"script","p":[0,0]})
    steps,_,warnings=recover({"s":[s,s]})
    assert steps[0]["narration"]==s["n"]
    assert {o["kind"] for o in steps[0]["objects"]}=={"arrow","text"}
    assert "Incomplete graphic elements omitted" in warnings

def test_math_disagreement_is_advisory():
    s=scene();s["e"]="50 / 5 = 100"
    steps,checks,warnings=recover({"s":[s,s],"checks":[{"op":"divide","operands":[50,5],"result":100}]})
    assert steps[0]["formula"]==s["e"] and not checks
    assert "Calculation needs review" in warnings

def test_partial_json_preserves_complete_scene():
    raw='{"s":['+json.dumps(scene())+',{"h":"Next","n":'
    steps,_,warnings=recover_lesson(raw,"Hydraulics","en")
    assert len(steps)==1 and steps[0]["narration"]==scene()["n"]
    assert "Partial AI response" in warnings

def test_unrenderable_scene_preserves_speech():
    s=scene();s["o"]=[{"k":"rect","p":[10]}]
    steps,_,warnings=recover({"s":[s]})
    assert steps[0]["narration"]==s["n"]
    assert all(o["kind"]=="text" for o in steps[0]["objects"])
    assert any("Diagram unavailable" in w for w in warnings)

def test_plain_explanation_is_not_lost():
    steps,_,warnings=recover_lesson("Pressure is transmitted through a confined fluid.","Hydraulics","en")
    assert steps[0]["narration"].startswith("Pressure")
    assert warnings

def test_strict_renderer_remains_strict():
    with pytest.raises(ValueError):
        validate_board(json.dumps({"steps":[{"title":"x","formula":"—","narration":"x","objects":[{"kind":"script"}]}]}),min_steps=1)

def test_live_generation_uses_recovery_not_strict_rejection(monkeypatch):
    from app import providers,whiteboard
    s=scene();s["e"]="50 / 5 = 100"
    async def fake_route(prompt,validator,budget=3000,**kwargs):
        return validator(json.dumps({"s":[s,s]})),"bazaarlink","fake"
    monkeypatch.delenv("DECLIC_LOCAL_ONLY",raising=False)
    monkeypatch.setattr(providers,"route",fake_route)
    with providers.use_mode("cloud",True):
        lesson=asyncio.run(whiteboard.generate("Explain pressure","en",[],[]))
    assert lesson["mode"]=="live_ai"
    assert "Calculation needs review" in lesson["quality_warnings"]


def test_any_nonempty_unrecognized_response_is_preserved():
    from app.lesson_recovery import recover_any_lesson
    steps,checks,warnings=recover_any_lesson('{"unexpected":"An answer"}',"Pressure","en")
    assert steps[0]["narration"]=='{"unexpected":"An answer"}'
    assert not checks and warnings

def test_semantic_invalid_plan_preserves_model_speech():
    from app.lesson_recovery import recover_any_lesson
    steps,checks,warnings=recover_any_lesson(json.dumps({"scenes":[{"title":"Explanation","speech":"The force is transmitted through the fluid."}]}),"Hydraulics","en",semantic=True)
    assert steps[0]["narration"]=="The force is transmitted through the fluid."
    assert warnings

def test_any_empty_response_still_triggers_provider_fallback():
    from app.lesson_recovery import recover_any_lesson
    with pytest.raises(ValueError):recover_any_lesson("  ","Pressure","en")
