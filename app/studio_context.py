"""Conservative Studio turn routing. No live market/news tools are installed.

Only context-dependent follow-ups inherit prior user questions. Model answers
are never used as topic anchors: a wrong answer must not poison later turns.
"""
import re

def _plain(text):
    return " ".join(text.casefold().replace("’","'").split()).strip(" ?!.,")

def is_followup(question):
    q=_plain(question)
    return bool(re.fullmatch(r"(?:please )?(?:(?:could|can|would) you )?(?:explain(?: (?:it|that|this))? (?:more|further|again|in more detail)|tell me more|elaborate(?: on (?:that|this|it))?|continue|go on|why|how|what about (?:it|that)|how (?:is|can|do) (?:it|this|that|we|you) (?:be )?used(?: in real life)?|give (?:me )?(?:an|another) example|explique(?: encore| davantage| plus| mieux)|peux-tu expliquer(?: davantage| plus| mieux)|pourquoi|comment|continue|donne(?:-moi)? un exemple)",q))

def resolve_turn(question,history):
    """Return effective question and context; standalone requests are independent."""
    if not is_followup(question):
        return question,[]
    anchor=next((t.get("text","") for t in reversed(history) if t.get("role")=="student" and t.get("text") and not is_followup(t["text"])),None)
    if not anchor:return question,[]
    return question+"\nTopic of this follow-up: "+anchor,[{"role":"student","text":anchor}]

def needs_fresh_data(question):
    q=_plain(question)
    # Price/current-events/weather requests, not electrical current or a
    # historical question about the latest stage of a mathematical proof.
    time=r"(?:latest|current|live|real[- ]time|today(?:'s)?|right now|as of now|this (?:week|month)|maintenant|actuel(?:le|s|les)?|aujourd'hui|derni[eè]r(?:e|es|s)?|en direct|temps r[eé]el)"
    dynamic=r"(?:price|prices|worth|market|stock|exchange rate|news|weather|forecast|score|results|update|prix|cours|m[eé]t[eé]o|actualit[eé]s|r[eé]sultats|taux de change)"
    return bool(re.search(r"\b"+time+r"\b.{0,100}\b"+dynamic+r"\b|\b"+dynamic+r"\b.{0,100}\b"+time+r"\b",q) or re.search(r"\b(?:how much|what is|what's|combien)\b.{0,80}\b(?:gold|silver|bitcoin|btc|or|argent)\b.{0,40}\b(?:worth|cost|price|vaut|co[uû]te)\b",q))

def unavailable_fresh(lang):
    fr=lang=="fr"
    return {"mode":"guided_offline","visual_mode":"information","sources":[],"steps":[{"scene":"information","title":"Données actuelles non vérifiées" if fr else "Live information unavailable","formula":"—","narration":"Je n’ai pas accès à un flux de données en temps réel pour vérifier cette information. Je peux expliquer le sujet ou analyser une source datée que tu fournis." if fr else "I do not have a live data feed to verify that information. I can explain the subject or help you interpret a dated source you provide."}],"notice":"Pas de données en temps réel · aucune valeur inventée" if fr else "No live data feed · no invented current value"}

def short_pythagoras(question,lang,sources):
    q=_plain(question)
    if not re.fullmatch(r"(?:(?:explain|explique) )?(?:(?:the|le) )?(?:pythagor(?:e|as|ean theorem)|th[eé]or[eè]me de pythagore)",q):return None
    import json
    from .local_board import compile_plan
    scene={"title":"Triangle","speech":"Observe the triangle.","formula":"—","diagram":"triangle","a":3,"b":4,"label1":"a","label2":"b","label3":"c"}
    steps,checks=compile_plan(json.dumps({"scenes":[scene,scene]}),"Pythagoras",lang)
    return {"mode":"guided_offline","visual_mode":"predefined","steps":steps,"numerical_checks":checks,"sources":sources,"notice":"Exemple local vérifié · côtés 3 et 4" if lang=="fr" else "Checked local example · sides 3 and 4"}
