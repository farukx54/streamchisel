"""Komut satırı: python -m klipo_core <komut> ...

Arayüz (Tauri) bu programı arka planda çalıştırır ve --json ile her satırda bir
olay (ilerleme, hata, sonuç) okur.
"""

from __future__ import annotations

import argparse
import json
import sys


def _rect(s: str) -> dict:
    x, y, w, h = (float(v) for v in s.split(","))
    return {"x": x, "y": y, "w": w, "h": h}


def _printer(as_json: bool):
    last = {"stage": None, "pct": -1}

    def emit(ev: dict) -> None:
        if as_json:
            print(json.dumps(ev, ensure_ascii=False), flush=True)
            return
        pct = int(ev.get("progress", 0) * 100)
        if ev["stage"] != last["stage"] or pct >= last["pct"] + 5 or ev["stage"] == "done":
            extra = {k: v for k, v in ev.items() if k not in ("stage", "progress")}
            print(f"[{ev['stage']:<10}] %{pct:>3} {extra if extra else ''}", flush=True)
            last.update(stage=ev["stage"], pct=pct)

    return emit


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="streamchisel", description="Yayın kaydını dikey kısa videoya çevirir.")
    p.add_argument("--json", action="store_true", help="Olayları JSON satırları olarak yaz (arayüz için)")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="Proje JSON dosyasını render et")
    r.add_argument("project")

    q = sub.add_parser("quick", help="Proje dosyası olmadan hızlı render")
    q.add_argument("input")
    q.add_argument("-o", "--output")
    q.add_argument("--preset", default="stack", choices=["stack", "blur", "full", "focus"])
    q.add_argument("--camera", type=_rect, help="x,y,w,h (0..1) kamera bölgesi")
    q.add_argument("--game", type=_rect, help="x,y,w,h (0..1) oyun bölgesi")
    q.add_argument("--focus", type=_rect, help="x,y,w,h (0..1) odak bölgesi")
    q.add_argument("--camera-ratio", type=float, default=0.35)
    q.add_argument("--start", type=float)
    q.add_argument("--end", type=float)
    q.add_argument("--cut-silence", action="store_true")
    q.add_argument("--silence-db", type=float, default=-38)
    q.add_argument("--subtitles", action="store_true")
    q.add_argument("--srt", help="Hazır SRT dosyası (otomatik yazıya çevirme yerine)")
    q.add_argument("--lang", help="Konuşma dili (tr, en ...); boşsa otomatik")
    q.add_argument("--model", default="small", help="tiny / base / small / medium / large-v3")
    q.add_argument("--style", default="bold", choices=["bold", "clean", "boxed"])
    q.add_argument("--tag", help="Yayıncı etiketi, ör. kick/kanaladi")
    q.add_argument("--quality", default="high", choices=["high", "balanced", "small"])
    q.add_argument("--encoder", default="auto")

    d = sub.add_parser("download", help="Linkten video indir")
    d.add_argument("url")
    d.add_argument("--out", default=".")
    d.add_argument("--quality", default="best", choices=["best", "1080", "720", "480"])

    i = sub.add_parser("info", help="Link hakkında bilgi al (indirmeden)")
    i.add_argument("url")

    sub.add_parser("encoders", help="Kullanılacak video kodlayıcıyı göster")

    a = p.parse_args(argv)
    emit = _printer(a.json)
    try:
        if a.cmd == "render":
            from .render import render
            render(a.project, emit)
        elif a.cmd == "quick":
            from .render import render
            proj = {
                "input": a.input, "output": a.output,
                "range": {"start": a.start, "end": a.end} if (a.start or a.end) else None,
                "layout": {"preset": a.preset, "camera": a.camera, "game": a.game,
                           "focus": a.focus, "camera_ratio": a.camera_ratio},
                "silence": {"enabled": a.cut_silence, "threshold_db": a.silence_db},
                "subtitles": {"enabled": a.subtitles or bool(a.srt), "srt_path": a.srt,
                              "language": a.lang, "model": a.model, "style": a.style},
                "tag": {"enabled": bool(a.tag), "text": a.tag or ""},
                "export": {"quality": a.quality, "encoder": a.encoder},
            }
            render(proj, emit)
        elif a.cmd == "download":
            from .download import download
            path = download(a.url, a.out, a.quality, emit)
            emit({"stage": "done", "progress": 1.0, "output": path})
        elif a.cmd == "info":
            from .download import probe_url
            emit({"stage": "info", "progress": 1.0, **probe_url(a.url)})
        elif a.cmd == "encoders":
            from .ffmpeg_tools import detect_encoder
            emit({"stage": "encoders", "progress": 1.0, "encoder": detect_encoder()})
    except Exception as e:  # arayüze okunur bir hata gönder
        emit({"stage": "error", "progress": 0.0, "message": str(e)})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
