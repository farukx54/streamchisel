"""Uzun yayında "en iyi anları" bulur. Tamamen çevrimdışı, API yok.

Yöntem:
  1. Sesi düşük örnekleme hızında akıtıp her 0.5 sn için ses yüksekliğini (dB) ölçeriz.
  2. Her pencereyi kendi çevresinin (±60 sn) ortancasıyla karşılaştırırız: yayıncının
     normal konuşmasına göre ani bağırma, gülme, heyecan = yüksek puan.
  3. İsteğe bağlı: altyazı varsa "oha, yok artık, what, gg" gibi tepki kelimeleri puanı artırır.
  4. Puanı en yüksek, birbiriyle çakışmayan N klip seçilir; zirve klibin ~%40'ına denk gelir
     (öncesinde biraz bağlam, sonrasında tepki).
"""

from __future__ import annotations

import subprocess
from typing import Callable, Optional

from .ffmpeg_tools import _CREATE_FLAGS, find_tool, probe

HOP = 0.5  # saniye
SR = 4000

REACTION_WORDS = {
    # Türkçe
    "oha", "vay", "yok", "artık", "lan", "inanılmaz", "efsane", "aman", "olamaz", "nasıl", "bak",
    "harika", "müthiş", "ölüyorum", "kanka", "abi", "yaa", "hahaha", "haha", "ahah", "aaa", "yuh",
    "helal", "kazandık", "kaybettik", "öldüm", "öldü", "gol", "bitti", "delirdim",
    # İngilizce
    "wow", "what", "omg", "no", "yes", "insane", "crazy", "bro", "dude", "lets", "go", "gg", "clutch",
    "wtf", "holy", "oh", "my", "god", "haha", "lol", "unbelievable", "dead", "won", "lost",
}


