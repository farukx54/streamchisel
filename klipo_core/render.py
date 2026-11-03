"""Bir projeyi baştan sona render eder.

Sıra: aralık → sessizlik + elle kesimler → renk → dikey düzen (+ zaman tabanlı zoom'lar)
→ logo → altyazı/etiket → ses karışımı (kaynak + müzik + efektler) → dışa aktar.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from . import silence as sil
from . import subtitles as subs
from .ffmpeg_tools import (detect_encoder, encoder_args, filter_script_args, find_tool, probe,
                           run_with_progress)
from .layout import build_layout_graph
from .project import load_project

EventCb = Optional[Callable[[dict], None]]


def _assets() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets"


def _fonts_dir() -> Path:
    return _assets() / "fonts"


def resolve_audio(path: str) -> str:
    """'sfx:whoosh' gibi hazır efekt adlarını dosya yoluna çevirir."""
    if path.startswith("sfx:"):
        f = _assets() / "sfx" / f"{path[4:]}.wav"
        if not f.is_file():
            raise FileNotFoundError(f"Ses efekti bulunamadı: {path[4:]}")
        return str(f)
    if not Path(path).is_file():
        raise FileNotFoundError(f"Ses dosyası bulunamadı: {path}")
    return path


def _keeps(proj: dict, src: str, info: dict, start: float, end: float, fps: float, emit) -> Optional[list]:
    """Videoda kalacak parçalar (klip başına göre). Hiç kesim yoksa None."""
    clip_len = end - start
    keeps = [(0.0, clip_len)]
    changed = False
    if proj["silence"]["enabled"] and info["has_audio"]:
        emit({"stage": "silence", "progress": 0.0})
        s = proj["silence"]
        silences = sil.detect_silences(src, s["threshold_db"], s["min_silence"], start, end)
        keeps = sil.keep_segments(silences, clip_len, s["padding"], fps)
        changed = True
    cuts = [(float(a) - start, float(b) - start) for a, b in proj.get("cuts") or []
            if float(b) > start and float(a) < end]
    if cuts:
        keeps = sil.subtract(keeps, cuts, fps)
        changed = True
    if not keeps:
        raise ValueError("Kesimlerden sonra videoda hiçbir şey kalmadı.")
    if changed:
        emit({"stage": "silence", "progress": 1.0, "removed_seconds": round(clip_len - sil.total(keeps), 2),
              "segments": len(keeps)})
    if len(keeps) == 1 and keeps[0][0] <= 1e-3 and keeps[0][1] >= clip_len - 1e-3:
        return None
    return keeps


def _out_spans(t0: float, t1: float, start: float, clip_len: float, keeps) -> list:
    """Kaynak zamanındaki bir aralığın çıktıda düştüğü yerler."""
    a, b = max(0.0, t0 - start), min(clip_len, t1 - start)
    if b <= a:
        return []
    return sil.remap_spans(a, b, keeps) if keeps else [(a, b)]


def render(project, on_event: EventCb = None) -> dict:
    emit = on_event or (lambda e: None)
    t0 = time.time()
    proj = load_project(project)
    src = str(Path(proj["input"]).resolve())
    out = str(Path(proj["output"]).resolve())
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    info = probe(src)
    rng = proj["range"] or {}
    start = max(0.0, float(rng.get("start") or 0.0))
    end = min(info["duration"], float(rng["end"])) if rng.get("end") is not None else info["duration"]
    if end <= start:
        raise ValueError("Klip aralığı geçersiz (bitiş başlangıçtan önce).")
    clip_len = end - start
    canvas = proj["canvas"]
    W, H = int(canvas["width"]), int(canvas["height"])
    still = bool(proj["export"].get("still"))  # kapak: tek kare JPG
    fps = float(canvas.get("fps") or min(60, max(24, round(info["fps"]))))

    # 1) Kalacak parçalar: sessizlik + elle kesimler
    keeps = _keeps(proj, src, info, start, end, fps, emit)
    out_len = sil.total(keeps) if keeps else clip_len

    with tempfile.TemporaryDirectory(prefix="streamchisel_") as td:
        # 2) Altyazı + yayıncı etiketi (tek ASS dosyası)
        sub_cfg, tag, hook = proj["subtitles"], proj["tag"], proj.get("hook") or {}
        hook_on = bool(hook.get("enabled") and str(hook.get("text", "")).strip())
        wm = str(proj.get("watermark") or "")
        ass_needed = sub_cfg["enabled"] or (tag["enabled"] and tag["text"]) or hook_on or bool(wm)
        srt_out = None
        if ass_needed:
            chunks, lang, word_level = [], sub_cfg.get("language"), False
            if sub_cfg["enabled"]:
                if sub_cfg.get("chunks"):
                    lang = sub_cfg.get("detected_language") or lang
                    for ch in sub_cfg["chunks"]:
                        ws = [subs.Word(float(w["start"]) - start, float(w["end"]) - start, str(w["text"]).strip())
                              for w in ch if str(w.get("text", "")).strip()]
                        ws = [w for w in ws if w.end > 0 and w.start < clip_len]
                        ws = subs.remap_words(ws, keeps)
                        if ws:
                            chunks.append(ws)
                    word_level = bool(sub_cfg.get("word_highlight", True))
                elif sub_cfg.get("srt_path"):
                    words = subs.read_srt(sub_cfg["srt_path"])
                    words = subs.remap_words(words, keeps)
                    chunks = [[w] for w in words]
                else:
                    emit({"stage": "transcribe", "progress": 0.0})
                    words, lang = subs.transcribe(
                        src, start, end, sub_cfg["model"], sub_cfg.get("language"),
                        on_progress=lambda p: emit({"stage": "transcribe", "progress": p}),
                        task="translate" if sub_cfg.get("translate") else "transcribe",
                        on_download=lambda: emit({"stage": "model", "progress": 0.0}))
                    words = subs.remap_words(words, keeps)
                    chunks = subs.chunk_words(words, int(sub_cfg.get("max_words", 3)))
                    word_level = bool(sub_cfg.get("word_highlight", True))
                srt_out = str(Path(out).with_suffix(".srt"))
                subs.write_srt(chunks, srt_out)
            ass = subs.build_ass(chunks, sub_cfg, canvas, tag, out_len, lang, word_level, hook, wm)
            Path(td, "subs.ass").write_text(ass, encoding="utf-8")
            shutil.copytree(_fonts_dir(), Path(td, "fonts"))

        # 3) Girdiler: 0 = kaynak, sonra logo, müzik, efektler
        extra_inputs: list[list[str]] = []

        def add_input(args: list[str]) -> int:
            extra_inputs.append(args)
            return len(extra_inputs)  # 0 kaynak olduğu için 1'den başlar

        # 4) Görüntü grafiği
        g: list[str] = [f"[0:v]setpts=PTS-STARTPTS,fps={fps:g}[v0]"]
        if keeps:
            g.append(f"[v0]select='{sil.select_expr(keeps)}',setpts=N/FRAME_RATE/TB[vc0]")
        else:
            g.append("[v0]null[vc0]")
        col = proj.get("color") or {}
        b_, c_, s_ = float(col.get("brightness", 1)), float(col.get("contrast", 1)), float(col.get("saturation", 1))
        if abs(b_ - 1) > 1e-3 or abs(c_ - 1) > 1e-3 or abs(s_ - 1) > 1e-3:
            g.append(f"[vc0]colorchannelmixer=rr={b_:.3f}:gg={b_:.3f}:bb={b_:.3f},"
                     f"eq=contrast={c_:.3f}:saturation={s_:.3f}[vc]")
        else:
            g.append("[vc0]null[vc]")

        layers = [dict(l) for l in proj["layers"]]
        for z in proj.get("zooms") or []:
            spans = _out_spans(float(z["start"]), float(z["end"]), start, clip_len, keeps)
            if not spans:
                continue
            layer = {"src": z["src"], "dst": z["dst"], "fit": "cover", "enable": spans}
            if z.get("border", True):
                layer["border"] = {"width": 6, "color": z.get("color", "#C8F135")}
            layers.append(layer)
        g += build_layout_graph(layers, canvas, fps, "vc", "vl")

        cur = "vl"
        logo = proj.get("logo")
        if logo and logo.get("path"):
            li = add_input(["-loop", "1", "-framerate", f"{fps:g}", "-i", str(logo["path"])])
            lw = max(2, int(round(W * float(logo.get("w", 0.3)) / 2)) * 2)
            lx, ly = int(round(W * float(logo.get("x", 0.05)))), int(round(H * float(logo.get("y", 0.03))))
            op = max(0.0, min(1.0, float(logo.get("opacity", 1.0))))
            chain = f"[{li}:v]format=rgba,scale={lw}:-2,colorchannelmixer=aa={op:.3f}"
            if logo.get("fade") and out_len > 2:
                chain += f",fade=t=in:st=0:d=0.6:alpha=1,fade=t=out:st={out_len - 0.6:.3f}:d=0.6:alpha=1"
            g.append(chain + "[logo]")
            g.append(f"[{cur}][logo]overlay=x={lx}:y={ly}:shortest=1:eof_action=endall[vlogo]")
            cur = "vlogo"
        if ass_needed:
            g.append(f"[{cur}]ass=subs.ass:fontsdir=fonts[vass]")
            cur = "vass"
        pb = proj.get("progress") or {}
        if pb.get("enabled") and out_len > 0.5:
            ph = max(4, int(round(H * float(pb.get("height", 0.006)))))
            py = 0 if pb.get("position") == "top" else H - ph
            g.append(f"[{cur}]drawbox=x=0:y={py}:w=iw:h={ph}:color=black@0.35:t=fill[vpbg]")
            g.append(f"color=c={pb.get('color', '#C8F135')}:s={W}x{ph}:r={fps:g}[pbar]")
            g.append(f"[vpbg][pbar]overlay=x='-w+w*t/{out_len:.3f}':y={py}:eval=frame:shortest=1[vpb]")
            cur = "vpb"
        g.append(f"[{cur}]null[vout]")

        # 5) Ses grafiği: kaynak (kesilmiş) + müzik + efektler
        audio = proj.get("audio") or {}
        AF = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
        mix: list[str] = []
        voice = None
        if info["has_audio"] and not still:
            n = int(round(48000 / fps))  # ses paketleri video karelerine hizalı → kayma olmaz
            a = f"[0:a]asetpts=PTS-STARTPTS,aresample=48000,asetnsamples=n={n}:p=0"
            if keeps:
                a += f",aselect='{sil.select_expr(keeps)}',asetpts=N/SR/TB"
            enh = audio.get("enhance") or {}
            if enh.get("denoise"):
                # Fan/klima uğultusu ve mikrofon cızırtısını azalt; konuşmayı bozmadan
                a += ",highpass=f=70,afftdn=nr=12:nf=-30:tn=1"
            a += f",aformat=sample_fmts=fltp:channel_layouts=stereo,volume={float(audio.get('source_volume', 1.0)):.3f}"
            g.append(a + "[voice]")
            voice = "voice"
        music = audio.get("music")
        sfx = [x for x in audio.get("sfx") or [] if x.get("path")]
        if still:
            music, sfx = None, []
        if not voice and (music or sfx):
            g.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{out_len:.3f}[voice]")
            voice = "voice"

        if music and music.get("path"):
            mi = add_input(["-stream_loop", "-1", "-ss", f"{float(music.get('offset', 0)):.3f}",
                            "-i", resolve_audio(music["path"])])
            fade_st = max(0.0, out_len - 1.5)
            g.append(f"[{mi}:a]{AF},atrim=0:{out_len:.3f},asetpts=PTS-STARTPTS,"
                     f"volume={float(music.get('volume', 0.25)):.3f},"
                     f"afade=t=in:st=0:d=0.4,afade=t=out:st={fade_st:.3f}:d=1.5[mus]")
            if music.get("duck", True) and info["has_audio"]:
                # Konuşma varken müziği otomatik kıs
                g.append("[voice]asplit=2[voice_m][voice_sc]")
                g.append("[mus][voice_sc]sidechaincompress=threshold=0.02:ratio=8:attack=15:release=350[musd]")
                mix += ["voice_m", "musd"]
            else:
                mix += [voice, "mus"]
        elif voice:
            mix.append(voice)

        for k, fx in enumerate(sfx):
            t_out = sil.remap_time(float(fx["time"]) - start, keeps) if keeps else float(fx["time"]) - start
            if t_out is None or t_out < 0 or t_out >= out_len:
                continue  # efekt kesilen bir yere düşüyor
            fi = add_input(["-i", resolve_audio(fx["path"])])
            ms = int(round(t_out * 1000))
            g.append(f"[{fi}:a]{AF},volume={float(fx.get('volume', 0.8)):.3f},adelay={ms}|{ms}[fx{k}]")
            mix.append(f"fx{k}")

        has_aout = bool(mix) and not still
        loud = ",loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000" if (audio.get("enhance") or {}).get("normalize") else ""
        if not has_aout:
            pass
        elif len(mix) == 1:
            g.append(f"[{mix[0]}]anull{loud}[aout]")
        else:
            ins = "".join(f"[{m}]" for m in mix)
            g.append(f"{ins}amix=inputs={len(mix)}:normalize=0:duration=first:dropout_transition=0,"
                     f"alimiter=limit=0.95{loud}[aout]")
        Path(td, "graph.txt").write_text(";\n".join(g), encoding="utf-8")

        # 6) Dışa aktar
        enc = proj["export"]["encoder"]
        if enc == "auto" and not still:
            enc = detect_encoder()
        args = [find_tool("ffmpeg"), "-y"]
        if start:
            args += ["-ss", f"{start:.3f}"]
        if end < info["duration"]:
            args += ["-to", f"{end:.3f}"]
        args += ["-i", src]
        for ex in extra_inputs:
            args += ex
        args += filter_script_args("graph.txt") + ["-map", "[vout]"]
        if still:
            args += ["-frames:v", "1", "-q:v", "2", "-update", "1", out]
            run_with_progress(args, 0.1, lambda p: None, cwd=td)
            emit({"stage": "done", "progress": 1.0, "output": out})
            return {"output": out}
        if has_aout:
            args += ["-map", "[aout]", "-c:a", "aac", "-b:a", proj["export"]["audio_bitrate"]]
        args += encoder_args(enc, proj["export"]["quality"])
        args += ["-r", f"{fps:g}", "-t", f"{out_len:.3f}", "-movflags", "+faststart", out]

        emit({"stage": "render", "progress": 0.0, "encoder": enc})
        run_with_progress(args, out_len, lambda p: emit({"stage": "render", "progress": p}), cwd=td)

    result = {"output": out, "srt": srt_out, "duration": round(out_len, 2),
              "source_duration": round(clip_len, 2), "encoder": enc,
              "elapsed": round(time.time() - t0, 2)}
    emit({"stage": "done", "progress": 1.0, **result})
    return result


# --------------------------------------------------------------------------- kapak (thumbnail)

def best_frame_time(path: str, start: float, end: float, samples: int = 10) -> float:
    """Aralıktaki en net (bulanık olmayan) kareyi seçer; yüz görünen karelere öncelik verir."""
    import cv2

    from .detect import _detector, _frame

    try:
        det = _detector()
    except Exception:
        det = None
    best, best_t = -1.0, start + (end - start) * 0.3
    for i in range(samples):
        t = start + (end - start) * (i + 0.5) / samples
        img = _frame(path, t, width=640)
        if img is None:
            continue
        sharp = float(cv2.Laplacian(img, cv2.CV_64F).var())
        bright = float(img.mean())
        score = sharp * (0.4 if bright < 35 else 1.0)  # çok karanlık kareyi seçme
        if det is not None and len(det.detectMultiScale(img, 1.1, 6, minSize=(30, 30))):
            score *= 1.6
        if score > best:
            best, best_t = score, t
    return best_t


def render_thumbnail(project, time_s: Optional[float] = None, title: str = "",
                     output: Optional[str] = None, style: str = "title",
                     on_event: EventCb = None) -> dict:
    """Projedeki düzenle tek kare kapak üretir (JPG), istenirse büyük başlık yazısıyla."""
    import copy

    base = load_project(project)
    info = probe(str(Path(base["input"]).resolve()))
    rng = base["range"] or {}
    a = float(rng.get("start") or 0.0)
    b = float(rng.get("end") or info["duration"])
    t = float(time_s) if time_s is not None else best_frame_time(base["input"], a, b)
    t = max(0.0, min(info["duration"] - 0.2, t))
    p = copy.deepcopy(base)
    p["layers"] = base["layers"]
    p["range"] = {"start": t, "end": min(info["duration"], t + 0.5)}
    p["silence"]["enabled"] = False
    p["cuts"] = []
    p["subtitles"] = dict(p["subtitles"], enabled=False)
    p["audio"] = {"source_volume": 0, "music": None, "sfx": []}
    p["progress"] = {"enabled": False}
    p["zooms"] = [z for z in p.get("zooms") or [] if float(z["start"]) <= t < float(z["end"])]
    if p.get("logo"):
        p["logo"] = dict(p["logo"], fade=False)
    p["hook"] = {"enabled": bool(title.strip()), "text": title, "style": style,
                 "size": 150 if style == "title" else 104, "y": 0.5 if style == "title" else 0.2,
                 "duration": 0, "animate": False, "upper": True}
    p["export"] = dict(p["export"], still=True)
    p["output"] = output or str(Path(base["output"]).with_suffix("")) + "_kapak.jpg"
    res = render(p, on_event)
    res["time"] = round(t, 2)
    return res
