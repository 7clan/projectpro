import json
import pytest
from app.whiteboard import validate_board

def board():
    return {"steps":[{"title":"A","formula":"—","narration":"Observe this example.","objects":[{"kind":"arrow","x":30,"y":30,"x2":200,"y2":90,"motion":"move","dx":20,"dy":0,"at":0.2},{"kind":"text","x":300,"y":100,"text":"A","size":20}]} for _ in range(2)]}

def test_generated_board_valid():
    result=validate_board(json.dumps(board()))
    assert result[0]["scene"]=="generated"
    assert result[0]["objects"][0]["dx"]==20

@pytest.mark.parametrize("patch",[{"kind":"script"},{"x":1000},{"at":1.5},{"color":"url(evil)"},{"dx":999},{"y":float("nan")}])
def test_reject_unsafe_commands(patch):
    data=board()
    data["steps"][0]["objects"][0].update(patch)
    with pytest.raises(ValueError):
        validate_board(json.dumps(data))

def test_ignores_untrusted_fields():
    data=board()
    data["steps"][0]["objects"][0]["onclick"]="alert(1)"
    assert "onclick" not in validate_board(json.dumps(data))[0]["objects"][0]


def test_compact_format_expands_safe_geometry():
    from app.whiteboard import validate_compact
    d={"s":[{"h":"Triangle","e":"a²+b²=c²","n":"Observe the triangle.","o":[{"k":"polygon","p":[[40,40],[40,120],[100,120]],"c":"blue","m":"grow","f":0.2},{"k":"text","p":[90,150,18],"v":"c"}]} for _ in range(2)]}
    steps=validate_compact(json.dumps(d))
    assert steps[0]["objects"][0]["points"]==[[40,40],[40,120],[100,120]]
    d["s"][0]["o"][0]["k"]="script"
    with pytest.raises(ValueError): validate_compact(json.dumps(d))
