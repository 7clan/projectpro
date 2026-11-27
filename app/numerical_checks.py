"""Bounded deterministic checks for declared numerical examples.

These checks establish the arithmetic of declared operands only, not the truth
of free-form narration, diagrams or unstated claims.
"""
from fractions import Fraction
import math

def number(value):
    if type(value) not in (int,float) or not math.isfinite(value) or abs(value)>1_000_000:
        raise ValueError("Invalid numerical operand")
    return Fraction(str(value))

def validate_checks(checks):
    if not isinstance(checks,list) or len(checks)>8:raise ValueError("Invalid numerical checks")
    out=[]
    for check in checks:
        if not isinstance(check,dict):raise ValueError("Invalid numerical check")
        op=check.get("op")
        operands=check.get("operands")
        if not isinstance(operands,list) or len(operands)!=2:raise ValueError("Invalid operands")
        a,b=map(number,operands)
        expected=number(check.get("result"))
        if op=="add":actual=a+b
        elif op=="subtract":actual=a-b
        elif op=="multiply":actual=a*b
        elif op=="divide":
            if not b:raise ValueError("Division by zero")
            actual=a/b
        elif op=="pythagoras":
            if a<=0 or b<=0 or expected<=0:raise ValueError("Invalid triangle lengths")
            if abs(float(a*a+b*b-expected*expected))>max(.00001,float(a*a+b*b)*.0001):raise ValueError("Incorrect Pythagorean result")
            actual=expected
        else:raise ValueError("Unsupported numerical operation")
        if abs(float(actual-expected))>max(.00001,abs(float(actual))*.0001):raise ValueError("Incorrect arithmetic")
        out.append({"op":op,"operands":operands,"result":check["result"]})
    return out


def verify_formula(formula):
    """Verify fully numeric equality chains; return None for symbolic or unsupported notation."""
    import ast
    import re
    # Accept a named result and a trailing SI unit, but do not remove units
    # inside the arithmetic: conversions and dimensional algebra are not inferred.
    normalized=formula.strip()
    normalized=re.sub(r"^(?:[a-zA-Z]|R[AB]|[ΣΔ][a-zA-Z])\s*=\s*","",normalized)
    normalized=re.sub(r"\s+(?:m/s[²³23]?|km/h|kg|kN|N|Pa|J|W|V|A|Hz|cm[²³]?|m[²³]?|s)\s*$","",normalized)
    normalized=re.sub(r"(?<=\d),(?=\d)",".",normalized)
    expression=normalized.replace("²","**2").replace("³","**3").replace("×","*").replace("÷","/").replace("−","-").replace("^","**")
    if "=" not in expression or len(expression)>120 or not re.fullmatch(r"[0-9. +*/()=\-]+",expression):
        return None
    def evaluate(node,depth=0):
        if depth>12:raise ValueError("Expression too deep")
        if isinstance(node,ast.Constant):return number(node.value)
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            x=evaluate(node.operand,depth+1)
            return x if isinstance(node.op,ast.UAdd) else -x
        if not isinstance(node,ast.BinOp):raise ValueError("Unsupported expression")
        a=evaluate(node.left,depth+1);b=evaluate(node.right,depth+1)
        if isinstance(node.op,ast.Add):v=a+b
        elif isinstance(node.op,ast.Sub):v=a-b
        elif isinstance(node.op,ast.Mult):v=a*b
        elif isinstance(node.op,ast.Div):
            if not b:raise ValueError("Division by zero")
            v=a/b
        elif isinstance(node.op,ast.Pow):
            if b.denominator!=1 or not 0<=b<=6:raise ValueError("Exponent out of bounds")
            v=a**int(b)
        else:raise ValueError("Unsupported expression")
        if abs(v)>10**12 or v.denominator>10**12:raise ValueError("Expression out of bounds")
        return v
    try:
        values=[evaluate(ast.parse(part.strip(),mode="eval").body) for part in expression.split("=")]
    except SyntaxError:
        return None
    if any(abs(float(a-values[0]))>max(.00001,abs(float(values[0]))*.0001) for a in values[1:]):
        raise ValueError("Incorrect visible numerical equality")
    return {"formula":formula,"scope":"numeric equality only"}


