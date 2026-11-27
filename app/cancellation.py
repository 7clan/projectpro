"""Cancel in-flight async work when the browser disconnects."""
import asyncio
from fastapi import HTTPException

async def until_disconnect(request, work):
    async def watch():
        while not await request.is_disconnected():
            await asyncio.sleep(.15)
    task=asyncio.create_task(work)
    watcher=asyncio.create_task(watch())
    try:
        done,_=await asyncio.wait((task,watcher),return_when=asyncio.FIRST_COMPLETED)
        if task in done:return await task
        # Propagate watcher errors rather than treating them as disconnects.
        await watcher
        raise HTTPException(499,"Client disconnected")
    finally:
        for t in (task,watcher):
            if not t.done():t.cancel()
        await asyncio.gather(task,watcher,return_exceptions=True)
