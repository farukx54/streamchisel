"""FFmpeg/FFprobe bulma, çalıştırma, ilerleme okuma ve donanım kodlayıcı tespiti."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

ProgressCb = Optional[Callable[[float], None]]

# Windows'ta ffmpeg çalışırken siyah konsol penceresi açılmasın
_CREATE_FLAGS = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


def _bin_dir() -> Path:
    """Program paketlendiğinde ffmpeg.exe'nin duracağı klasör (bin/)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "bin"


@lru_cache(maxsize=None)
def find_tool(name: str) -> str:
    exe = name + (".exe" if sys.platform == "win32" else "")
    bundled = _bin_dir() / exe
    if bundled.exists():
        return str(bundled)
    env = os.environ.get(f"KLIPO_{name.upper()}")
    if env and Path(env).exists():
        return env
    found = shutil.which(name)
    if not found:
        raise FileNotFoundError(f"{name} bulunamadı. bin/ klasörüne koyun veya PATH'e ekleyin.")
    return found


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=_CREATE_FLAGS, check=check,
    )


def probe(path: str) -> dict:
    out = run([find_tool("ffprobe"), "-v", "error", "-print_format", "json",
               "-show_format", "-show_streams", path]).stdout
    data = json.loads(out)
    v = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        raise ValueError("Dosyada video akışı yok.")
    num, den = (v.get("avg_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    return {
        "duration": float(data["format"].get("duration", 0)),
        "width": int(v["width"]),
        "height": int(v["height"]),
        "fps": fps,
        "has_audio": a is not None,
    }


@lru_cache(maxsize=1)
def ffmpeg_major() -> int:
    """ffmpeg ana sürüm numarası; tanınmayan (git) derlemeler için yeni sürüm varsayılır."""
    import re

    first = run([find_tool("ffmpeg"), "-version"], check=False).stdout.splitlines()[:1]
    m = re.search(r"ffmpeg version n?(\d+)\.", first[0] if first else "")
    return int(m.group(1)) if m else 99


def filter_script_args(path: str) -> list[str]:
    """Filtre grafiğini dosyadan okutma: ffmpeg 7+ '-/filter_complex', eskiler '-filter_complex_script'.

    (Uzun grafikleri komut satırına yazmak Windows'un 8191 karakter sınırına takılır.)
    """
    if ffmpeg_major() >= 7:
        return ["-/filter_complex", path]
    return ["-filter_complex_script", path]


# Denenecek sıra: NVIDIA → Intel → AMD → işlemci
_HW_CANDIDATES = ["h264_nvenc", "h264_qsv", "h264_amf"]


@lru_cache(maxsize=1)
def detect_encoder() -> str:
    """Gerçekten çalışan ilk donanım kodlayıcıyı döndürür, yoksa libx264."""
    ff = find_tool("ffmpeg")
    listed = run([ff, "-hide_banner", "-encoders"], check=False).stdout
    for enc in _HW_CANDIDATES:
        if enc not in listed:
            continue
        # Listede olması yetmez; ekran kartı yoksa açılamaz. 1 karelik deneme yap.
        test = run([ff, "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.1",
                    "-frames:v", "1", "-c:v", enc, "-f", "null", "-"], check=False)
        if test.returncode == 0:
            return enc
    return "libx264"


def encoder_args(encoder: str, quality: str) -> list[str]:
    """Kalite: high | balanced | small."""
    if encoder == "auto":
        encoder = detect_encoder()
    q = {"high": 0, "balanced": 1, "small": 2}.get(quality, 0)
    if encoder == "h264_nvenc":
        cq = [19, 23, 28][q]
        return ["-c:v", encoder, "-preset", "p5", "-rc", "vbr", "-cq", str(cq), "-b:v", "0"]
    if encoder == "h264_qsv":
        return ["-c:v", encoder, "-global_quality", str([20, 24, 29][q])]
    if encoder == "h264_amf":
        qp = [20, 24, 29][q]
        return ["-c:v", encoder, "-rc", "cqp", "-qp_i", str(qp), "-qp_p", str(qp)]
    crf = [19, 23, 28][q]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf)]


def run_with_progress(args: list[str], total_seconds: float, on_progress: ProgressCb = None,
                      cwd: Optional[str] = None) -> None:
    """ffmpeg'i -progress ile çalıştırır, 0..1 arası ilerleme bildirir."""
    cmd = [args[0], "-hide_banner", "-nostats", "-progress", "pipe:1"] + args[1:]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace", creationflags=_CREATE_FLAGS,
                            cwd=cwd)
    assert proc.stdout is not None
    for line in proc.stdout:
        if line.startswith("out_time_us=") and on_progress and total_seconds > 0:
            try:
                t = int(line.split("=", 1)[1]) / 1_000_000
                on_progress(max(0.0, min(1.0, t / total_seconds)))
            except ValueError:
                pass
    stderr = proc.stderr.read() if proc.stderr else ""
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg hatası:\n" + stderr[-3000:])
    if on_progress:
        on_progress(1.0)
