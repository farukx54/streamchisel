"""Proje dosyası (JSON) ve hazır düzen şablonları.

Arayüz bu JSON'u üretir, motor da onu okuyup render eder. Bütün koordinatlar
0..1 arasıdır, yani kaynak videonun ya da çıktının oranı olarak tutulur. Bu
sayede 720p veya 1440p kaynakta aynı proje çalışır.

Katman (layer):
  src:  kaynaktan kesilecek bölge   {"x","y","w","h"}  (0..1, kaynak videoya göre)
  dst:  çıktıda konulacağı yer      {"x","y","w","h"}  (0..1, 9:16 tuvale göre)
  fit:  "cover" (doldur, taşanı kes) | "contain" (sığdır) | "stretch"
  blur: 0 = yok; büyüdükçe daha bulanık
  dim:  0..1 karartma (bulanık arka plan için)
  border: {"width": px, "color": "#RRGGBB"}  (isteğe bağlı çerçeve)
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

FULL = {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}

DEFAULTS: dict[str, Any] = {
    "input": None,
    "output": None,
    "range": None,  # {"start": sn, "end": sn}  ya da null = tüm video
    "canvas": {"width": 1080, "height": 1920, "fps": None, "background": "#000000"},
    "layout": {"preset": "stack", "camera": None, "game": None, "focus": None,
               "camera_ratio": 0.35, "focus_dst": None,
               "game_fit": "cover",  # cover = alanı doldur (kırp), contain = sığdır + bulanık zemin
               "blur": 40, "dim": 0.35},
    "layers": None,  # doluysa preset yerine doğrudan bunlar kullanılır
    "silence": {"enabled": False, "threshold_db": -38.0, "min_silence": 0.8, "padding": 0.15},
    "subtitles": {"enabled": False, "model": "small", "language": None, "style": "bold",
                  "word_highlight": True, "position_y": 0.62, "font_size": 84,
                  "highlight_color": "#C8F135", "max_words": 3, "srt_path": None},
    "tag": {"enabled": False, "text": "", "y": None, "color": "#C8F135"},
    "export": {"encoder": "auto", "quality": "high", "audio_bitrate": "192k"},
    # Kaynak zamanına göre elle kesilen (atılan) parçalar: [[başlangıç, bitiş], ...]
    "cuts": [],
    # Zaman tabanlı yakınlaştırmalar: {"start","end" (kaynak sn), "src", "dst", "border"}
    "zooms": [],
    "color": {"brightness": 1.0, "contrast": 1.0, "saturation": 1.0},
    # Logo: {"path": png, "x","y","w" (0..1 tuvale göre), "opacity", "fade"}
    "logo": None,
    "audio": {"source_volume": 1.0, "music": None, "sfx": [],
              "enhance": {"denoise": False, "normalize": False}},
    # Kanca yazısı: ilk saniyelerde görünen büyük başlık
    "hook": {"enabled": False, "text": "", "duration": 3.0, "y": 0.16, "style": "box",
             "size": 72, "color": "#111111", "background": "#FFFFFF", "animate": True, "upper": True},
    # Videonun ne kadarının izlendiğini gösteren ince çubuk
    "progress": {"enabled": False, "color": "#C8F135", "position": "bottom", "height": 0.006},
    "watermark": "",  # ücretsiz sürümde köşedeki yazı
}

# Çıktı biçimleri: platform → tuval boyutu
FORMATS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350), "16:9": (1920, 1080)}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_project(path_or_dict: str | Path | dict) -> dict:
    data = path_or_dict if isinstance(path_or_dict, dict) else json.loads(
        Path(path_or_dict).read_text(encoding="utf-8"))
    proj = _merge(DEFAULTS, data)
    fmt = proj.get("format")
    if fmt in FORMATS:
        proj["canvas"]["width"], proj["canvas"]["height"] = FORMATS[fmt]
    if not proj["input"]:
        raise ValueError("Projede 'input' (kaynak video) yok.")
    if not proj["output"]:
        proj["output"] = str(Path(proj["input"]).with_name(Path(proj["input"]).stem + "_dikey.mp4"))
    if not proj["layers"]:
        proj["layers"] = build_preset_layers(proj["layout"])
    for i, layer in enumerate(proj["layers"]):
        for key in ("src", "dst"):
            r = layer.setdefault(key, dict(FULL))
            for c in ("x", "y", "w", "h"):
                if not 0.0 <= float(r[c]) <= 1.0:
                    raise ValueError(f"Katman {i} {key}.{c} 0..1 arasında olmalı.")
            if r["w"] <= 0 or r["h"] <= 0:
                raise ValueError(f"Katman {i} {key} genişlik/yükseklik 0 olamaz.")
        layer.setdefault("fit", "cover")
        layer.setdefault("blur", 0)
        layer.setdefault("dim", 0)
    if proj["tag"]["enabled"] and proj["tag"]["y"] is None:
        proj["tag"]["y"] = default_tag_y(proj["layout"])
    return proj


def default_tag_y(layout: dict) -> float:
    """Yayıncı etiketini kamera ile oyunun birleştiği çizgiye koy."""
    if layout.get("preset") in ("stack", "focus"):
        return float(layout.get("camera_ratio", 0.35))
    return 0.12


def build_preset_layers(layout: dict) -> list[dict]:
    preset = layout.get("preset", "stack")
    cam = layout.get("camera") or {"x": 0.0, "y": 0.0, "w": 0.25, "h": 0.30}
    game = layout.get("game") or {"x": 0.21875, "y": 0.0, "w": 0.5625, "h": 1.0}
    ratio = float(layout.get("camera_ratio", 0.35))

    fit = layout.get("game_fit", "cover")
    blur = float(layout.get("blur", 40))
    dim = float(layout.get("dim", 0.35))

    def game_layers(dst: dict) -> list[dict]:
        if fit == "contain":  # oyunun tamamı görünsün, boşluk bulanık oyunla dolsun
            return [{"src": game, "dst": dst, "fit": "cover", "blur": blur, "dim": dim},
                    {"src": game, "dst": dst, "fit": "contain"}]
        return [{"src": game, "dst": dst, "fit": "cover"}]

    top = {"x": 0, "y": 0, "w": 1, "h": ratio}
    bottom = {"x": 0, "y": ratio, "w": 1, "h": 1 - ratio}
    if preset == "stack":  # kamera üstte, oyun altta
        return [{"src": cam, "dst": top, "fit": "cover"}] + game_layers(bottom)
    if preset == "blur":  # bulanık arka plan + ortada yatay video
        return [
            {"src": FULL, "dst": FULL, "fit": "cover", "blur": blur, "dim": dim},
            {"src": FULL, "dst": FULL, "fit": "contain"},
        ]
    if preset == "full":  # tam ekran oyun
        return game_layers(dict(FULL))
    if preset == "focus":  # kamera üstte, oyun altta + odak bölgesi (ör. minimap)
        focus = layout.get("focus") or {"x": 0.84, "y": 0.70, "w": 0.16, "h": 0.30}
        fdst = layout.get("focus_dst") or {"x": 0.60, "y": 0.70, "w": 0.36, "h": 0.20}
        return ([{"src": cam, "dst": top, "fit": "cover"}] + game_layers(bottom)
                + [{"src": focus, "dst": fdst, "fit": "cover", "border": {"width": 6, "color": "#FF8A3D"}}])
    raise ValueError(f"Bilinmeyen düzen şablonu: {preset}")
