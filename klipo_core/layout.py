"""Katmanlardan ffmpeg filter_complex grafiği üretir (9:16 tuval)."""

from __future__ import annotations


def _even(v: float) -> int:
    return max(2, int(round(v / 2.0)) * 2)


def _hex(color: str) -> str:
    return "0x" + color.lstrip("#")


def build_layout_graph(layers: list[dict], canvas: dict, fps: float,
                       in_label: str, out_label: str) -> list[str]:
    """[in_label] videosunu katmanlara bölüp tuvale yerleştirir, [out_label] verir."""
    W, H = int(canvas["width"]), int(canvas["height"])
    n = len(layers)
    lines: list[str] = []
    split_outs = "".join(f"[L{i}s]" for i in range(n))
    lines.append(f"[{in_label}]split={n}{split_outs}" if n > 1 else f"[{in_label}]null[L0s]")
    lines.append(f"color=c={_hex(canvas.get('background', '#000000'))}:s={W}x{H}:r={fps:.4f}[base]")

    prev = "base"
    for i, layer in enumerate(layers):
        src, dst = layer["src"], layer["dst"]
        dw, dh = _even(W * dst["w"]), _even(H * dst["h"])
        dx, dy = int(round(W * dst["x"])), int(round(H * dst["y"]))
        f: list[str] = []
        if (src["x"], src["y"], src["w"], src["h"]) != (0, 0, 1, 1):
            f.append(
                f"crop=w='trunc(iw*{src['w']:.5f}/2)*2':h='trunc(ih*{src['h']:.5f}/2)*2'"
                f":x='iw*{src['x']:.5f}':y='ih*{src['y']:.5f}'"
            )
        fit = layer.get("fit", "cover")
        blur = float(layer.get("blur", 0))
        if blur > 0:
            # Bulanıklaştırmayı küçük çözünürlükte yap: hem hızlı hem daha yumuşak
            sw, sh = _even(dw / 4), _even(dh / 4)
            f.append(f"scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh}")
            r = max(1, min(int(blur / 4), min(sw, sh) // 2 - 1))
            f.append(f"boxblur={r}:2")
            f.append(f"scale={dw}:{dh}")
        elif fit == "cover":
            f.append(f"scale={dw}:{dh}:force_original_aspect_ratio=increase,crop={dw}:{dh}")
        elif fit == "contain":
            f.append(f"scale={dw}:{dh}:force_original_aspect_ratio=decrease")
        else:
            f.append(f"scale={dw}:{dh}")
        dim = float(layer.get("dim", 0))
        if dim > 0:
            m = 1.0 - min(0.95, dim)
            f.append(f"colorchannelmixer=rr={m:.3f}:gg={m:.3f}:bb={m:.3f}")
        border = layer.get("border")
        bw = int(border.get("width", 0)) if border else 0
        if bw > 0:
            f.append(f"pad=w=iw+{2 * bw}:h=ih+{2 * bw}:x={bw}:y={bw}:color={_hex(border.get('color', '#FFFFFF'))}")
        f.append("setsar=1")
        lines.append(f"[L{i}s]" + ",".join(f) + f"[L{i}]")

        if fit == "contain" and blur <= 0:
            ox = f"{dx}+({dw}-overlay_w)/2"
            oy = f"{dy}+({dh}-overlay_h)/2"
        else:
            ox, oy = str(dx - bw), str(dy - bw)
        nxt = f"C{i}"
        enable = ""
        if layer.get("enable"):  # sadece belli zaman aralıklarında görünen katman (ör. zoom)
            expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in layer["enable"])
            enable = f":enable='{expr}'"
        lines.append(f"[{prev}][L{i}]overlay=x={ox}:y={oy}:shortest=1:eof_action=endall{enable}[{nxt}]")
        prev = nxt

    lines.append(f"[{prev}]format=yuv420p[{out_label}]")
    return lines
