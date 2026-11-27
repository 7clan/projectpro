import asyncio
import json
import pytest
from app import studio_context,whiteboard,providers
from test_api import client,auth

def test_exact_reported_conversation_no_stale_triangle(client,auth,monkeypatch):
    monkeypatch.setenv("DECLIC_LOCAL_ONLY","1")
    monkeypatch.delenv("DECLIC_OLLAMA_MODEL",raising=False)
    history=[]
    for i,q in enumerate(["pythagore?","whats the latest update on gold worth?","whats the latest update on gold worth in us dollars?","could you explain more ? do you have current price of gold in us dollars?","could you explain more ? do you have current price of gold in us dollars?","im only talking about gold and not math"]):
        response=client.post("/api/studio",headers=auth,json={"question":q,"history":history[-8:],"lang":"en","generative":True,"ai_mode":"local"})
        assert response.status_code==200,response.text
        result=response.json()
        if i==0:
            assert result["steps"][0]["scene"]=="generated"
            assert result["numerical_checks"]
        else:
            assert result["visual_mode"]=="information",result
            assert result["sources"]==[]
            assert "live data feed" in result["steps"][0]["narration"]
            assert "triangle" not in json.dumps(result).lower()
        # Deliberately reproduce prior wrong tutor output in supplied history.
        history.extend([{"role":"student","text":q},{"role":"tutor","text":"Right triangles satisfy the Pythagorean theorem."}])

def test_topic_switch_and_followups():
    h=[{"role":"student","text":"Explain Pythagoras"},{"role":"tutor","text":"Triangles and squares."}]
    assert studio_context.resolve_turn("Explain gold as an investment",h)==("Explain gold as an investment",[])
    h.extend([{"role":"student","text":"Explain photosynthesis"},{"role":"tutor","text":"Wrong answer about triangles"}])
    q,ctx=studio_context.resolve_turn("Could you explain more?",h)
    assert "photosynthesis" in q and "triangle" not in str(ctx)
    assert len(ctx)==1 and ctx[0]["role"]=="student"
    q,ctx=studio_context.resolve_turn("Can you explain how this theorem is used in real life?",h[:2])
    assert "Pythagoras" in q
    assert not studio_context.needs_fresh_data("Explain electrical current and Ohm's law")
    assert studio_context.needs_fresh_data("Quel est le prix actuel de l'or ?")
    assert studio_context.needs_fresh_data("What is today's weather?")
    assert not studio_context.needs_fresh_data("Explain why gold prices fluctuate")

def test_unrelated_prompt_does_not_prime_triangle_example(monkeypatch):
    seen=[]
    async def fake_route(prompt,validator,*args,**kwargs):
        seen.append(prompt)
        return None
    monkeypatch.setattr(providers,"route",fake_route)
    with providers.use_mode("cloud",True):
        asyncio.run(whiteboard.generate("Explain photosynthesis","en",[],[]))
    assert seen and "For a Pythagorean area diagram" not in seen[0]
    assert "latest user request is the only task" in seen[0]

def test_local_unrelated_scene_cannot_be_triangle():
    from app.local_board import compile_plan,schema_for
    scene={"title":"Triangle","speech":"Observe the triangle.","formula":"—","diagram":"triangle","a":3,"b":4,"label1":"a","label2":"b","label3":"c"}
    with pytest.raises(ValueError):
        compile_plan(json.dumps({"scenes":[scene,scene]}),"Explain gold","en")
    assert schema_for("Explain gold")["properties"]["scenes"]["items"]["properties"]["diagram"]["enum"]==["flow"]

def test_auth_form_cannot_default_to_get(client):
    from html.parser import HTMLParser
    class Parser(HTMLParser):
        def __init__(self):super().__init__();self.form=None;self.submit=None
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if attrs.get("id")=="auth-form":self.form=attrs
            if attrs.get("id")=="auth-submit":self.submit=attrs
    p=Parser();p.feed(client.get("/").text)
    assert p.form["method"]=="post"
    assert "disabled" in p.submit
