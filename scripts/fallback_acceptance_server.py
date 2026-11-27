"""Test-only server: cloud rejection is simulated; actual local synthesis is untouched."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ["OPENROUTER_API_KEY"]="fixture-never-sent"
os.environ["DECLIC_LOCAL_ONLY"]="0"
from app import voice
async def fail(*args):
    raise voice.CloudRateLimited(60)
voice._openrouter_render=fail
voice._gemini_render=fail
from app.main import app
import uvicorn
uvicorn.run(app,host="127.0.0.1",port=8000)
