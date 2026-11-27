import asyncio
import io
import shutil
import wave
import pytest
from app.voice import split_cues, synthesize
from app.reviewer import validate_review

def test_cue_positions_are_aligned_and_all_preserved():
    text="La force agit verticalement. Puis le moment change lorsque la distance augmente."
    cues=[0,.1,.24,.43,.7,.9]
    chunks=split_cues(text,cues)
    assert ' '.join(c for c,_ in chunks)==text
    assert sorted({v for _,positions in chunks for v in positions})==cues
    assert all(c for c,_ in chunks)

def test_dense_cues_remain_bounded():
    text=" ".join(["example"]*60)
    cues=[i*.025 for i in range(32)]
    chunks=split_cues(text,cues)
    assert len(chunks)<=17
    assert sorted({v for _,positions in chunks for v in positions})==cues

@pytest.mark.skipif(not(shutil.which("espeak") or shutil.which("espeak-ng")),reason="local speech engine not installed")
def test_audio_contains_real_frames_and_precise_cues():
    raw,marks=asyncio.run(synthesize("Bonjour. Observe le triangle.", "fr", [0,.45,.8]))
    with wave.open(io.BytesIO(raw),"rb") as w:
        assert w.getnframes()>0
        duration=w.getnframes()/w.getframerate()
        assert any(w.readframes(w.getnframes()))
    assert marks[0]["time"]==0
    assert all(0<=m["time"]<duration for m in marks)
    assert len({m["time"] for m in marks})>=2

def test_review_cannot_claim_pass_with_issues():
    with pytest.raises(ValueError):
        validate_review('{"verdict":"pass","issues":["incorrect equation"]}')
    assert validate_review('{"verdict":"revise","issues":["incorrect equation"]}')["verdict"]=="revise"
