"""Sessiz bölümleri bulma ve korunacak parçaları hesaplama (ffmpeg silencedetect)."""

from __future__ import annotations

import re
from typing import Optional

from .ffmpeg_tools import find_tool, run

Segment = tuple[float, float]

_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_END = re.compile(r"silence_end:\s*(-?[\d.]+)")


def detect_silences(path: str, threshold_db: float, min_silence: float,
                    start: float = 0.0, end: Optional[float] = None) -> list[Segment]:
    """Sessiz aralıkları döndürür. Zamanlar 'start'a göredir (klip başı = 0)."""
    args = [find_tool("ffmpeg"), "-hide_banner", "-nostats"]
    if start:
        args += ["-ss", f"{start:.3f}"]
    if end is not None:
        args += ["-to", f"{end:.3f}"]
    args += ["-i", path, "-vn", "-af",
             f"silencedetect=noise={threshold_db}dB:d={min_silence}", "-f", "null", "-"]
    log = run(args, check=False).stderr
    silences: list[Segment] = []
    cur: Optional[float] = None
    for line in log.splitlines():
        m = _START.search(line)
        if m:
            cur = max(0.0, float(m.group(1)))
            continue
        m = _END.search(line)
        if m and cur is not None:
            silences.append((cur, float(m.group(1))))
            cur = None
    if cur is not None:  # dosya sessizlikle bitiyor
        silences.append((cur, float("inf")))
    return silences


def keep_segments(silences: list[Segment], duration: float, padding: float,
                  fps: float, min_keep: float = 0.25) -> list[Segment]:
    """Sessizliklerin tersini alır; konuşma kenarlarına 'padding' kadar pay bırakır.

    Sınırlar video karelerine hizalanır, böylece ses ve görüntü kaymaz.
    """
    frame = 1.0 / fps
    keeps: list[Segment] = []
    cursor = 0.0
    for s, e in silences:
        s_pad = min(duration, s + padding)
        e_pad = max(0.0, min(duration, e) - padding)
        if s_pad > cursor:
            keeps.append((cursor, s_pad))
        cursor = max(cursor, e_pad)
    if cursor < duration:
        keeps.append((cursor, duration))

    snapped: list[Segment] = []
    for a, b in keeps:
        a = round(a / frame) * frame
        b = round(b / frame) * frame
        if b - a < min_keep:
            continue
        if snapped and a <= snapped[-1][1]:  # üst üste binenleri birleştir
            snapped[-1] = (snapped[-1][0], max(snapped[-1][1], b))
        else:
            snapped.append((a, b))
    return snapped


def total(segments: list[Segment]) -> float:
    return sum(b - a for a, b in segments)


def remap_time(t: float, segments: list[Segment]) -> Optional[float]:
    """Kaynak zamanını kesilmiş videodaki zamana çevirir; kesilen yerdeyse None."""
    offset = 0.0
    for a, b in segments:
        if t < a:
            return None
        if t <= b:
            return offset + (t - a)
        offset += b - a
    return None


def remap_span(t0: float, t1: float, segments: list[Segment]) -> Optional[Segment]:
    """Bir aralığı (ör. altyazı kelimesi) kesilmiş zamana taşır; kenardaysa kırpar."""
    offset = 0.0
    for a, b in segments:
        lo, hi = max(t0, a), min(t1, b)
        if lo < hi:
            return (offset + lo - a, offset + hi - a)
        offset += b - a
    return None


def select_expr(segments: list[Segment]) -> str:
    """ffmpeg select/aselect ifadesi: between(t,a,b)+between(t,c,d)+...

    Filtre grafiğinde tek tırnak içinde kullanılmalıdır: select='...'
    """
    return "+".join(f"between(t,{a:.4f},{b - 1e-4:.4f})" for a, b in segments)


def subtract(keeps: list[Segment], cuts: list[Segment], fps: float, min_keep: float = 0.1) -> list[Segment]:
    """Korunan parçalardan elle kesilen aralıkları çıkarır (kare sınırlarına hizalı)."""
    frame = 1.0 / fps
    cuts = sorted((round(a / frame) * frame, round(b / frame) * frame) for a, b in cuts if b > a)
    out = []
    for a, b in keeps:
        pieces = [(a, b)]
        for ca, cb in cuts:
            nxt = []
            for x, y in pieces:
                if cb <= x or ca >= y:
                    nxt.append((x, y))
                    continue
                if ca > x:
                    nxt.append((x, ca))
                if cb < y:
                    nxt.append((cb, y))
            pieces = nxt
        out += [(x, y) for x, y in pieces if y - x >= min_keep]
    return out


def remap_spans(t0: float, t1: float, segments: list[Segment]) -> list[Segment]:
    """Bir aralığın kesilmiş videoda düştüğü tüm parçalar (kesimden geçen zoom gibi)."""
    out, offset = [], 0.0
    for a, b in segments:
        lo, hi = max(t0, a), min(t1, b)
        if lo < hi:
            out.append((offset + lo - a, offset + hi - a))
        offset += b - a
    return out
