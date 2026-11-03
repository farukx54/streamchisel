"""Zaman çizelgesi için ses dalgası ve küçük kare şeridi. Sonuçlar önbelleğe yazılır,
aynı video ikinci kez açıldığında anında gelir."""

from __future__ import annotations

import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from .ffmpeg_tools import _CREATE_FLAGS, find_tool, probe

RATE = 20       # dalga şekli: saniyede 20 tepe değeri (3 saatlik yayın ≈ 216 KB)
STRIP_N = 90    # kare şeridindeki kare sayısı
STRIP_H = 72    # kare yüksekliği (px)


def cache_dir() -> Path:
    d = Path.home() / ".streamchisel" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_key(path: str) -> str:
    st = Path(path).stat()
    return hashlib.sha1(f"{Path(path).resolve()}|{st.st_size}|{int(st.st_mtime)}".lower().encode("utf-8")).hexdigest()[:20]


def waveform(path: str, on_progress: Optional[Callable[[float], None]] = None) -> Optional[Path]:
    """Her 1/RATE sn için 0..255 tepe değeri (karekök ölçekli, sessiz sesler de görünsün)."""
    import numpy as np

    out = cache_dir() / f"{cache_key(path)}.peaks"
    if out.exists():
        return out
    info = probe(path)
    if not info["has_audio"]:
        return None
    sr = 4000
    hop = sr // RATE
    args = [find_tool("ffmpeg"), "-v", "error", "-nostdin", "-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=_CREATE_FLAGS)
    vals: list = []
    rest = np.zeros(0, dtype=np.float32)
    assert proc.stdout is not None
    total = max(1, int(info["duration"] * RATE))
    while True:
        buf = proc.stdout.read(hop * 4 * 600)
        if not buf:
            break
        x = np.concatenate([rest, np.frombuffer(buf[: len(buf) // 4 * 4], dtype=np.float32)])
        n = len(x) // hop
        if n:
            vals.append(np.abs(x[: n * hop]).reshape(n, hop).max(axis=1))
        rest = x[n * hop:]
        if on_progress:
            on_progress(min(0.99, sum(len(v) for v in vals) / total))
    proc.wait()
    if not vals:
        return None
    pk = np.concatenate(vals)
    pk = np.sqrt(np.clip(pk / (np.percentile(pk, 99.5) + 1e-6), 0, 1))
    tmp = out.with_suffix(".tmp")
    tmp.write_bytes((pk * 255).astype(np.uint8).tobytes())
    tmp.replace(out)
    return out


def _grab(path: str, t: float, w: int, h: int):
    import cv2
    import numpy as np

    args = [find_tool("ffmpeg"), "-v", "error", "-nostdin", "-skip_frame", "nokey", "-noaccurate_seek", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1",
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}", "-f", "image2pipe", "-vcodec", "png", "-"]
    data = subprocess.run(args, capture_output=True, creationflags=_CREATE_FLAGS).stdout
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) if data else None
    return img if img is not None else np.zeros((h, w, 3), np.uint8)


def filmstrip(path: str, on_progress: Optional[Callable[[float], None]] = None) -> Path:
    """STRIP_N kareyi yan yana tek JPG'de birleştirir."""
    import cv2

    out = cache_dir() / f"{cache_key(path)}.strip.jpg"
    if out.exists():
        return out
    info = probe(path)
    d = max(0.1, info["duration"])
    h = STRIP_H
    w = int(round(h * 16 / 9))
    times = [d * (i + 0.5) / STRIP_N for i in range(STRIP_N)]
    done = [0]

    def one(t):
        img = _grab(path, t, w, h)
        done[0] += 1
        if on_progress:
            on_progress(done[0] / STRIP_N)
        return img

    with ThreadPoolExecutor(max_workers=4) as ex:
        imgs = list(ex.map(one, times))
    ok, buf = cv2.imencode(".jpg", cv2.hconcat(imgs), [cv2.IMWRITE_JPEG_QUALITY, 70])
    tmp = out.with_suffix(".tmp")
    tmp.write_bytes(buf.tobytes())
    tmp.replace(out)
    return out