def verify_newton_labels(steps,question):
    """Check explicitly labelled F, m and a in a Newton-II question, in SI only.
    Do not infer relationships from other contexts or mix numbers across scenes.
    """
    import re
    q=question.casefold()
    if "newton" not in q or not any(x in q for x in ("deuxième","seconde","second","2e","2nd","2ème")):
        return []
    output=[]
    for step in steps:
        texts=[step["formula"]]+[o["text"] for o in step["objects"] if o["kind"]=="text"]
        values={}
        patterns={"force":r"\bF\s*=\s*(-?\d+(?:[.,]\d+)?)\s*N\b","mass":r"\bm\s*=\s*(-?\d+(?:[.,]\d+)?)\s*kg\b","acceleration":r"\ba\s*=\s*(-?\d+(?:[.,]\d+)?)\s*m/s(?:²|\^2|2)(?!\w)"}
        for key,pattern in patterns.items():
            matches={number(float(m.replace(",","."))) for t in texts for m in re.findall(pattern,t)}
            if len(matches)==1:values[key]=matches.pop()
        if len(values)==3:
            f,m,a=(values[k] for k in ("force","mass","acceleration"))
            if m<=0 or abs(float(f-m*a))>max(.00001,abs(float(f))*.0001):
                raise ValueError("Newton II labels contradict F = m × a")
            output.append({"scope":"Newton II explicit SI labels","force_N":float(f),"mass_kg":float(m),"acceleration_m_s2":float(a)})
    return output


def verify_subject_labels(steps,question):
    """Cross-check explicit, unambiguous SI labels within a single scene.
    Scope is deliberately limited to the named relationship, not general proof.
    """
    import re
    q=question.casefold()
    specs=[
      (("ohm",), "Ohm's law", {"V":r"\b(?:U|V)\s*=\s*(-?\d+(?:[.,]\d+)?)\s*V\b","R":r"\bR\s*=\s*(-?\d+(?:[.,]\d+)?)\s*(?:Ω|ohms?)\b","I":r"\bI\s*=\s*(-?\d+(?:[.,]\d+)?)\s*A\b"},lambda v:(v["V"],v["R"]*v["I"])),
      (("density","masse volumique"), "Density", {"rho":r"(?:ρ|rho)\s*=\s*(-?\d+(?:[.,]\d+)?)\s*kg/m(?:³|\^3|3)","m":r"\bm\s*=\s*(-?\d+(?:[.,]\d+)?)\s*kg\b","vol":r"\bV\s*=\s*(-?\d+(?:[.,]\d+)?)\s*m(?:³|\^3|3)"},lambda v:(v["m"],v["rho"]*v["vol"])),
      (("kinetic energy","énergie cinétique"), "Kinetic energy", {"E":r"\b(?:Ec|E_k|E)\s*=\s*(-?\d+(?:[.,]\d+)?)\s*J\b","m":r"\bm\s*=\s*(-?\d+(?:[.,]\d+)?)\s*kg\b","v":r"\bv\s*=\s*(-?\d+(?:[.,]\d+)?)\s*m/s(?![\d²³^])"},lambda v:(v["E"],v["m"]*v["v"]**2/2))
    ]
    output=verify_newton_labels(steps,question)
    for keys,scope,patterns,relation in specs:
        if not any(key in q for key in keys):continue
        for step in steps:
            texts=[step["formula"]]+[o["text"] for o in step["objects"] if o["kind"]=="text"]
            values={}
            for key,pattern in patterns.items():
                matches={number(float(m.replace(",","."))) for t in texts for m in re.findall(pattern,t)}
                if len(matches)==1:values[key]=matches.pop()
            if len(values)!=len(patterns):continue
            left,right=relation(values)
            if abs(float(left-right))>max(.00001,abs(float(left))*.0001):raise ValueError(scope+" labels contradict the stated relationship")
            output.append({"scope":scope+" explicit SI labels","values":{k:float(v) for k,v in values.items()}})
    return output
