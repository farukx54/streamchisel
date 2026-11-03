import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klipo_core.project import load_project
from klipo_core.silence import keep_segments, remap_span, remap_time, total
from klipo_core.subtitles import Word, _upper, chunk_words, remap_words


def test_keep_segments_and_remap():
    keeps = keep_segments([(2.0, 4.0), (8.0, float("inf"))], duration=10.0, padding=0.1, fps=30)
    assert keeps[0][0] == 0.0 and abs(keeps[0][1] - 2.1) < 0.02
    assert abs(keeps[1][0] - 3.9) < 0.02 and abs(keeps[1][1] - 8.1) < 0.02
    assert remap_time(1.0, keeps) == 1.0
    assert remap_time(3.0, keeps) is None
    assert abs(remap_time(5.0, keeps) - (keeps[0][1] + 5.0 - keeps[1][0])) < 1e-9
    assert abs(total(keeps) - 6.3) < 0.05
    assert remap_span(2.0, 4.5, keeps) is not None


def test_words_remap_and_chunk():
    keeps = [(0.0, 2.0), (5.0, 8.0)]
    words = [Word(0.5, 0.9, "a"), Word(3.0, 3.5, "kesildi"), Word(5.5, 6.0, "b."), Word(6.1, 6.5, "c")]
    out = remap_words(words, keeps)
    assert [w.text for w in out] == ["a", "b.", "c"]
    assert abs(out[1].start - 2.5) < 1e-9
    chunks = chunk_words(out, max_words=3)
    assert [[w.text for w in c] for c in chunks] == [["a"], ["b."], ["c"]]


def test_turkish_upper():
    assert _upper("işte bıçak", "tr") == "İŞTE BIÇAK"


def test_presets_build():
    for preset in ("stack", "blur", "full", "focus"):
        p = load_project({"input": "x.mp4", "layout": {"preset": preset}})
        assert p["layers"] and p["output"].endswith("x_dikey.mp4")


def test_game_fit_contain_adds_blur_layer():
    p = load_project({"input": "x.mp4", "layout": {"preset": "stack", "game_fit": "contain"}})
    fits = [l["fit"] for l in p["layers"]]
    assert fits == ["cover", "cover", "contain"] and p["layers"][1].get("blur")


def test_manual_cuts_and_spans():
    from klipo_core.silence import remap_spans, subtract
    keeps = subtract([(0.0, 10.0)], [(2.0, 4.0), (6.0, 7.0)], fps=30)
    assert [(round(a, 2), round(b, 2)) for a, b in keeps] == [(0.0, 2.0), (4.0, 6.0), (7.0, 10.0)]
    # 1.5–5 aralığı kesimden geçer: çıktıda iki parçaya bölünür
    spans = remap_spans(1.5, 5.0, keeps)
    assert [(round(a, 2), round(b, 2)) for a, b in spans] == [(1.5, 2.0), (2.0, 3.0)]


def test_hook_and_animation_ass():
    from klipo_core.subtitles import Word, build_ass
    ch = [[Word(0, 0.4, "a"), Word(0.4, 0.9, "b")]]
    ass = build_ass(ch, {"animation": "karaoke"}, {"width": 1080, "height": 1920}, {}, 5, "tr", True,
                    {"enabled": True, "text": "izle\nsonuna kadar", "duration": 2})
    assert "\\alpha&H66&" in ass and ",Hook,," in ass and "SONUNA KADAR" in ass


def test_formats_and_suggest():
    from klipo_core.suggest import suggest
    p = load_project({"input": "x.mp4", "format": "1:1"})
    assert (p["canvas"]["width"], p["canvas"]["height"]) == (1080, 1080)
    r = suggest("boss boss çok zor oha", "tr", "kick")
    assert r["keywords"][0] == "boss" and "#kick" in r["hashtags"]
