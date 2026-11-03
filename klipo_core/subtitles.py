"""Çevrimdışı otomatik altyazı (faster-whisper) ve ASS altyazı dosyası üretimi.

Kelime zamanları kesilmiş videonun zaman çizelgesine taşınır, sonra her kelime
konuşulurken vurgulanan "reels tarzı" altyazı oluşturulur.
"""

from __future__ import annotations

import os
import re
import subprocess
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .ffmpeg_tools import _CREATE_FLAGS, find_tool
from .silence import Segment, remap_span

# Model indirilirken çıkan zararsız Windows uyarılarını gizle
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
warnings.filterwarnings("ignore", module="huggingface_hub")


@dataclass
class Word:
    start: float
    end: float
    text: str


# --------------------------------------------------------------------------- yazıya çevirme

def models_dir() -> Path:
    env = os.environ.get("STREAMCHISEL_MODELS") or os.environ.get("KLIPO_MODELS")
    d = Path(env) if env else Path.home() / ".streamchisel" / "models"
    legacy = Path.home() / ".klipo" / "models"  # eski sürümde inen model tekrar inmesin
    if not env and not d.exists() and legacy.exists():
        return legacy
    d.mkdir(parents=True, exist_ok=True)
    return d


_MODELS: dict = {}  # yüklenen model süreç boyunca saklanır (her klipte yeniden yüklenmesin)


def _cuda_ok() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def _cpu_threads() -> int:
    n = os.cpu_count() or 4
    return max(2, min(8, n - 1 if n > 4 else n))


def _ensure_local(name: str, on_download: Optional[Callable[[], None]] = None) -> str:
    """Model diskte yoksa (ilk kullanım) indirir; yerel klasör yolunu döndürür."""
    if Path(name).exists():
        return name
    from faster_whisper.utils import download_model
    try:
        return download_model(name, local_files_only=True, cache_dir=str(models_dir()))
    except Exception:
        if on_download:
            on_download()
        return download_model(name, cache_dir=str(models_dir()))


def _load_model(name: str, on_download: Optional[Callable[[], None]] = None):
    from faster_whisper import WhisperModel  # ağır içe aktarma; sadece gerekince

    if name in _MODELS:
        return _MODELS[name]
    target = _ensure_local(name, on_download)
    m = None
    if _cuda_ok():
        try:
            m = WhisperModel(target, device="cuda", compute_type="float16")
            m._sc_gpu = True
        except Exception:
            m = None
    if m is None:
        m = WhisperModel(target, device="cpu", compute_type="int8", cpu_threads=_cpu_threads())
    _MODELS.clear()  # bellekte tek model tut
    _MODELS[name] = m
    return m


def transcribe(path: str, start: float, end: Optional[float], model: str = "small",
               language: Optional[str] = None,
               on_progress: Optional[Callable[[float], None]] = None,
               task: str = "transcribe",
               on_download: Optional[Callable[[], None]] = None) -> tuple[list[Word], str]:
    """Klip aralığının sesini yazıya çevirir. Zamanlar klip başına göredir.

    task="translate": konuşma hangi dilde olursa olsun İngilizce altyazı üretir (çevrimdışı).
    """
    import numpy as np

    # Sesi kendimiz ffmpeg ile 16 kHz mono float olarak çözüyoruz ve modele dizi
    # olarak veriyoruz. faster-whisper'ın kendi çözücüsü (PyAV) sürümler arasında
    # uyumsuzluk çıkarabiliyor; bu yol ona hiç bağımlı değil.
    args = [find_tool("ffmpeg"), "-v", "error", "-nostdin"]
    if start:
        args += ["-ss", f"{start:.3f}"]
    if end is not None:
        args += ["-to", f"{end:.3f}"]
    args += ["-i", path, "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"]
    proc = subprocess.run(args, capture_output=True, creationflags=_CREATE_FLAGS)
    if proc.returncode != 0:
        raise RuntimeError("Ses okunamadı: " + proc.stderr.decode("utf-8", "replace")[-500:])
    audio = np.frombuffer(proc.stdout, dtype=np.float32).copy()
    if audio.size == 0:
        return [], language or "tr"
    m = _load_model(model, on_download)
    # Hız ayarları: oyun sesi/müzik gibi konuşma olmayan yerlerde Whisper sıcaklığı artırarak
    # aynı parçayı 6 kez yeniden çözmeye çalışır; 3 denemeyle sınırlıyoruz. Önceki metne
    # bağlamamak da tekrar eden "hayalet" yazıları ve uzun takılmaları önler.
    kw = dict(language=language, word_timestamps=True, vad_filter=True,
              beam_size=1 if model in ("base", "tiny") else 5,
              temperature=(0.0, 0.4, 0.8), condition_on_previous_text=False,
              task="translate" if task == "translate" else "transcribe")
    try:
        segments, info = m.transcribe(audio, **kw)
        segments = list(_progress(segments, info, on_progress))
    except Exception:
        # Ekran kartı (CUDA) kütüphanesi eksik/bozuksa işlemciyle tekrar dene
        if not getattr(m, "_sc_gpu", False):
            raise
        from faster_whisper import WhisperModel
        m = WhisperModel(_ensure_local(model), device="cpu", compute_type="int8", cpu_threads=_cpu_threads())
        _MODELS.clear(); _MODELS[model] = m
        segments, info = m.transcribe(audio, **kw)
        segments = list(_progress(segments, info, on_progress))
    words: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            t = w.word.strip()
            if t:
                words.append(Word(float(w.start), float(w.end), t))
    return words, ("en" if task == "translate" else info.language)


