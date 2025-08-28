import os
from urllib.parse import urlparse
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp

API_KEY = os.getenv("API_KEY")  # عيّنه في Render
ALLOW_ORIGINS = os.getenv("ALLOW_ORIGINS", "*")
BLOCKLIST = [d.strip().lower() for d in os.getenv("BLOCKLIST", "").split(",") if d.strip()]

app = FastAPI(title="yt-dlp Direct Link API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOW_ORIGINS.split(",")] if ALLOW_ORIGINS else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DirectReq(BaseModel):
    url: str
    format: Optional[str] = "best"  # best | bestvideo+bestaudio | anche others if you want

def domain_blocked(u: str) -> bool:
    try:
        host = urlparse(u).netloc.lower()
    except Exception:
        return True
    return any(host == d or host.endswith("." + d) for d in BLOCKLIST)

def pick_best_progressive(info: Dict[str, Any]) -> Dict[str, Any]:
    # اختر أفضل صيغة تجمع صوت+فيديو (progressive)
    fmts = info.get("formats", []) or []
    progressives = [
        f for f in fmts
        if (f.get("acodec") not in (None, "none")) and (f.get("vcodec") not in (None, "none"))
    ]
    # رتب حسب معدل البت (tbr) إن وجد
    progressives.sort(key=lambda f: (f.get("tbr") or 0), reverse=True)
    return progressives[0] if progressives else None

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/direct")
def direct(req: DirectReq, x_api_key: Optional[str] = Header(None)):
    if API_KEY:
        if not x_api_key or x_api_key != API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")

    if not req.url or not req.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Bad URL")

    if BLOCKLIST and domain_blocked(req.url):
        raise HTTPException(status_code=403, detail="Domain is blocked by policy")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        # لا تنزل شيء، فقط استخرج معلومات وروابط مباشرة
        "simulate": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=422, detail=f"yt-dlp error: {str(e)}")

    result = {
        "title": info.get("title"),
        "webpage_url": info.get("webpage_url"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader"),
        "direct": []  # قائمة روابط مباشرة
    }

    # حالة دمج صوت/فيديو: requested_formats
    if info.get("requested_formats"):
        for f in info["requested_formats"]:
            result["direct"].append({
                "url": f.get("url"),
                "ext": f.get("ext"),
                "format_id": f.get("format_id"),
                "filesize": f.get("filesize") or f.get("filesize_approx"),
                "protocol": f.get("protocol"),
            })
    elif info.get("url"):
        # صيغة واحدة مباشرة
        result["direct"].append({
            "url": info.get("url"),
            "ext": info.get("ext"),
            "format_id": info.get("format_id"),
            "filesize": info.get("filesize") or info.get("filesize_approx"),
            "protocol": info.get("protocol"),
        })
    else:
        # اختر أفضل progressive
        best = pick_best_progressive(info)
        if best:
            result["direct"].append({
                "url": best.get("url"),
                "ext": best.get("ext"),
                "format_id": best.get("format_id"),
                "filesize": best.get("filesize") or best.get("filesize_approx"),
                "protocol": best.get("protocol"),
            })

    if not result["direct"]:
        raise HTTPException(status_code=404, detail="No direct URL found")

    return result
