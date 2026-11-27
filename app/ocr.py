"""Bounded offline OCR for image-only PDF pages. No cloud upload."""
import os
import shutil
import subprocess
import math
import time
import fitz

def extract_pages(data, max_ocr=12, deadline_seconds=35):
    pages=[]; meta=[]
    executable=shutil.which("tesseract")
    deadline=time.monotonic()+deadline_seconds
    attempted=0
    with fitz.open(stream=data,filetype="pdf") as pdf:
        for i,p in enumerate(pdf):
            native=p.get_text()[:20000]
            # A page number/header can coexist with a full scanned image.
            mixed=bool(native.strip()) and len(native.strip())<100 and bool(p.get_images(full=True))
            if native.strip() and not mixed:
                pages.append((i,native));meta.append((i,"native"));continue
            status="empty";text=native
            if not executable:status="ocr_unavailable"
            elif attempted>=max_ocr or time.monotonic()>=deadline:status="ocr_deferred"
            else:
                attempted+=1
                try:
                    area=max(1,p.rect.width*p.rect.height)
                    scale=min(2.8,math.sqrt(6_000_000/area),3500/max(1,p.rect.width,p.rect.height))
                    pix=p.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csGRAY,alpha=False)
                    result=subprocess.run([executable,"stdin","stdout","-l",os.getenv("DECLIC_OCR_LANG","fra+eng"),"--psm","3"],input=pix.tobytes("png"),capture_output=True,timeout=max(.1,min(8,deadline-time.monotonic())),check=False)
                    if result.returncode==0:
                        recovered=result.stdout.decode("utf-8",errors="replace")[:20000]
                        if recovered.strip():
                            text=(native+"\n"+recovered)[:20000] if mixed else recovered
                            status="mixed_ocr" if mixed else "ocr"
                        else:status="empty"
                    else:status="ocr_failed"
                except (OSError,subprocess.TimeoutExpired,ValueError,RuntimeError):
                    status="ocr_failed"
            pages.append((i,text));meta.append((i,status))
    return pages,meta