def _progress(segments, info, on_progress):
    for seg in segments:
        if on_progress and info.duration:
            on_progress(min(1.0, seg.end / info.duration))
        yield seg


# --------------------------------------------------------------------------- SRT

_SRT_TIME = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def _srt_t(s: str) -> float:
    h, m, sec, ms = _SRT_TIME.search(s).groups()
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms.ljust(3, "0")[:3]) / 1000


def read_srt(path: str) -> list[Word]:
    """SRT satırlarını tek tek 'kelime grubu' olarak döndürür (vurgusuz)."""
    blocks = re.split(r"\n\s*\n", Path(path).read_text(encoding="utf-8-sig").strip())
    out: list[Word] = []
    for b in blocks:
        lines = [l for l in b.splitlines() if l.strip()]
        ti = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if ti is None:
            continue
        a, z = lines[ti].split("-->")
        out.append(Word(_srt_t(a), _srt_t(z), " ".join(lines[ti + 1:])))
    return out


def _fmt_srt(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(chunks: list[list[Word]], path: str) -> None:
    lines = []
    for i, ch in enumerate(chunks, 1):
        lines += [str(i), f"{_fmt_srt(ch[0].start)} --> {_fmt_srt(ch[-1].end)}",
                  " ".join(w.text for w in ch), ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- zamanı taşıma ve gruplama

def remap_words(words: list[Word], keeps: Optional[list[Segment]]) -> list[Word]:
    if not keeps:
        return words
    out = []
    for w in words:
        span = remap_span(w.start, w.end, keeps)
        if span:
            out.append(Word(span[0], span[1], w.text))
    return out


def chunk_words(words: list[Word], max_words: int, max_gap: float = 0.6) -> list[list[Word]]:
    chunks: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur and (len(cur) >= max_words or w.start - cur[-1].end > max_gap
                    or cur[-1].text[-1:] in ".!?"):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


# --------------------------------------------------------------------------- ASS

def _ass_color(hex_color: str, alpha: int = 0) -> str:
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _ass_t(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _upper(text: str, lang: Optional[str]) -> str:
    if lang in ("tr", "az"):
        text = text.replace("i", "İ").replace("ı", "I")
    return text.upper()


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


FONT_NAME = "Poppins"

STYLES = {
    # ad: (büyük harf, kenar kalınlığı, gölge, kutulu mu)
    "bold": (True, 6, 2, False),
    "clean": (False, 4, 1, False),
    "boxed": (True, 0, 0, True),
}


ANIMATIONS = ("none", "pop", "bounce", "karaoke", "fade", "slide")


def build_ass(chunks: list[list[Word]], cfg: dict, canvas: dict, tag: dict,
              duration: float, lang: Optional[str], word_level: bool,
              hook: Optional[dict] = None, watermark: str = "") -> str:
    W, H = int(canvas["width"]), int(canvas["height"])
    upper, outline, shadow, boxed = STYLES.get(cfg.get("style", "bold"), STYLES["bold"])
    size = int(cfg.get("font_size", 78))
    hl = _ass_color(cfg.get("highlight_color", "#C8F135"))
    white = _ass_color("#FFFFFF")
    if boxed:
        # BorderStyle 3'te kutunun rengi OutlineColour alanından gelir
        primary, oc, back, border_style, outline = (_ass_color("#111111"), _ass_color("#FFE14D"),
                                                    _ass_color("#000000", 0xFF), 3, 12)
        hl = _ass_color("#D9480F")
    else:
        primary, oc, back, border_style = white, _ass_color("#000000"), _ass_color("#000000", 0x80), 1

    tag_size = 54
    hook = hook or {}
    hook_style = hook.get("style", "box")  # box = beyaz kutu, siyah yazı; title = kutusuz kalın
    hook_size = int(hook.get("size", 72))
    hook_fg, hook_bg = hook.get("color", "#111111"), hook.get("background", "#FFFFFF")
    hook_pad = max(8, hook_size // 5)
    anim = cfg.get("animation", "none") if cfg.get("animation") in ANIMATIONS else "none"
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{FONT_NAME},{size},{primary},{primary},{oc},{back},-1,0,0,0,100,100,0,0,{border_style},{outline},{shadow},5,60,60,0,1
Style: Hook,{FONT_NAME},{hook_size},{_ass_color(hook_fg)},{_ass_color(hook_fg)},{_ass_color(hook_bg)},&H00000000,-1,0,0,0,100,100,0,0,3,{hook_pad},0,5,40,40,0,1
Style: Title,{FONT_NAME},{hook_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,10,6,5,40,40,0,1
Style: WM,{FONT_NAME},34,&H50FFFFFF,&H50FFFFFF,&H90000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,9,0,0,0,1
Style: Tag,{FONT_NAME},{tag_size},{_ass_color(tag.get('color', '#C8F135'))},&H000000FF,&H00110F0E,&H00000000,-1,0,0,0,100,100,0,0,3,14,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev: list[str] = []
    px, py = W // 2, int(H * float(cfg.get("position_y", 0.62)))
    pos = f"{{\\an5\\pos({px},{py})}}"

    def fmt(w: Word) -> str:
        return _esc(_upper(w.text, lang) if upper else w.text)

    dim = "&H66&"  # karaoke: henüz söylenmemiş kelimeler soluk

    def intro(first: bool) -> str:
        """Grubun ilk görünüşündeki giriş animasyonu (olay başına göre ms)."""
        if not first:
            return ""
        if anim == "pop":
            return "\\fscx70\\fscy70\\t(0,110,\\fscx108\\fscy108)\\t(110,180,\\fscx100\\fscy100)"
        if anim == "fade":
            return "\\fad(120,0)"
        if anim == "slide":
            return f"\\move({px},{py + 40},{px},{py},0,140)\\fad(90,0)"
        return ""

    for ch in chunks:
        if word_level:
            for i, w in enumerate(ch):
                s = w.start
                e = ch[i + 1].start if i + 1 < len(ch) else ch[-1].end
                parts = []
                for j, x in enumerate(ch):
                    t = fmt(x)
                    if j == i:
                        grow = ("\\fscx100\\fscy100\\t(0,80,\\fscx118\\fscy118)\\t(80,170,\\fscx108\\fscy108)"
                                if anim == "bounce" else "")
                        reset = "\\fscx100\\fscy100" if grow else ""
                        parts.append(f"{{\\c{hl}{grow}}}{t}{{\\c{primary}{reset}}}")
                    elif anim == "karaoke" and j > i:
                        parts.append(f"{{\\alpha{dim}}}{t}{{\\alpha&H00&}}")
                    else:
                        parts.append(t)
                p = pos if anim != "slide" or i else "{\\an5}"
                fx = intro(i == 0)
                head_tag = (p[:-1] + fx + "}") if fx else p
                ev.append(f"Dialogue: 1,{_ass_t(s)},{_ass_t(e)},Sub,,0,0,0,,{head_tag}{' '.join(parts)}")
        else:
            text = " ".join(fmt(x) for x in ch)
            p = pos if anim != "slide" else "{\\an5}"
            fx = intro(True)
            head_tag = (p[:-1] + fx + "}") if fx else p
            ev.append(f"Dialogue: 1,{_ass_t(ch[0].start)},{_ass_t(ch[-1].end)},Sub,,0,0,0,,{head_tag}{text}")

    if hook.get("enabled") and str(hook.get("text", "")).strip():
        hy = int(H * float(hook.get("y", 0.16)))
        hd = min(duration, float(hook.get("duration", 3.0))) if float(hook.get("duration", 3.0)) > 0 else duration
        lines = [l.strip() for l in str(hook["text"]).splitlines() if l.strip()][:3]
        txt = "\\N".join(_esc(_upper(l, lang) if hook.get("upper", True) else l) for l in lines)
        style = "Title" if hook_style == "title" else "Hook"
        a = "\\fscx60\\fscy60\\t(0,140,\\fscx106\\fscy106)\\t(140,220,\\fscx100\\fscy100)" if hook.get("animate", True) else ""
        out_fade = "\\fad(0,200)" if hd < duration - 0.05 else ""
        ev.append(f"Dialogue: 3,{_ass_t(0)},{_ass_t(hd)},{style},,0,0,0,,{{\\an5\\pos({W // 2},{hy}){a}{out_fade}}}{txt}")

    if watermark:
        ev.append(f"Dialogue: 4,{_ass_t(0)},{_ass_t(duration + 1)},WM,,0,0,0,,"
                  f"{{\\an9\\pos({W - 28},{int(H * 0.115)})}}{_esc(watermark)}")

    if tag.get("enabled") and tag.get("text"):
        ty = int(H * float(tag["y"]))
        ev.append(f"Dialogue: 2,{_ass_t(0)},{_ass_t(duration + 1)},Tag,,0,0,0,,"
                  f"{{\\an5\\pos({W // 2},{ty})}}{_esc(tag['text'])}")
    return head + "\n".join(ev) + "\n"
