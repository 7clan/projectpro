"""Private-pilot HTTP hardening. Not a substitute for an authenticated reverse proxy."""
from collections import OrderedDict
import hashlib
import os
import time
from starlette.responses import JSONResponse

class PilotSecurity:
    def __init__(self,app):
        self.app=app
        self.buckets=OrderedDict()
        self.requests=0
        self.rejected=0
    async def __call__(self,scope,receive,send):
        if scope["type"]!="http":return await self.app(scope,receive,send)
        path=scope.get("path","")
        headers=dict(scope["headers"])
        self.requests+=1
        async def secured(message):
            if message["type"]=="http.response.start":
                hdr=message.setdefault("headers",[])
                hdr.extend([(b"x-content-type-options",b"nosniff"),(b"x-frame-options",b"DENY"),(b"referrer-policy",b"no-referrer"),(b"permissions-policy",b"camera=(), geolocation=(), microphone=(self)"),(b"content-security-policy",b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")])
                if path.startswith("/api/") and not any(k.lower()==b"cache-control" for k,v in hdr):hdr.append((b"cache-control",b"no-store"))
            await send(message)
        async def reject(code,detail):
            self.rejected+=1
            await JSONResponse({"detail":detail},status_code=code)(scope,receive,secured)
        if scope.get("method") in ("POST","PUT","PATCH"):
            try:size=int(headers.get(b"content-length",b"0"))
            except ValueError:return await reject(400,"Invalid content length")
            if size<0 or size>13*1024*1024:return await reject(413,"Request too large")
        if os.getenv("DECLIC_PILOT_LIMITS")=="1" and path.startswith("/api/") and path!="/api/health":
            now=time.monotonic();window=int(now//60)
            ip=(scope.get("client") or ("unknown",0))[0]
            auth=headers.get(b"authorization",b"")
            # Anonymous authentication requests limited by peer IP; authenticated
            # requests by token hash. No trust of forwarded headers here.
            group="auth" if path.startswith("/api/auth/") else "ai" if path in ("/api/studio","/api/studio/audio","/api/studio/review","/api/coach") else "api"
            principal=ip if group=="auth" or not auth else hashlib.sha256(auth).hexdigest()
            key=(principal,group)
            prior,count=self.buckets.get(key,(window,0))
            if prior!=window:count=0
            limit={"auth":12,"ai":30,"api":180}[group]
            if count>=limit:return await reject(429,"Request limit reached; retry in a minute")
            self.buckets[key]=(window,count+1);self.buckets.move_to_end(key)
            while len(self.buckets)>4096:self.buckets.popitem(last=False)
        return await self.app(scope,receive,secured)
