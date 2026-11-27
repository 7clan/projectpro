"""Validated conceptual statics questions with adaptive concept selection.
Unlike recall quizzes, these ask learners to apply a physical principle.
"""
import random
import secrets
from .engine import Beam

def conceptual_questions(count=6,difficulty="adaptive",weak=None,lang="fr"):
    rng=random.SystemRandom()
    weak=weak or {}
    concepts=["force_balance","moment_equilibrium","support_reactions","load_transfer"]
    concepts.sort(key=lambda c:weak.get(c,0))
    out=[]
    for i in range(count):
        c=concepts[i%4]
        level=("easy" if weak.get(c,0)<50 else "hard") if difficulty=="adaptive" else difficulty
        L=rng.choice([6,8,10,12]);P=rng.choice([8,12,16,20]);a=L*rng.choice([.25,.75]);q=rng.choice([2,4]) if level=="hard" else 0
        b=Beam(L,P,a,q)
        def tr(fr,en):return fr if lang=="fr" else en
        prefix=tr(f"Poutre simplement appuyée : L={L} m, P={P} kN à {a:g} m de A, q={q} kN/m. ",f"Simply supported beam: L={L} m, P={P} kN at {a:g} m from A, q={q} kN/m. ")
        if c=="force_balance":
            prompt=prefix+tr("Quelle est la somme RA + RB ?","What is RA + RB?")
            correct=b.total_load;wrong=[P if q else P/2,b.total_load+L,b.total_load*2]
            explanation=tr("La somme des réactions égale P + qL.","The reactions sum to P + qL.")
        elif c=="moment_equilibrium":
            prompt=prefix+tr("Quel est le moment du chargement autour de A (kN·m, valeur absolue) ?","What is the absolute load moment about A (kN·m)?")
            correct=P*a+q*L*L/2;wrong=[P*(L-a),P*L+q*L*L/2,correct+L]
            explanation=tr("Le bras de levier de P est a ; celui de qL est L/2.","The lever arm of P is a; the lever arm of qL is L/2.")
        elif c=="support_reactions":
            prompt=prefix+tr("Quelle est la réaction RB ?","What is reaction RB?")
            correct=b.rb;wrong=[b.ra,b.total_load/2,b.total_load]
            explanation=tr("RB = (P × a + q × L² / 2) / L.","RB = (P × a + q × L² / 2) / L.")
        else:
            prompt=prefix+tr("Si P se rapproche de B sans changer sa valeur, que devient RB ?","If P moves toward B without changing magnitude, what happens to RB?")
            answer=tr("Elle augmente","It increases");options=[answer,tr("Elle diminue","It decreases"),tr("Elle ne change pas","It does not change"),tr("Elle devient nulle","It becomes zero")]
            explanation=tr("Le moment de P autour de A augmente ; RB augmente.","The moment of P about A increases, so RB increases.")
        if c!="load_transfer":
            vals=[correct]+wrong
            distinct=list(dict.fromkeys(round(v,4) for v in vals))
            while len(distinct)<4:
                v=round(correct+len(distinct)+1,4)
                if v not in distinct:distinct.append(v)
                else:distinct.append(max(distinct)+1)
            unit="kN·m" if c=="moment_equilibrium" else "kN"
            options=[f"{v:g} {unit}" for v in distinct[:4]]
            answer=options[0]
        rng.shuffle(options)
        out.append({"id":secrets.token_hex(8),"prompt":prompt,"answer":answer,"options":options,"excerpt":explanation,"title":"RDM2 · deterministic statics","page":None,"document_id":None,"concept":c,"difficulty":level})
    return out
