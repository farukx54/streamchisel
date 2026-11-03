"""Yayıncının kamerasını (yüzünü) otomatik bulma. Tamamen çevrimdışı (OpenCV).

Videodan birkaç kare alır, her karede yüz arar, karelerin çoğunda aynı yerde
duran yüzü "kamera" kabul eder. Kareler ffmpeg ile okunur; böylece Windows'ta
Türkçe karakterli klasör yollarında (ör. Masaüstü) sorun çıkmaz.
"""

from __future__ import annotations

import subprocess
from typing import Optional

from .ffmpeg_tools import _CREATE_FLAGS, find_tool, probe


def _frame(path: str, t: float, width: int = 960):
    import cv2
    import numpy as np

    args = [find_tool("ffmpeg"), "-v", "error", "-nostdin", "-ss", f"{t:.2f}", "-i", path,
            "-frames:v", "1", "-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "png", "-"]
    out = subprocess.run(args, capture_output=True, creationflags=_CREATE_FLAGS).stdout
    if not out:
        return None
    return cv2.imdecode(np.frombuffer(out, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)


def _cascade(name: str):
    import sys
    from pathlib import Path

    import cv2

    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    candidates = [base / "assets" / "models" / name]
    if hasattr(cv2, "data"):
        candidates.append(Path(cv2.data.haarcascades) / name)
    for f in candidates:
        if f.is_file():
            fs = cv2.FileStorage(f.read_text(encoding="utf-8"), cv2.FILE_STORAGE_READ | cv2.FILE_STORAGE_MEMORY)
            c = cv2.CascadeClassifier()
            if c.read(fs.getFirstTopLevelNode()) and not c.empty():
                return c
    return None


def _detector():
    """Yüz modelini dosya yolu vermeden, bellekten yükler.

    OpenCV Windows'ta Türkçe karakterli yollardan (Masaüstü vb.) dosya açamayabiliyor;
    bu yüzden XML'i Python ile okuyup belleğe veriyoruz.
    """
    import sys
    from pathlib import Path

    import cv2

    name = "haarcascade_frontalface_default.xml"
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    candidates = [base / "assets" / "models" / name]
    if hasattr(cv2, "data"):
        candidates.append(Path(cv2.data.haarcascades) / name)
    for f in candidates:
        if f.is_file():
            fs = cv2.FileStorage(f.read_text(encoding="utf-8"),
                                 cv2.FILE_STORAGE_READ | cv2.FILE_STORAGE_MEMORY)
            c = cv2.CascadeClassifier()
            if c.read(fs.getFirstTopLevelNode()) and not c.empty():
                return c
    raise RuntimeError("Yüz algılama modeli yüklenemedi.")


def find_faces(path: str, start: float = 0.0, end: Optional[float] = None, samples: int = 12) -> dict:
    """Karelerdeki yüzleri bulur ve en tutarlı yüzü döndürür (0..1 koordinatlarla)."""
    info = probe(path)
    end = info["duration"] if end is None else min(end, info["duration"])
    span = max(0.1, end - start)
    det = _detector()
    eyes = _cascade("haarcascade_eye.xml")  # yazıları/desenleri yüz sanmayı önlemek için göz kontrolü
    hits: list[tuple[float, float, float, float, int]] = []
    used = 0
    for i in range(samples):
        t = start + span * (i + 0.5) / samples
        img = _frame(path, t)
        if img is None:
            continue
        used += 1
        h, w = img.shape[:2]
        faces = det.detectMultiScale(img, scaleFactor=1.1, minNeighbors=6,
                                     minSize=(max(20, w // 60), max(20, w // 60)))
        for (x, y, fw, fh) in faces:
            if fw < w * 0.025:  # sohbet yazısı gibi çok küçük "yüzler" gerçek kamera olamaz
                continue
            if eyes is not None:
                import cv2
                # Göz modeli ~20 px altını göremez: yüzü 160 px genişliğe büyütüp üst kısmında göz ara
                face_img = cv2.resize(img[y:y + fh, x:x + fw], (160, int(160 * fh / max(1, fw))))
                top = face_img[: int(face_img.shape[0] * 0.6)]
                found = eyes.detectMultiScale(top, scaleFactor=1.08, minNeighbors=3, minSize=(18, 18))
                if len(found) == 0:
                    continue
            hits.append((float(x / w), float(y / h), float(fw / w), float(fh / h), i))
    if not hits:
        return {"face": None, "frames": used}

    # Merkezleri birbirine yakın yüzleri grupla; en çok karede görüneni seç
    groups: list[list[tuple[float, float, float, float, int]]] = []
    for b in hits:
        cx, cy = b[0] + b[2] / 2, b[1] + b[3] / 2
        for g in groups:
            gx = sum(x[0] + x[2] / 2 for x in g) / len(g)
            gy = sum(x[1] + x[3] / 2 for x in g) / len(g)
            if abs(cx - gx) < 0.07 and abs(cy - gy) < 0.09:
                g.append(b)
                break
        else:
            groups.append([b])
    frames_of = lambda g: len({b[4] for b in g})  # noqa: E731  (aynı karede çift algılamayı sayma)
    # En çok karede görünen; eşitse daha büyük yüz (kamera penceresi genelde en büyük sabit yüzdür)
    best = max(groups, key=lambda g: (frames_of(g), sum(b[2] for b in g) / len(g)))
    seen = frames_of(best)
    if seen < max(2, used // 4):  # tek karede görünen yüz büyük ihtimalle oyundaki bir karakter
        return {"face": None, "frames": used}

    def med(vals):
        s = sorted(vals)
        return s[len(s) // 2]

    face = {"x": med([b[0] for b in best]), "y": med([b[1] for b in best]),
            "w": med([b[2] for b in best]), "h": med([b[3] for b in best])}
    frames_with_face = sorted({b[4] for b in best})
    t_mid = start + span * (frames_with_face[len(frames_with_face) // 2] + 0.5) / samples
    overlay = find_overlay(path, t_mid, face)
    return {"face": face, "overlay": overlay, "frames": used, "hits": seen,
            "confidence": round(seen / max(1, used), 2)}


def find_overlay(path: str, t: float, face: dict) -> Optional[dict]:
    """Yüzün etrafındaki kamera penceresinin kenarlarını bulmaya çalışır.

    Yayıncı kameraları oyun görüntüsünün üstüne yapıştırılmış dikdörtgenlerdir; kenarlarında
    boydan boya keskin bir geçiş olur. Yüzün her yönünde bu çizgiyi arıyoruz.
    """
    import cv2
    import numpy as np

    img = _frame(path, t, width=960)
    if img is None:
        return None
    H, W = img.shape[:2]
    g = img.astype(np.float32)
    gx = np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3))
    gy = np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    fx, fy, fw, fh = face["x"] * W, face["y"] * H, face["w"] * W, face["h"] * H
    cx, cy = fx + fw / 2, fy + fh / 2

    def continuity(grad: np.ndarray, axis: int) -> np.ndarray:
        """Her sütun (ya da satır) boyunca keskin kenarın kesintisiz süren oranı (0..1)."""
        thr = max(25.0, float(np.percentile(grad, 85)))
        e = (grad > thr).astype(np.float32)
        if axis == 0:  # sütunlar: ±1 piksel kaymaya izin ver
            e = np.maximum(e, np.maximum(np.roll(e, 1, axis=1), np.roll(e, -1, axis=1)))
            return e.mean(axis=0)
        e = np.maximum(e, np.maximum(np.roll(e, 1, axis=0), np.roll(e, -1, axis=0)))
        return e.mean(axis=1)

    def best_line(prof: np.ndarray, lo: int, hi: int) -> Optional[int]:
        lo, hi = max(0, lo), min(len(prof) - 1, hi)
        if hi - lo < 3:
            return None
        seg = prof[lo:hi + 1]
        i = int(seg.argmax())
        return lo + i if seg[i] >= 0.6 else None

    # Dikey kenarlar: yüzün hemen etrafındaki (kamera penceresinin içinde kalan) satır bandında ara
    r0, r1 = int(max(0, fy - fh * 0.3)), int(min(H, fy + fh * 1.6))
    cols = continuity(gx[r0:r1], axis=0)
    left = best_line(cols, int(cx - fw * 4.5), int(fx - fw * 0.3))
    right = best_line(cols, int(fx + fw * 1.3), int(cx + fw * 4.5))
    # Yatay kenarlar
    c0, c1 = int(max(0, fx - fw * 0.3)), int(min(W, fx + fw * 1.3))
    rows = continuity(gy[:, c0:c1], axis=1)
    top = best_line(rows, int(cy - fh * 3.5), int(fy - fh * 0.2))
    bottom = best_line(rows, int(fy + fh * 1.3), int(cy + fh * 4.5))

    # Kenar bulunamayan taraf için görüntü sınırını ya da makul bir payı kullan
    L = left if left is not None else (0 if cx < W * 0.15 else None)
    R = right if right is not None else (W - 1 if cx > W * 0.85 else None)
    T = top if top is not None else (0 if cy < H * 0.2 else None)
    B = bottom if bottom is not None else (H - 1 if cy > H * 0.8 else None)
    if None in (L, R, T, B):
        return None
    w, h = R - L, B - T
    # Mantıksız kutuları ele: yüz içeride olmalı ve kutu yüzden çok büyük olmamalı
    if w < fw * 1.4 or h < fh * 1.4 or w > fw * 9 or h > fh * 9 or w > W * 0.7 or h > H * 0.8:
        return None
    pad = 2  # kenar çizgisinin kendisini (çerçeveyi) içeri alma
    return {"x": (L + pad) / W, "y": (T + pad) / H, "w": (w - 2 * pad) / W, "h": (h - 2 * pad) / H}
