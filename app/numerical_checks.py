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
    expression=formula.replace("²","**2").replace("³","**3").replace("×","*").replace("÷","/").replace("−","-").replace("^","**")
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
    except (SyntaxError,ValueError,ZeroDivisionError,OverflowError):
        return None
    if any(abs(float(a-values[0]))>max(.00001,abs(float(values[0]))*.0001) for a in values[1:]):
        raise ValueError("Incorrect visible numerical equality")
    return {"formula":formula,"scope":"numeric equality only"}
