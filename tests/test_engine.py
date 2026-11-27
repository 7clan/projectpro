import math
import pytest
from app.engine import Beam, explanation_check

@pytest.mark.parametrize('l,p,a,q,ra,rb',[
    (8,12,2,0,9,3),
    (8,12,6,0,3,9),
    (8,12,4,0,6,6),
    (10,0,5,2,10,10),
    (8,12,2,2,17,11),
    (6,6,1.5,1,7.5,4.5),
])
def test_reactions(l,p,a,q,ra,rb):
    b=Beam(l,p,a,q)
    assert b.ra==pytest.approx(ra)
    assert b.rb==pytest.approx(rb)
    assert b.validate_equilibrium()

@pytest.mark.parametrize('l,p,a,q',[(6,8,2,3),(10,14,4,0),(20,80,3,10),(8,12,6,1)])
def test_equilibrium_and_moment_continuity(l,p,a,q):
    b=Beam(l,p,a,q)
    assert b.validate_equilibrium()
    assert b.moment(a-1e-5)==pytest.approx(b.moment(a+1e-5),abs=0.005)
    assert b.moment(0)==pytest.approx(0)
    assert b.moment(l)==pytest.approx(0)
    assert b.max_moment if hasattr(b,'max_moment') else b.moment(b.critical_x())>=0

def test_misconceptions():
    b=Beam(8,12,2,2)
    assert b.check(11,17)['misconception']=='moment_arms_reversed'
    assert b.check(9,3)['misconception']=='forgot_distributed_load'
    assert b.check(0,0)['misconception']=='force_balance'
    assert b.check(b.ra,b.rb)['correct']

def test_reject_bad_inputs():
    for kwargs in ({'length':0},{'position':8},{'load':-1},{'udl':-1},{'load':0,'udl':0}):
        with pytest.raises(ValueError):Beam(**kwargs)

def test_reasoning_check_is_conservative():
    assert explanation_check('Juste parce que oui, cela marche.')['quality']=='revise'
    assert explanation_check("L'équilibre des forces et le moment dépendent de la position de la charge. La distance au support compte.")['quality']=='complete'
