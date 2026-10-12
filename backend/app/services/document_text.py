"""Extract bounded PDF text in a resource-limited child; never perform OCR."""
import asyncio
import json
import subprocess
import sys
from fastapi import HTTPException

# Parsing runs outside the web process. A small compressed upload may contain
# enormous decoded streams, so page/character limits alone are insufficient.
_PDF_WORKER = r'''
import io,json,resource,sys
resource.setrlimit(resource.RLIMIT_AS, (384*1024*1024,384*1024*1024))
resource.setrlimit(resource.RLIMIT_CPU, (5,5))
from pypdf import PdfReader
try:
    reader=PdfReader(io.BytesIO(sys.stdin.buffer.read(5*1024*1024+1)),strict=False)
    if reader.is_encrypted:
        print(json.dumps({"state":"manual"}))
    elif len(reader.pages)>50:
        print(json.dumps({"state":"too_many_pages"}))
    else:
        parts=[]
        length=0
        for page in reader.pages:
            value=page.extract_text() or ""
            length+=len(value)+(1 if parts else 0)
            if length>16000:
                print(json.dumps({"state":"too_long"}))
                break
            parts.append(value)
        else:
            text="\n".join(parts)
            print(json.dumps({"state":"ready" if text.strip() else "manual","text":text if text.strip() else None}))
except Exception:
    print(json.dumps({"state":"manual"}))
'''


def _extract(content):
    try:
        result = subprocess.run([sys.executable, "-c", _PDF_WORKER], input=content,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8, check=False)
        if result.returncode or len(result.stdout) > 200000:
            return {"state": "manual"}
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return {"state": "manual"}


async def pdf_text(content):
    result = await asyncio.to_thread(_extract, content)
    if result["state"] in {"too_long", "too_many_pages"}:
        raise HTTPException(422, "PDF exceeds 50 pages or 16000 extracted characters; shorten or split it before uploading. No text was imported.")
    return result.get("text") if result["state"] == "ready" else None