def loudness_curve(path: str, start: float = 0.0, end: Optional[float] = None,
                   on_progress: Optional[Callable[[float], None]] = None):
    """Her HOP saniye için RMS (dB) dizisi döndürür. Uzun yayınlarda belleği şişirmez."""
    import numpy as np

    info = probe(path)
    if not info["has_audio"]:
        raise ValueError("Bu videoda ses yok; en iyi anlar sesten bulunuyor.")
    end = info["duration"] if end is None else min(end, info["duration"])
    span = max(0.1, end - start)
    args = [find_tool("ffmpeg"), "-v", "error", "-nostdin"]
    if start:
        args += ["-ss", f"{start:.3f}"]
    args += ["-to", f"{end:.3f}", "-i", path, "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            creationflags=_CREATE_FLAGS)
    hop = int(SR * HOP)
    block = hop * 240 * 4  # ~2 dakikalık parça
    out: list[float] = []
    rest = np.zeros(0, dtype=np.float32)
    assert proc.stdout is not None
    while True:
        buf = proc.stdout.read(block)
        if not buf:
            break
        x = np.concatenate([rest, np.frombuffer(buf[: len(buf) // 4 * 4], dtype=np.float32)])
        n = len(x) // hop
        if n:
            frames = x[: n * hop].reshape(n, hop)
            rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
            out.extend((20 * np.log10(rms + 1e-6)).tolist())
        rest = x[n * hop:]
        if on_progress:
            on_progress(min(0.99, len(out) * HOP / span))
    proc.wait()
    return np.array(out, dtype=np.float64), start


def _rolling_median(x, win: int):
    import numpy as np

    # Hızlı yaklaşık ortanca: her 'step' pencerede bir hesaplayıp aradakileri doldur
    n = len(x)
    step = max(1, win // 8)
    centers = np.arange(0, n, step)
    meds = np.array([np.median(x[max(0, c - win):min(n, c + win)]) for c in centers])
    return np.interp(np.arange(n), centers, meds)


def score_curve(db, words: Optional[list] = None, t0: float = 0.0):
    """Her pencere için heyecan puanı (0 civarı = sıradan, yükseldikçe ilginç)."""
    import numpy as np

    db = np.maximum(db, -70.0)
    base = _rolling_median(db, int(60 / HOP))
    spread = np.maximum(3.0, _rolling_median(np.abs(db - base), int(60 / HOP)) * 1.5)
    z = (db - base) / spread
    # Kısa süreli yoğunluk: 3 sn içindeki en yüksek sesler
    k = int(3 / HOP)
    kernel = np.ones(k) / k
    energy = np.convolve(np.clip(z, 0, None), kernel, mode="same")
    peak = np.convolve(np.clip(z, 0, None) ** 2, kernel, mode="same")
    score = energy + 0.35 * np.sqrt(peak)
    # Uzun sessizlik/menü bekleme anlarını aşağı çek
    score -= 0.6 * (db < base - 12)
    if words:
        bonus = np.zeros_like(score)
        for w in words:
            txt = "".join(ch for ch in str(w.get("text", "")).lower() if ch.isalpha())
            if txt in REACTION_WORDS or txt.startswith("haha") or txt.startswith("ahah"):
                i = int((float(w["start"]) - t0) / HOP)
                if 0 <= i < len(bonus):
                    bonus[max(0, i - 2):i + 3] += 0.5
        score += np.convolve(bonus, kernel, mode="same")
    return score


def find_highlights(path: str, start: float = 0.0, end: Optional[float] = None,
                    clip_len: float = 45.0, count: int = 6, words: Optional[list] = None,
                    on_progress: Optional[Callable[[float], None]] = None) -> list[dict]:
    """En iyi `count` anı döndürür: [{start, end, peak, score, level}] (kaynak saniyeleri)."""
    import numpy as np

    db, t0 = loudness_curve(path, start, end, on_progress)
    if len(db) < 8:
        return []
    score = score_curve(db, words, t0)
    total = len(db) * HOP
    clip_len = max(5.0, min(clip_len, total))
    L = int(clip_len / HOP)
    # Klip puanı = klibin içindeki en iyi 6 sn'nin ortalaması + genel ortalama
    k6 = int(6 / HOP)
    best6 = np.convolve(score, np.ones(k6) / k6, mode="same")
    taken = np.zeros(len(score), dtype=bool)
    out: list[dict] = []
    order = np.argsort(-best6)
    for i in order:
        if len(out) >= count:
            break
        if best6[i] <= 0.15:
            break
        s = int(max(0, min(len(score) - L, i - L * 0.4)))
        e = s + L
        if taken[s:e].any():
            continue
        taken[max(0, s - int(5 / HOP)):e + int(5 / HOP)] = True
        clip_score = float(best6[i] + 0.3 * score[s:e].mean())
        out.append({"start": round(t0 + s * HOP, 2), "end": round(t0 + min(e, len(score)) * HOP, 2),
                    "peak": round(float(t0 + i * HOP), 2), "score": round(clip_score, 3)})
    if out:
        top = max(o["score"] for o in out)
        out = [o for o in out if o["score"] >= top * 0.2]  # zirveye göre çok sönük olanları atma
        for o in out:
            r = o["score"] / top if top > 0 else 0
            o["level"] = "çok yüksek" if r > 0.85 else "yüksek" if r > 0.6 else "orta"
    if on_progress:
        on_progress(1.0)
    return out


def curve_preview(path: str, start: float = 0.0, end: Optional[float] = None, points: int = 400) -> list[float]:
    """Zaman çizelgesinde göstermek için heyecan eğrisini `points` noktaya küçültür (0..1)."""
    import numpy as np

    db, t0 = loudness_curve(path, start, end)
    sc = score_curve(db, None, t0)
    if not len(sc):
        return []
    idx = np.linspace(0, len(sc), points + 1).astype(int)
    v = np.array([sc[a:b].max() if b > a else 0 for a, b in zip(idx[:-1], idx[1:])])
    v = np.clip(v, 0, None)
    return (v / (v.max() or 1)).round(3).tolist()
