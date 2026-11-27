"""Exercise actual configured providers, local and cloud, using synthetic course excerpts."""
import asyncio,json,pathlib,time
from app.providers import use_mode,route,provider_status
from app.course_ai import generate
OUT=pathlib.Path("mode-evidence");OUT.mkdir(exist_ok=True)
PAGES=[
 {"document_id":"synthetic-biology","title":"Biology","page":0,"content":"Mitochondria produce ATP through oxidative phosphorylation. ATP provides energy for cellular processes. Photosynthesis converts light energy into chemical energy in chloroplasts."},
 {"document_id":"synthetic-computing","title":"Computer science","page":0,"content":"A queue removes elements in first-in, first-out order. A stack removes elements in last-in, first-out order. Binary search requires sorted data and repeatedly halves the search interval."}
]
async def main():
    status=await provider_status()
    print("PROVIDERS",json.dumps(status),flush=True)
    assert status["providers"]["ollama"]["installed"]
    report={"status":status}
    def validate(raw):
        d=json.loads(raw[raw.index("{"):raw.rindex("}")+1])
        if d.get("answer")!=25:raise ValueError("wrong answer")
        return d
    for selected in ("local","cloud"):
        started=time.monotonic()
        with use_mode(selected,selected=="cloud"):
            result=await route('Return only JSON {"answer":25}. Calculate three squared plus four squared.',validate,budget=100,role="coach")
        report[selected]={"result":result,"seconds":round(time.monotonic()-started,2)}
        print("MODE",selected,report[selected],flush=True)
        assert not result or ((result[1]=="ollama")==(selected=="local"))
        for page in PAGES:
            with use_mode(selected,selected=="cloud"):
                quiz=await generate([page],1,"easy","en")
            report[selected][page["title"]]={"generated":bool(quiz),"metadata":quiz[1] if quiz else None}
            if quiz:
                assert ((quiz[1]["provider"]=="ollama")==(selected=="local"))
                (OUT/(selected+"-"+page["document_id"]+".json")).write_text(json.dumps(quiz,ensure_ascii=False,indent=2))
            print("QUIZ",selected,page["title"],report[selected][page["title"]],flush=True)
    (OUT/"results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    assert report["local"]["result"],"Local inference unavailable"
    assert report["cloud"]["result"],"All cloud text providers unavailable"
    assert all(any(report[selected][p["title"]]["generated"] for selected in ("local","cloud")) for p in PAGES),"One subject did not produce an acceptable quiz"
asyncio.run(main())
