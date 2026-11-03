"""Linkten video indirme (yt-dlp). YouTube, Kick, Twitch, TikTok, Instagram, X ..."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .ffmpeg_tools import find_tool

QUALITY_FORMATS = {
    "best": "bv*+ba/b",
    "1080": "bv*[height<=1080]+ba/b[height<=1080]/b",
    "720": "bv*[height<=720]+ba/b[height<=720]/b",
    "480": "bv*[height<=480]+ba/b[height<=480]/b",
}


def probe_url(url: str) -> dict:
    """İndirmeden önce başlık, süre, kanal ve küçük resim bilgisini getirir."""
    import yt_dlp

    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "title": info.get("title"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader") or info.get("channel"),
        "thumbnail": info.get("thumbnail"),
        "platform": info.get("extractor_key"),
        "max_height": max((f.get("height") or 0 for f in info.get("formats") or []), default=0),
    }


def download(url: str, out_dir: str, quality: str = "best",
             on_progress: Optional[Callable[[dict], None]] = None) -> str:
    """Videoyu indirir, kaydedilen dosyanın yolunu döndürür."""
    import yt_dlp

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    result: dict = {}

    def hook(d: dict) -> None:
        if d["status"] == "downloading" and on_progress:
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            on_progress({"stage": "download", "progress": done / total if total else 0.0,
                         "downloaded": done, "total": total, "speed": d.get("speed")})
        elif d["status"] == "finished":
            result["file"] = d.get("filename")

    opts = {
        "format": QUALITY_FORMATS.get(quality, QUALITY_FORMATS["best"]),
        "merge_output_format": "mp4",
        "outtmpl": str(Path(out_dir) / "%(title).80s [%(id)s].%(ext)s"),
        "ffmpeg_location": str(Path(find_tool("ffmpeg")).parent),
        "progress_hooks": [hook],
        "quiet": True,
        "no_warnings": True,
        "windowsfilenames": True,
        "concurrent_fragment_downloads": 4,  # Kick/Twitch VOD'ları parça parça iner
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        final = ydl.prepare_filename(info)
    final_mp4 = str(Path(final).with_suffix(".mp4"))
    return final_mp4 if Path(final_mp4).exists() else (result.get("file") or final)
