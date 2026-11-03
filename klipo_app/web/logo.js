// Streamchisel logo stüdyosu: şablondan logo üretme, kendi logonu yükleme,
// renklendirme (SVG renk eşleme / PNG boyama, renk değiştirme, ton kaydırma),
// arka plan silme ve efektler (kontur, gölge, parıltı). Hepsi tarayıcıda, çevrimdışı.
"use strict";

const Logo = (() => {
  const PALETTES = [
    ["Fosfor", "#C8F135", "#0E0F11", "#FFFFFF"], ["Mor neon", "#B26BFF", "#14081F", "#F2E8FF"],
    ["Ateş", "#FF5A1F", "#1A0D08", "#FFD84D"], ["Buz", "#3FD0FF", "#07141C", "#E9FBFF"],
    ["Kırmızı", "#FF2E4D", "#120709", "#FFFFFF"], ["Altın", "#F5C542", "#141108", "#FFFFFF"],
    ["Pembe", "#FF4FB3", "#1A0714", "#FFFFFF"], ["Klasik", "#FFFFFF", "#111111", "#FF3B3B"],
  ];
  const ICONS = {
    bolt: '<path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z"/>',
    crown: '<path d="M3 18h18l-1.6-10-4.9 4L12 5l-2.5 7-4.9-4L3 18z"/><rect x="3" y="19.5" width="18" height="2.2" rx="1"/>',
    flame: '<path d="M12 2c.6 3.6 5.5 5.4 5.5 11a5.5 5.5 0 0 1-11 0c0-2.8 1.6-4.3 2.4-6.6.9 1.3 1.8 2.2 2.8 2.6.3-2.4-.1-4.6.3-7z"/>',
    pad: '<path d="M7 7h10a5 5 0 0 1 4.6 7l-1.1 2.5a2.4 2.4 0 0 1-4 .6L14.4 15H9.6l-2.1 2.1a2.4 2.4 0 0 1-4-.6L2.4 14A5 5 0 0 1 7 7z"/>',
    star: '<path d="M12 2l3 6.6 7.2.8-5.4 4.9 1.5 7.1L12 17.8l-6.3 3.6 1.5-7.1L1.8 9.4 9 8.6 12 2z"/>',
    aim: '<circle cx="12" cy="12" r="8" fill="none" stroke-width="2.6"/><circle cx="12" cy="12" r="2.6"/><rect x="11" y="1" width="2" height="6" rx="1"/><rect x="11" y="17" width="2" height="6" rx="1"/><rect x="1" y="11" width="6" height="2" rx="1"/><rect x="17" y="11" width="6" height="2" rx="1"/>',
  };
  const STYLES = ["Rozet", "Kalkan", "Neon", "Monogram", "E-spor", "Piksel", "Yığılı", "Yayın etiketi"];

  const mctx = document.createElement("canvas").getContext("2d");
  const tw = (text, font) => { mctx.font = font; return mctx.measureText(text).width; };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const icon = (id, x, y, s, fill) => `<g transform="translate(${x} ${y}) scale(${s / 24})" fill="${fill}" stroke="${fill}">${ICONS[id] || ICONS.bolt}</g>`;
  const initials = (n) => {
    const w = n.trim().split(/\s+/).filter(Boolean);
    if (w.length > 1) return (w[0][0] + w[1][0]).toLocaleUpperCase("tr-TR");
    const caps = n.match(/[A-ZÇĞİÖŞÜ0-9]/g) || [];
    return (caps.length >= 2 ? caps[0] + caps[1] : n.slice(0, 2)).toLocaleUpperCase("tr-TR");
  };
  const platTxt = (p) => ({ kick: "kick.com/", twitch: "twitch.tv/", yt: "youtube.com/@", none: "" })[p] ?? "";

  // ---- 8 şablon (önizleme sayfasındakiyle aynı)
  function variants(g) {
    const [, A, D, L] = PALETTES[g.pal] || PALETTES[0];
    const N = (g.name || "").trim() || "Kanal", UP = N.toLocaleUpperCase("tr-TR"), ic = g.icon || "bolt";
    const out = [];
    { const w = Math.max(160, tw(N, "700 44px Poppins") + 120);
      out.push({ vb: [w, 100], svg: `<rect x="2" y="12" width="${w - 4}" height="76" rx="20" fill="${D}" stroke="${A}" stroke-width="4"/><rect x="14" y="24" width="52" height="52" rx="14" fill="${A}"/>${icon(ic, 26, 36, 28, D)}<text x="82" y="64" font-family="Poppins" font-weight="700" font-size="44" fill="${L}">${esc(N)}</text>` }); }
    { const w = Math.max(220, tw(UP, '400 46px "Russo One"') + 40), cx = w / 2;
      out.push({ vb: [w, 230], svg: `<path d="M${cx} 8 L${cx + 70} 30 V82 C${cx + 70} 122 ${cx + 40} 146 ${cx} 162 C${cx - 40} 146 ${cx - 70} 122 ${cx - 70} 82 V30 Z" fill="${D}" stroke="${A}" stroke-width="6"/><path d="M${cx} 22 L${cx + 56} 40 V82 C${cx + 56} 114 ${cx + 32} 134 ${cx} 147 Z" fill="${A}" opacity=".18"/><text x="${cx}" y="110" text-anchor="middle" font-family="Russo One" font-size="56" fill="${A}">${esc(initials(N))}</text><text x="${cx}" y="214" text-anchor="middle" font-family="Russo One" font-size="46" fill="${L}">${esc(UP)}</text>` }); }
    { const w = Math.max(200, tw(UP, "800 64px Orbitron") + 60);
      out.push({ vb: [w, 130], svg: `<defs><filter id="g3" x="-30%" y="-60%" width="160%" height="220%"><feGaussianBlur stdDeviation="7" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs><text x="${w / 2}" y="86" text-anchor="middle" font-family="Orbitron, Poppins" font-weight="800" font-size="64" fill="none" stroke="${A}" stroke-width="3" filter="url(#g3)">${esc(UP)}</text><text x="${w / 2}" y="86" text-anchor="middle" font-family="Orbitron, Poppins" font-weight="800" font-size="64" fill="${L}" opacity=".9">${esc(UP)}</text>` }); }
    out.push({ vb: [200, 200], svg: `<circle cx="100" cy="100" r="92" fill="${A}"/><circle cx="100" cy="100" r="78" fill="none" stroke="${D}" stroke-width="4" stroke-dasharray="4 10"/><text x="100" y="124" text-anchor="middle" font-family="Bungee" font-size="70" fill="${D}">${esc(initials(N))}</text>` });
    { const w = Math.max(220, tw(UP, '400 84px "Bebas Neue"') * 1.05 + 70);
      out.push({ vb: [w, 140], svg: `<g transform="skewX(-12) translate(22 0)"><text x="${w / 2}" y="92" text-anchor="middle" font-family="Bebas Neue" font-size="84" fill="${L}" stroke="${D}" stroke-width="10" paint-order="stroke">${esc(UP)}</text><rect x="${w / 2 - 70}" y="104" width="140" height="10" fill="${A}"/><rect x="${w / 2 + 78}" y="104" width="22" height="10" fill="${A}" opacity=".5"/></g>` }); }
    { const w = Math.max(200, tw(UP, '400 34px "Press Start 2P"') + 70);
      out.push({ vb: [w, 120], svg: `<rect x="8" y="16" width="${w - 16}" height="88" fill="${D}"/><path d="M8 16h${w - 16}v88H8z" fill="none" stroke="${A}" stroke-width="8" stroke-dasharray="16 6"/><text x="${w / 2}" y="76" text-anchor="middle" font-family="Press Start 2P" font-size="34" fill="${A}">${esc(UP)}</text>` }); }
    { const half = Math.ceil(UP.length / 2), a = UP.slice(0, half), b = UP.slice(half), w = Math.max(200, tw(UP, "700 58px Rajdhani") + 50);
      out.push({ vb: [w, 190], svg: `${icon(ic, w / 2 - 34, 6, 68, A)}<text x="${w / 2}" y="150" text-anchor="middle" font-family="Rajdhani" font-weight="700" font-size="58" letter-spacing="4"><tspan fill="${L}">${esc(a)}</tspan><tspan fill="${A}">${esc(b)}</tspan></text><rect x="${w / 2 - 50}" y="166" width="100" height="5" rx="2.5" fill="${A}"/>` }); }
    { const p = platTxt(g.plat), w = tw(p, "700 34px Poppins") + tw(N.toLowerCase(), "700 34px Poppins") + (p ? 110 : 96);
      out.push({ vb: [w, 90], svg: `<rect x="2" y="12" width="${w - 4}" height="66" rx="33" fill="${D}" fill-opacity=".92"/><circle cx="44" cy="45" r="20" fill="${A}"/>${icon(ic, 32, 33, 24, D)}<text x="76" y="57" font-family="Poppins" font-weight="700" font-size="34"><tspan fill="${L}" fill-opacity=".7">${esc(p)}</tspan><tspan fill="${A}">${esc(N.toLowerCase())}</tspan></text>` }); }
    return out.map((v, i) => ({ ...v, name: STYLES[i] }));
  }

  // ---- yazı tiplerini SVG'nin içine göm (resme dönüşürken web yazı tipleri yüklenmez)
  const FONT_FILES = {
    "Poppins": [["/fonts/Poppins-Bold.ttf", 700, "truetype"]],
    "Russo One": [["/static/fonts/russo-one-latin-400-normal.woff2", 400], ["/static/fonts/russo-one-latin-ext-400-normal.woff2", 400]],
    "Orbitron": [["/static/fonts/orbitron-latin-800-normal.woff2", 800]],
    "Bungee": [["/static/fonts/bungee-latin-400-normal.woff2", 400], ["/static/fonts/bungee-latin-ext-400-normal.woff2", 400]],
    "Bebas Neue": [["/static/fonts/bebas-neue-latin-400-normal.woff2", 400], ["/static/fonts/bebas-neue-latin-ext-400-normal.woff2", 400]],
    "Press Start 2P": [["/static/fonts/press-start-2p-latin-400-normal.woff2", 400], ["/static/fonts/press-start-2p-latin-ext-400-normal.woff2", 400]],
    "Rajdhani": [["/static/fonts/rajdhani-latin-700-normal.woff2", 700], ["/static/fonts/rajdhani-latin-ext-700-normal.woff2", 700]],
  };
  const fontCache = {};
  async function fontFaceCss(svg) {
    let css = "";
    for (const [fam, files] of Object.entries(FONT_FILES)) {
      if (!svg.includes(fam)) continue;
      for (const [url, w, fmt] of files) {
        if (!fontCache[url]) {
          fontCache[url] = fetch(url).then(r => r.blob()).then(b => new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(b); }));
        }
        css += `@font-face{font-family:"${fam}";font-weight:${w};src:url(${await fontCache[url]}) format("${fmt || "woff2"}");}`;
      }
    }
    return css;
  }
  function loadImage(src) {
    return new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = () => rej(new Error("Görsel açılamadı")); im.src = src; });
  }
  async function svgToImage(svgText, vb, scale) {
    const css = await fontFaceCss(svgText);
    let s = svgText;
    if (!/^\s*<svg/i.test(s)) {
      s = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${vb[0]} ${vb[1]}" width="${vb[0] * scale}" height="${vb[1] * scale}"><style>${css}</style>${s}</svg>`;
    } else if (css) {
      s = s.replace(/<svg([^>]*)>/i, `<svg$1><style>${css}</style>`);
    }
    const url = URL.createObjectURL(new Blob([s], { type: "image/svg+xml" }));
    try { return await loadImage(url); } finally { setTimeout(() => URL.revokeObjectURL(url), 2000); }
  }

  // ---- yüklenen SVG'deki renkleri bul / değiştir
  const COLOR_RE = /#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b|rgba?\([^)]*\)/g;
  function normHex(c) {
    c = c.trim();
    if (/^#[0-9a-f]{3}$/i.test(c)) return ("#" + c.slice(1).split("").map(x => x + x).join("")).toUpperCase();
    if (/^#[0-9a-f]{6}$/i.test(c)) return c.toUpperCase();
    const m = c.match(/rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/i);
    return m ? "#" + [m[1], m[2], m[3]].map(n => (+n).toString(16).padStart(2, "0")).join("").toUpperCase() : null;
  }
  function svgColors(svg) {
    const set = new Map();
    for (const m of svg.matchAll(COLOR_RE)) { const h = normHex(m[0]); if (h) set.set(h, (set.get(h) || 0) + 1); }
    for (const m of svg.matchAll(/(?:fill|stroke)\s*[:=]\s*["']?(black|white)\b/gi)) { const h = m[1].toLowerCase() === "black" ? "#000000" : "#FFFFFF"; set.set(h, (set.get(h) || 0) + 1); }
    return [...set.entries()].sort((a, b) => b[1] - a[1]).map(e => e[0]).slice(0, 12);
  }
  function recolorSvg(svg, map) {
    let s = svg.replace(COLOR_RE, (m) => { const h = normHex(m); return h && map[h] ? map[h] : m; });
    s = s.replace(/((?:fill|stroke)\s*[:=]\s*["']?)(black|white)\b/gi, (all, pre, name) => {
      const h = name.toLowerCase() === "black" ? "#000000" : "#FFFFFF"; return map[h] ? pre + map[h] : all;
    });
    return s;
  }

  // ---- piksel işlemleri
  const hexRgb = (h) => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  function canvasOf(img, maxW = 1200) {
    const s = Math.min(1, maxW / (img.naturalWidth || img.width));
    const c = document.createElement("canvas");
    c.width = Math.max(1, Math.round((img.naturalWidth || img.width) * s));
    c.height = Math.max(1, Math.round((img.naturalHeight || img.height) * s));
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    return c;
  }
  function removeBackground(c, tol) {
    // Köşelerden başlayıp arka plan rengine benzeyen bitişik pikselleri sil
    const ctx = c.getContext("2d"), { width: w, height: h } = c;
    const d = ctx.getImageData(0, 0, w, h), p = d.data, seen = new Uint8Array(w * h);
    const t2 = (tol * 4.4) ** 2, stack = [];
    for (const [x, y] of [[0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1]]) stack.push([x, y, (y * w + x) * 4]);
    const ref = stack.map(([, , i]) => [p[i], p[i + 1], p[i + 2]]);
    while (stack.length) {
      const [x, y] = stack.pop(); const k = y * w + x;
      if (x < 0 || y < 0 || x >= w || y >= h || seen[k]) continue;
      seen[k] = 1; const i = k * 4;
      if (p[i + 3] === 0 || ref.some(([r, g, b]) => (p[i] - r) ** 2 + (p[i + 1] - g) ** 2 + (p[i + 2] - b) ** 2 <= t2)) {
        p[i + 3] = 0; stack.push([x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]);
      }
    }
    ctx.putImageData(d, 0, 0);
  }
  function tint(c, hex) {
    const ctx = c.getContext("2d");
    ctx.globalCompositeOperation = "source-in"; ctx.fillStyle = hex; ctx.fillRect(0, 0, c.width, c.height);
    ctx.globalCompositeOperation = "source-over";
  }
  function replaceColor(c, fromHex, toHex, tol) {
    const ctx = c.getContext("2d"), d = ctx.getImageData(0, 0, c.width, c.height), p = d.data;
    const [fr, fg, fb] = hexRgb(fromHex), [tr, tg, tb] = hexRgb(toHex), t2 = (tol * 4.4) ** 2;
    const fl = (fr + fg + fb) / 3 || 1;
    for (let i = 0; i < p.length; i += 4) {
      if (!p[i + 3]) continue;
      if ((p[i] - fr) ** 2 + (p[i + 1] - fg) ** 2 + (p[i + 2] - fb) ** 2 <= t2) {
        const k = ((p[i] + p[i + 1] + p[i + 2]) / 3) / fl;  // gölge/ışık farkını koru
        p[i] = Math.min(255, tr * k); p[i + 1] = Math.min(255, tg * k); p[i + 2] = Math.min(255, tb * k);
      }
    }
    ctx.putImageData(d, 0, 0);
  }
  function hueShift(c, deg, sat, bri) {
    const o = document.createElement("canvas"); o.width = c.width; o.height = c.height;
    const ctx = o.getContext("2d"); ctx.filter = `hue-rotate(${deg}deg) saturate(${sat}) brightness(${bri})`;
    ctx.drawImage(c, 0, 0); return o;
  }
  function dominantColors(c, n = 6) {
    const s = document.createElement("canvas"); s.width = 64; s.height = Math.max(1, Math.round(64 * c.height / c.width));
    const x = s.getContext("2d"); x.drawImage(c, 0, 0, s.width, s.height);
    const p = x.getImageData(0, 0, s.width, s.height).data, bins = new Map();
    for (let i = 0; i < p.length; i += 4) {
      if (p[i + 3] < 128) continue;
      const k = ((p[i] >> 5) << 6) | ((p[i + 1] >> 5) << 3) | (p[i + 2] >> 5);
      const b = bins.get(k) || [0, 0, 0, 0]; b[0] += p[i]; b[1] += p[i + 1]; b[2] += p[i + 2]; b[3]++; bins.set(k, b);
    }
    return [...bins.values()].sort((a, b) => b[3] - a[3]).slice(0, n)
      .map(([r, g, b, k]) => "#" + [r / k, g / k, b / k].map(v => Math.round(v).toString(16).padStart(2, "0")).join("").toUpperCase());
  }
  function effects(c, fx) {
    const ow = fx.outline?.on ? Math.max(1, Math.round(fx.outline.width * c.width / 400)) : 0;
    const gl = fx.glow?.on ? Math.round(c.width / 18) : 0;
    const sh = fx.shadow?.on ? Math.round(c.width / 60) : 0;
    const pad = ow + gl + sh * 2 + 2;
    const o = document.createElement("canvas"); o.width = c.width + pad * 2; o.height = c.height + pad * 2;
    const ctx = o.getContext("2d");
    if (ow) {
      const m = document.createElement("canvas"); m.width = c.width; m.height = c.height;
      const mx = m.getContext("2d"); mx.drawImage(c, 0, 0); mx.globalCompositeOperation = "source-in"; mx.fillStyle = fx.outline.color; mx.fillRect(0, 0, m.width, m.height);
      for (let a = 0; a < 24; a++) { const r = a / 24 * Math.PI * 2; ctx.drawImage(m, pad + Math.cos(r) * ow, pad + Math.sin(r) * ow); }
      ctx.drawImage(m, pad, pad);
    }
    if (gl) { ctx.save(); ctx.shadowColor = fx.glow.color; ctx.shadowBlur = gl; ctx.drawImage(o, 0, 0); ctx.drawImage(c, pad, pad); ctx.drawImage(c, pad, pad); ctx.restore(); }
    if (sh) { ctx.save(); ctx.shadowColor = "rgba(0,0,0,.7)"; ctx.shadowBlur = sh * 2; ctx.shadowOffsetX = sh; ctx.shadowOffsetY = sh; ctx.drawImage(c, pad, pad); ctx.restore(); }
    ctx.drawImage(c, pad, pad);
    return o;
  }

  // ---- ana işlem: ayarlardan son logo görüntüsünü üret
  let fileCache = { key: null, img: null, svg: null };
  async function sourceImage(L) {
    if (L.source === "gen") {
      const v = variants(L.gen)[L.gen.style] || variants(L.gen)[0];
      return { img: await svgToImage(v.svg, v.vb, 4), svg: null };
    }
    if (!L.file?.path) return null;
    const url = "/media?path=" + encodeURIComponent(L.file.path);
    if (/\.svg$/i.test(L.file.path)) {
      if (fileCache.key !== url) fileCache = { key: url, svg: await (await fetch(url)).text(), img: null };
      const s = recolorSvg(fileCache.svg, L.svgMap || {});
      return { img: await svgToImage(s, null, 1), svg: fileCache.svg };
    }
    if (fileCache.key !== url) fileCache = { key: url, img: await loadImage(url), svg: null };
    return { img: fileCache.img, svg: null };
  }
  async function render(L) {
    const s = await sourceImage(L);
    if (!s) return null;
    let c = canvasOf(s.img);
    if (L.source === "file" && !s.svg) {
      const r = L.raster || {};
      if (r.bgRemove) removeBackground(c, r.bgTol ?? 25);
      if (r.mode === "tint") tint(c, r.color || "#FFFFFF");
      else if (r.mode === "replace" && r.from) replaceColor(c, r.from, r.color || "#FFFFFF", r.tol ?? 30);
      else if (r.mode === "hue") c = hueShift(c, r.hue || 0, r.sat ?? 1, r.bri ?? 1);
    }
    return effects(c, L.fx || {});
  }

  return { PALETTES, ICONS, STYLES, variants, render, svgColors, dominantColors, canvasOf, sourceImage, esc };
})();
