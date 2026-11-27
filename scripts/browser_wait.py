"""Poll through Playwright's DevTools evaluation, not in-page eval.
Do not disable CSP in the browser context.
"""
import time
def wait_for(page,expression,arg=None,timeout=30000):
    deadline=time.monotonic()+timeout/1000
    while time.monotonic()<deadline:
        if page.evaluate(expression,arg):return
        page.wait_for_timeout(100)
    raise AssertionError("Timed out waiting for browser condition: "+expression[:180])
