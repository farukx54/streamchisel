"""Altyazı metninden başlık ve hashtag önerisi. Çevrimdışı, basit anahtar kelime çıkarımı."""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional

STOP_TR = set("""ve ile de da ki bu şu o bir iki ben sen biz siz onlar ama fakat çünkü gibi için kadar daha çok en
ne neden nasıl niye mi mı mu mü ya yani işte şey şimdi sonra önce hiç her hep artık bile diye olan oldu olur
var yok değil evet hayır tamam abi kanka lan ya yaa ha hı he eee ıı aa benim senin onun bunu şunu bana sana ona
bize size burada orada şurada böyle şöyle öyle biraz bi bişey birşey zaten aslında galiba belki hadi gel git
bak dur yap yaptı yapıyor yapacak olarak olsun etmek etti ediyor geldi gitti dedi diyor diyorum mısın misin
musun müsün miyim mıyım tane kez kere çünkü acaba bizi sizi onu biri bugün beni seni böyle oldu""".split())
STOP_EN = set("""the a an and or but so to of in on at for with is are was were be been it this that these those
i you he she we they me him her us them my your his our their what why how when where who which not no yes
just like really very do does did done have has had get got go going gonna wanna yeah okay ok oh uh um
can could would should will there here then than too also about from out up down all some any one two""".split())

PLATFORM_TAGS = {
    "genel": ["#keşfet", "#reels", "#shorts", "#fyp"],
    "kick": ["#kick", "#kickstreamer", "#kicktürkiye"],
    "twitch": ["#twitch", "#twitchtr", "#twitchclips"],
    "youtube": ["#youtubeshorts", "#shorts"],
    "tiktok": ["#tiktok", "#keşfetteyiz", "#fyp"],
}

TITLES_TR = [
    "{K} anı… sonunu bekle 😱", "Yayında {k} olayı 🔥", "Bu {k} kısmı efsane", "Kimse {k} beklemiyordu 😳",
    "{K} yüzünden yayın karıştı", "En iyi {k} anı", "{K}?! Sonuna kadar izle", "Yayının en çılgın anı: {k}",
]
TITLES_EN = [
    "Wait for the {k} part 😱", "Nobody expected {k} 😳", "The {k} moment 🔥", "{K} went crazy on stream",
    "Best {k} clip ever", "This {k} is insane",
]


def keywords(text: str, lang: Optional[str] = None, n: int = 8) -> list[str]:
    stop = STOP_TR | STOP_EN
    words = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]{3,}", text)
    low = [w.lower().replace("İ", "i") for w in words]
    cnt = Counter(w for w in low if w not in stop and not w.isdigit())
    # Büyük harfle başlayan özel isimlere küçük bir artı
    for w in words:
        if w[:1].isupper() and w.lower() in cnt:
            cnt[w.lower()] += 0.5
    return [w for w, _ in cnt.most_common(n)]


def _tag(w: str) -> str:
    return "#" + re.sub(r"[^0-9a-zçğıöşü]", "", w.lower())


def suggest(text: str, lang: Optional[str] = None, platform: str = "genel",
            channel: str = "", game: str = "") -> dict:
    kws = keywords(text, lang)
    en = (lang or "").startswith("en")
    tmpl = TITLES_EN if en else TITLES_TR
    pick = kws[:3] or ([game] if game else ["yayın" if not en else "stream"])
    titles = []
    for i, t in enumerate(tmpl):
        k = pick[i % len(pick)]
        titles.append(t.format(k=k, K=k[:1].upper() + k[1:]))
    tags = [_tag(k) for k in kws[:5]]
    if game:
        tags.insert(0, _tag(game))
    if channel:
        tags.insert(0, _tag(channel.split("/")[-1]))
    tags += PLATFORM_TAGS.get(platform, []) + PLATFORM_TAGS["genel"]
    seen, uniq = set(), []
    for t in tags:
        if len(t) > 2 and t not in seen:
            seen.add(t); uniq.append(t)
    return {"keywords": kws, "titles": titles[:6], "hashtags": uniq[:15]}
