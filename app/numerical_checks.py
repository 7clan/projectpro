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
