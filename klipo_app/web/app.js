// Streamchisel editörü (v0.6)
"use strict";
const $ = (id) => document.getElementById(id);
let W = 1080, H = 1920;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const uid = () => Math.random().toString(36).slice(2, 9);
const fmt = (t) => { t = Math.max(0, t || 0); const h = Math.floor(t / 3600), m = Math.floor(t / 60) % 60, s = Math.floor(t % 60);
  return [h, m, s].map(n => String(n).padStart(2, "0")).join(":"); };
const fmtS = (t) => { const m = Math.floor(t / 60), s = (t % 60).toFixed(1).padStart(4, "0"); return `${String(m).padStart(2, "0")}:${s}`; };
const escHtml = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || j.error) throw new Error(j.error || "Sunucu hatası");
  return j;
}
async function poll(id, onTick) {
  while (true) {
    const j = await api("/api/job/" + id);
    onTick(j);
    if (j.done) return j;
    await new Promise(r => setTimeout(r, 450));
  }
}
function toast(msg) { const t = $("toast"); t.textContent = msg; t.style.display = "block"; clearTimeout(toast.t); toast.t = setTimeout(() => t.style.display = "none", 3500); }

// ================================================================== durum
const DEF = {
  tab: "medya",
  preset: "stack", ratio: 0.35, lock: true, gameFit: "cover", autoCam: true, blur: 40,
  camera: { x: 0.0, y: 0.0, w: 0.25, h: 0.30 },
  game: { x: 0.21875, y: 0.0, w: 0.5625, h: 1.0 },
  focus: { x: 0.84, y: 0.70, w: 0.16, h: 0.30 },
  free: { bg: "blur", layers: null },
  silence: true, silDb: -38, silMin: 0.8, skipSil: true,
  subs: true, style: "bold", lang: "", model: "small", subPos: 0.62,
  tag: false, tagText: "",
  color: { brightness: 1, contrast: 1, saturation: 1 },
  srcVol: 1, music: null,
  format: "9:16", anim: "pop", wizAuto: true, pack: null, snap: true, translate: false, safe: false,
  hook: { on: false, text: "", style: "box", dur: 3, y: 0.16 },
  pb: { on: false, pos: "bottom", color: "#C8F135" },
  enhance: { denoise: false, normalize: false },
  logo: {
    on: false, source: "gen",
    gen: { name: "", plat: "kick", pal: 0, icon: "bolt", style: 7 },
    file: null, svgMap: {},
    raster: { mode: "none", color: "#C8F135", from: null, tol: 30, hue: 0, sat: 1, bri: 1, bgRemove: false, bgTol: 25 },
    fx: { outline: { on: false, color: "#FFFFFF", width: 5 }, glow: { on: false, color: "#C8F135" }, shadow: { on: false } },
    place: { x: 0.62, y: 0.015, w: 0.34, opacity: 1, fade: false, pos: "tr" },
  },
};
const LAYOUT_KEYS = ["preset", "ratio", "lock", "gameFit", "blur", "camera", "game", "focus", "free", "silence", "silDb", "silMin",
  "subs", "style", "lang", "model", "subPos", "tag", "tagText", "color", "srcVol", "music", "logo",
  "format", "anim", "translate", "hook", "pb", "enhance"];
let S = structuredClone(DEF);
let LAYOUTS = [];
let media = null;
// videoya özel (proje) durumu
let P = newProject();
function newProject() { return { range: { start: null, end: null }, splits: [], cuts: [], zooms: [], sfx: [], selSeg: null, selZoom: null, selFx: null, undo: [] }; }
let SIL = null, T = null, SFXLIB = [];
let saveTimer = null;
function deepMerge(a, b) {
  for (const [k, v] of Object.entries(b || {})) {
    if (v && typeof v === "object" && !Array.isArray(v) && a[k] && typeof a[k] === "object" && !Array.isArray(a[k])) deepMerge(a[k], v);
    else a[k] = v;
  }
  return a;
}
function save() {
  try { localStorage.setItem("streamchisel.settings", JSON.stringify(S)); } catch (e) {}
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => api("/api/state", { settings: S }).catch(() => {}), 400);
}
function pushUndo() { P.undo.push(JSON.stringify({ splits: P.splits, cuts: P.cuts, zooms: P.zooms, sfx: P.sfx })); if (P.undo.length > 60) P.undo.shift(); }
function undo() {
  const s = P.undo.pop(); if (!s) { toast("Geri alınacak bir şey yok"); return; }
  Object.assign(P, JSON.parse(s)); P.selSeg = null; renderAll();
}

// ================================================================== sekmeler
const TABS = [
  ["medya", "Medya", '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9.5v5l4-2.5z" fill="currentColor"/>'],
  ["anlar", "Anlar", '<path d="M12 3c1 3 4 4.5 4 8.5a4 4 0 0 1-8 0c0-1.6.7-2.7 1.5-3.5.2 1.3.9 2 1.7 2.3C11 8 11 5.5 12 3z"/><path d="M8.5 17.5A5 5 0 0 0 12 21a5 5 0 0 0 5-5"/>'],
  ["kadraj", "Kadraj", '<path d="M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4"/><rect x="8" y="8" width="8" height="8" rx="1"/>'],
  ["altyazi", "Altyazı", '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 15h4M13 15h4M7 11h10"/>'],
  ["logo", "Logo", '<path d="M12 3l2.6 5.6 6.1.7-4.6 4.1 1.3 6L12 16.4 6.6 19.4l1.3-6L3.3 9.3l6.1-.7z"/>'],
  ["ses", "Ses", '<path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2"/>'],
  ["renk", "Renk", '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/>'],
];
function renderRail() {
  $("rail").innerHTML = TABS.map(([id, label, ico]) =>
    `<button class="tabb" type="button" role="tab" aria-selected="${S.tab === id}" data-t="${id}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ico}</svg>${label}</button>`).join("");
  for (const b of $("rail").children) b.onclick = () => { S.tab = b.dataset.t; save(); renderRail(); showTab(); };
}
function showTab() {
  for (const s of document.querySelectorAll("aside .tab[data-tab]")) s.hidden = s.dataset.tab !== S.tab;
  renderRects(); renderOutOv();
  if (S.tab === "logo") refreshLogo();
}

// ================================================================== katmanlar (motorla aynı)
const v = $("vid");
function srcAspect() { return media && v.videoWidth ? v.videoWidth / v.videoHeight : 16 / 9; }
function presetLayers() {
  const FULL = { x: 0, y: 0, w: 1, h: 1 }, r = S.ratio, B = S.blur, D = 0.35;
  const top = { x: 0, y: 0, w: 1, h: r }, bottom = { x: 0, y: r, w: 1, h: 1 - r };
  const game = (dst) => S.gameFit === "contain"
    ? [{ src: S.game, dst, fit: "cover", blur: B, dim: D }, { src: S.game, dst, fit: "contain" }]
    : [{ src: S.game, dst, fit: "cover" }];
  switch (S.preset) {
    case "stack": return [{ src: S.camera, dst: top, fit: "cover" }, ...game(bottom)];
    case "blur": return [{ src: FULL, dst: FULL, fit: "cover", blur: B, dim: D }, { src: FULL, dst: FULL, fit: "contain" }];
    case "full": return game(FULL);
    case "focus": return [{ src: S.camera, dst: top, fit: "cover" }, ...game(bottom),
      { src: S.focus, dst: { x: 0.60, y: 0.70, w: 0.36, h: 0.20 }, fit: "cover", border: { width: 6, color: "#FF8A3D" } }];
    case "free": {
      const FULLc = { x: 0, y: 0, w: 1, h: 1 };
      const bg = S.free.bg === "blur" ? [{ src: FULLc, dst: FULLc, fit: "cover", blur: B, dim: D }] : [];
      return [...bg, ...freeLayers().map(l => ({ src: l.src, dst: l.dst, fit: "cover" }))];
    }
  }
  return [];
}
function freeLayers() {
  if (!S.free.layers || !S.free.layers.length) {
    S.free.layers = [
      { id: uid(), name: "Kamera", src: { ...S.camera }, dst: { x: 0.04, y: 0.03, w: 0.92, h: 0.30 } },
      { id: uid(), name: "Oyun", src: { ...S.game }, dst: { x: 0, y: 0.36, w: 1, h: 0.64 } },
    ];
  }
  return S.free.layers;
}
const RECTS = { stack: ["camera", "game"], blur: [], full: ["game"], focus: ["camera", "game", "focus"], free: [] };
const RECT_META = { camera: ["Kamera", "#5AA9FF"], game: ["Oyun", "#C8F135"], focus: ["Odak", "#FF8A3D"] };
const FREE_COLORS = ["#5AA9FF", "#C8F135", "#FF8A3D", "#B26BFF", "#3FD0FF", "#FF4FB3"];

// ---- oran kilidi: kaynakta seçilen kutu, çıktıda gideceği alanla aynı oranda olur
function dstAspect(key) {
  const r = S.ratio;
  if (key === "camera") return W / (H * r);
  if (key === "game") { if (S.gameFit === "contain") return null; return S.preset === "full" ? W / H : W / (H * (1 - r)); }
  if (key === "focus") return (0.36 * W) / (0.20 * H);
  return null;
}
const rectPxAspect = (dst) => (dst.w * W) / (dst.h * H);
function fitRect(r, aspect, anchor, ca) {
  ca = ca || srcAspect();
  let w = r.w, h = w * ca / aspect;
  if (h > 1) { h = 1; w = h * aspect / ca; }
  if (w > 1) { w = 1; h = w * ca / aspect; }
  let x, y;
  if (anchor === "tl") { x = r.x; y = r.y; } else { x = r.x + r.w / 2 - w / 2; y = r.y + r.h / 2 - h / 2; }
  return { x: clamp(x, 0, 1 - w), y: clamp(y, 0, 1 - h), w, h };
}
function relockAll() {
  if (!S.lock) return;
  for (const k of ["camera", "game", "focus"]) { const a = dstAspect(k); if (a) S[k] = fitRect(S[k], a, "c"); }
  if (S.preset === "free") for (const l of freeLayers()) l.src = fitRect(l.src, rectPxAspect(l.dst), "c");
  for (const z of P.zooms) z.src = fitRect(z.src, rectPxAspect(z.dst), "c");
}

// ================================================================== sürüklenebilir kutu (kaynak ve çıktı üzerinde)
function makeBox(container, opts) {
  // opts: {label, color, dashed, get():rect, set(rect), aspect():px oranı|null, ca: kapsayıcı en/boy, onEnd()}
  const el = document.createElement("div");
  el.className = "rect" + (opts.dashed ? " dashed" : "");
  el.style.borderColor = opts.color;
  el.innerHTML = `<span style="background:${opts.color}">${escHtml(opts.label)}</span><div class="h" style="background:${opts.color}" title="Boyutlandır"></div>`;
  const place = (r) => { el.style.left = r.x * 100 + "%"; el.style.top = r.y * 100 + "%"; el.style.width = r.w * 100 + "%"; el.style.height = r.h * 100 + "%"; };
  place(opts.get());
  el.addEventListener("pointerdown", (e) => {
    e.preventDefault(); e.stopPropagation();
    const resize = e.target.classList.contains("h");
    const box = container.getBoundingClientRect();
    const r0 = { ...opts.get() }, x0 = e.clientX, y0 = e.clientY;
    el.setPointerCapture(e.pointerId);
    const move = (ev) => {
      const dx = (ev.clientX - x0) / box.width, dy = (ev.clientY - y0) / box.height;
      let r = { ...r0 };
      const a = opts.aspect ? opts.aspect() : null, ca = opts.ca();
      if (resize) {
        r.w = clamp(r0.w + dx, 0.03, 1 - r.x); r.h = clamp(r0.h + dy, 0.03, 1 - r.y);
        if (a) {
          r.h = r.w * ca / a;
          if (r.y + r.h > 1) { r.h = 1 - r.y; r.w = r.h * a / ca; }
        }
      } else { r.x = clamp(r0.x + dx, 0, 1 - r.w); r.y = clamp(r0.y + dy, 0, 1 - r.h); }
      opts.set(r); place(r);
    };
    const up = () => { el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up); opts.onEnd && opts.onEnd(); save(); };
    el.addEventListener("pointermove", move); el.addEventListener("pointerup", up);
  });
  container.appendChild(el);
  return el;
}
function renderRects() {
  const ov = $("ov"); ov.innerHTML = "";
  if (!media) return;
  const sa = () => srcAspect();
  if (S.preset === "free") {
    freeLayers().forEach((l, i) => makeBox(ov, { label: l.name, color: FREE_COLORS[i % FREE_COLORS.length], ca: sa,
      get: () => l.src, set: (r) => { l.src = r; }, aspect: () => S.lock ? rectPxAspect(l.dst) : null }));
  } else {
    for (const k of RECTS[S.preset]) {
      const [label, color] = RECT_META[k];
      makeBox(ov, { label, color, ca: sa, get: () => S[k], set: (r) => { S[k] = r; }, aspect: () => S.lock ? dstAspect(k) : null, dashed: k === "focus" });
    }
  }
  const z = P.zooms.find(z => z.id === P.selZoom);
  if (z) makeBox(ov, { label: "Zoom kaynağı", color: "#FF8A3D", dashed: true, ca: sa, get: () => z.src, set: (r) => { z.src = r; }, aspect: () => rectPxAspect(z.dst) });
}
function renderOutOv() {
  const ov = $("outOv"); ov.innerHTML = "";
  if (!media) return;
  const ca = () => W / H;
  if (S.tab === "kadraj" && S.preset === "free") {
    freeLayers().forEach((l, i) => makeBox(ov, { label: l.name, color: FREE_COLORS[i % FREE_COLORS.length], ca,
      get: () => l.dst, set: (r) => { l.dst = r; if (S.lock) l.src = fitRect(l.src, rectPxAspect(r), "c"); }, onEnd: renderRects }));
  }
  const z = P.zooms.find(z => z.id === P.selZoom);
  if (S.tab === "kadraj" && z) makeBox(ov, { label: "Zoom", color: "#FF8A3D", ca, get: () => z.dst,
    set: (r) => { z.dst = r; z.src = fitRect(z.src, rectPxAspect(r), "c"); }, onEnd: renderRects });
  if (S.tab === "logo" && S.logo.on && logoCanvas) {
    const pl = S.logo.place, ar = logoCanvas.height / logoCanvas.width;
    makeBox(ov, { label: "Logo", color: "#B26BFF", ca, get: () => ({ x: pl.x, y: pl.y, w: pl.w, h: pl.w * ar * W / H }),
      set: (r) => { pl.x = r.x; pl.y = r.y; pl.w = r.w; pl.pos = null; }, aspect: () => 1 / ar, onEnd: () => { syncLogoPanel(); } });
  }
}

// ================================================================== Kadraj paneli
const PRESETS = [
  ["stack", "Kamera üstte", ["#3A2A48", "35%", "#1B3B45"]],
  ["blur", "Bulanık fon", ["#22313A", "100%", "#22313A"]],
  ["full", "Tam ekran", ["#1B3B45", "100%", "#1B3B45"]],
  ["focus", "Odak bölgesi", ["#3A2A48", "30%", "#1B3B45"]],
  ["free", "Serbest", ["#22313A", "100%", "#22313A"]],
];
function segButtons(el, items, cur, onPick) {
  el.innerHTML = "";
  for (const [id, label] of items) {
    const b = document.createElement("button"); b.type = "button"; b.textContent = label;
    b.className = cur === id ? "on" : ""; b.setAttribute("aria-pressed", cur === id);
    b.onclick = () => onPick(id); el.appendChild(b);
  }
}
const FORMATS = { "9:16": [1080, 1920, "Reels · TikTok · Shorts"], "1:1": [1080, 1080, "Instagram gönderi · X"], "4:5": [1080, 1350, "Instagram akış (dikey gönderi)"] };
function applyFormat() {
  const f = FORMATS[S.format] || FORMATS["9:16"];
  W = f[0]; H = f[1];
  const ch = Math.round(540 * H / W);
  if (cv.height !== ch) cv.height = ch;
  const hpx = Math.round(270 * H / W);
  cv.style.height = hpx + "px"; $("outWrap").style.height = hpx + "px";
  $("outCap").textContent = "ÇIKTI · " + (S.format || "9:16");
}
// ---- hazır stil paketleri (kadraj kutularına dokunmaz; sadece görünüm ve ayarlar)
const PACKS = [
  { id: "enerjik", name: "Enerjik", ds: "FPS, rekabetçi oyunlar", look: ["#3A2A48", 35, "#1B3B45", "#C8F135", "bold"],
    set: { preset: "stack", ratio: 0.35, gameFit: "cover", subs: true, style: "bold", anim: "bounce", hookOn: true, hookStyle: "box", pb: true, color: "Canlı", silence: true, enhance: true } },
  { id: "sohbet", name: "Sohbet", ds: "Just chatting, podcast", look: ["#3A2A48", 50, "#22313A", "#FFFFFF", "clean"],
    set: { preset: "stack", ratio: 0.5, gameFit: "cover", subs: true, style: "clean", anim: "karaoke", hookOn: false, pb: true, color: "Doğal", silence: true, enhance: true } },
  { id: "komik", name: "Komik", ds: "Tepki, fail, eğlenceli anlar", look: ["#48322A", 40, "#2A3A48", "#D9480F", "boxed"],
    set: { preset: "stack", ratio: 0.4, gameFit: "cover", subs: true, style: "boxed", anim: "pop", hookOn: true, hookStyle: "title", pb: true, color: "Canlı", silence: true, enhance: true } },
  { id: "irl", name: "IRL", ds: "Dışarı yayını, tek kamera", look: ["#2B4A3A", 100, "#2B4A3A", "#D9480F", "boxed"],
    set: { preset: "full", gameFit: "cover", subs: true, style: "boxed", anim: "pop", hookOn: true, hookStyle: "box", pb: false, color: "Parlak", silence: true, enhance: true } },
  { id: "sinematik", name: "Sinematik", ds: "Hikâye modu, manzara", look: ["#1D2733", 100, "#1D2733", "#FFFFFF", "clean"],
    set: { preset: "blur", subs: true, style: "clean", anim: "fade", hookOn: true, hookStyle: "title", pb: false, color: "Sinematik", silence: false, enhance: true } },
  { id: "sade", name: "Sade", ds: "Hızlı ve temiz", look: ["#22313A", 100, "#22313A", "#FFFFFF", "clean"],
    set: { preset: "blur", subs: true, style: "clean", anim: "none", hookOn: false, pb: false, color: "Doğal", silence: true, enhance: false } },
];
function packCard(pk, on, onPick) {
  const [top, h, bot, col, st] = pk.look, x = pk.set;
  const b = document.createElement("button"); b.type = "button"; b.className = "pack" + (on ? " on" : ""); b.setAttribute("aria-pressed", on);
  const sub = st === "boxed" ? `background:#FFE14D;color:#111;padding:1px 3px` : `color:${col};text-shadow:0 0 2px #000,0 0 2px #000`;
  const word = st === "clean" ? "Örnek" : "ÖRNEK";
  b.innerHTML = `<div class="pv" style="background:${bot}"><i style="height:${h}%;background:${top}"></i><i style="flex:1;background:${bot}"></i>` +
    (x.hookOn ? `<s style="${x.hookStyle === "title" ? "color:#fff;text-shadow:0 0 2px #000" : "background:#fff;color:#111"}">BUNU İZLE</s>` : "") +
    `<b><span style="${sub}">${word}</span></b>` + (x.pb ? `<u style="background:#C8F135"></u>` : "") + `</div><span class="nm">${pk.name}</span><span class="ds">${pk.ds}</span>`;
  b.onclick = () => onPick(pk.id);
  return b;
}
function applyPack(id) {
  const pk = PACKS.find(p => p.id === id); if (!pk) return;
  const x = pk.set, hadCam = S.preset === "stack" || S.preset === "focus";
  S.pack = id; S.preset = x.preset; if (x.ratio) S.ratio = x.ratio; if (x.gameFit) S.gameFit = x.gameFit;
  if (x.preset === "full") S.game = { x: 0, y: 0, w: 1, h: 1 };
  S.subs = x.subs; S.style = x.style; S.anim = x.anim;
  S.hook.on = x.hookOn; if (x.hookStyle) S.hook.style = x.hookStyle;
  S.pb.on = x.pb; S.silence = x.silence; S.enhance = { denoise: x.enhance, normalize: x.enhance };
  const c = COLOR_PRESETS.find(p => p[0] === x.color); if (c) S.color = { brightness: c[1], contrast: c[2], saturation: c[3] };
  relockAll(); save(); syncAll(); analyzeSilenceSoon();
  if (media && S.autoCam && !hadCam && (S.preset === "stack" || S.preset === "focus")) detectCamera(true);
}
function renderPacks(el, onPick) { el.innerHTML = ""; for (const pk of PACKS) el.appendChild(packCard(pk, S.pack === pk.id, onPick)); }
function syncKadraj() {
  renderPacks($("packs"), (id) => { applyPack(id); toast(`"${PACKS.find(p => p.id === id).name}" stili uygulandı`); });
  segButtons($("fmtSeg"), Object.keys(FORMATS).map(k => [k, k]), S.format, (id) => { S.format = id; applyFormat(); relockAll(); changed(); });
  $("fmtHint").textContent = (FORMATS[S.format] || FORMATS["9:16"])[2];
  $("presets").innerHTML = "";
  for (const [id, label, [a, h, b]] of PRESETS) {
    const btn = document.createElement("button"); btn.type = "button"; btn.className = "preset" + (S.preset === id ? " on" : "");
    btn.setAttribute("aria-pressed", S.preset === id);
    const extra = id === "free" ? '<i style="position:absolute;left:4px;top:5px;width:20px;height:12px;border:2px solid #5AA9FF;border-radius:2px"></i><i style="position:absolute;left:3px;top:22px;width:22px;height:22px;border:2px solid #C8F135;border-radius:2px"></i>' : "";
    btn.innerHTML = `<div class="thumb"><div style="height:${h};background:${a}"></div><div style="flex:1;background:${b}"></div>${extra}</div>${label}`;
    btn.onclick = () => { S.preset = id; if (id === "free") freeLayers(); relockAll(); changed(); };
    $("presets").appendChild(btn);
  }
  const hasCam = S.preset === "stack" || S.preset === "focus";
  $("secRatio").hidden = !hasCam;
  $("ratio").value = Math.round(S.ratio * 100); $("ratioV").textContent = `${Math.round(S.ratio * 100)} / ${100 - Math.round(S.ratio * 100)}`;
  const keys = RECTS[S.preset];
  $("secRects").hidden = keys.length === 0 && S.preset !== "free";
  $("chips").innerHTML = keys.map(k => `<div class="chip"><i style="border-color:${RECT_META[k][1]}"></i>${RECT_META[k][0]}</div>`).join("");
  $("bDetect").hidden = !hasCam;
  $("fitBox").hidden = !keys.includes("game");
  segButtons($("fitSeg"), [["cover", "Doldur"], ["contain", "Sığdır"]], S.gameFit, (id) => {
    if (id === S.gameFit) return; S.gameFit = id;
    if (id === "contain") S.game = { x: 0, y: 0, w: 1, h: 1 };
    relockAll(); changed();
  });
  $("lockOn").checked = S.lock;
  $("secFree").hidden = S.preset !== "free";
  if (S.preset === "free") {
    $("freeBg").value = S.free.bg;
    $("layerList").innerHTML = "";
    freeLayers().forEach((l, i) => {
      const it = document.createElement("div"); it.className = "item";
      it.innerHTML = `<i style="width:12px;height:12px;border-radius:3px;border:2px solid ${FREE_COLORS[i % FREE_COLORS.length]}"></i>`;
      const nm = document.createElement("input"); nm.type = "text"; nm.value = l.name; nm.style.height = "28px"; nm.setAttribute("aria-label", "Katman adı");
      nm.oninput = () => { l.name = nm.value; save(); renderRects(); renderOutOv(); };
      const del = document.createElement("button"); del.type = "button"; del.className = "btn tiny ghost danger"; del.textContent = "Sil";
      del.onclick = () => { if (freeLayers().length <= 1) { toast("En az bir katman olmalı"); return; } S.free.layers.splice(i, 1); changed(); };
      it.append(nm, del); $("layerList").appendChild(it);
    });
  }
  $("secBlur").hidden = !(S.preset === "blur" || (S.preset === "free" && S.free.bg === "blur") || (keys.includes("game") && S.gameFit === "contain"));
  $("blurAmt").value = S.blur; $("blurV").textContent = S.blur;
  $("rectHint").textContent = S.preset === "free" ? "Katmanları solda kaynaktan, sağda dikey videoda yerleştir" : keys.length ? "Kutuları sürükle, köşeden boyutlandır" : "Bu şablonda kadraj yok";
  renderZoomList();
}
function changed() { save(); syncKadraj(); renderRects(); renderOutOv(); }
$("ratio").oninput = (e) => { S.ratio = e.target.value / 100; relockAll(); changed(); };
$("lockOn").onchange = (e) => { S.lock = e.target.checked; relockAll(); changed(); };
$("blurAmt").oninput = (e) => { S.blur = +e.target.value; $("blurV").textContent = S.blur; save(); };
$("freeBg").onchange = (e) => { S.free.bg = e.target.value; changed(); };
$("bAddLayer").onclick = () => {
  const n = freeLayers().length + 1;
  S.free.layers.push({ id: uid(), name: "Katman " + n, src: { x: 0.35, y: 0.35, w: 0.3, h: 0.3 }, dst: { x: 0.3, y: 0.4, w: 0.4, h: 0.2 } });
  relockAll(); changed();
};
$("bReset").onclick = () => { S.camera = { ...DEF.camera }; S.game = { ...DEF.game }; S.focus = { ...DEF.focus }; relockAll(); changed(); };

// ---- düzenlerim
function renderLayouts() {
  const sel = $("lySel"), cur = sel.value;
  sel.innerHTML = '<option value="">— Kayıtlı düzen seç —</option>' + LAYOUTS.map((l, i) => `<option value="${i}">${escHtml(l.name)}</option>`).join("");
  if (cur && LAYOUTS[+cur]) sel.value = cur;
  $("lyDel").disabled = !sel.value;
}
$("lySel").onchange = () => {
  const l = LAYOUTS[+$("lySel").value]; $("lyDel").disabled = !l; if (!l) return;
  deepMerge(S, structuredClone(l.data)); relockAll(); syncAll(); refreshLogo(); toast(`"${l.name}" düzeni uygulandı`);
};
$("lySave").onclick = () => { $("lyName").value = ""; $("dLy").showModal(); $("lyName").focus(); };
$("lyCancel").onclick = () => $("dLy").close();
$("fLy").onsubmit = (e) => {
  e.preventDefault();
  const name = $("lyName").value.trim(); if (!name) return;
  const data = {}; for (const k of LAYOUT_KEYS) data[k] = structuredClone(S[k]);
  const i = LAYOUTS.findIndex(l => l.name.toLowerCase() === name.toLowerCase());
  if (i >= 0) LAYOUTS[i] = { name, data }; else LAYOUTS.push({ name, data });
  api("/api/state", { layouts: LAYOUTS }).catch(e => toast(e.message));
  $("dLy").close(); renderLayouts(); $("lySel").value = String(i >= 0 ? i : LAYOUTS.length - 1); $("lyDel").disabled = false;
  toast(`"${name}" kaydedildi`);
};
$("lyDel").onclick = () => {
  const i = +$("lySel").value; if (!LAYOUTS[i]) return;
  const name = LAYOUTS[i].name; LAYOUTS.splice(i, 1); api("/api/state", { layouts: LAYOUTS }).catch(e => toast(e.message));
  $("lySel").value = ""; renderLayouts(); toast(`"${name}" silindi`);
};

// ---- kamerayı otomatik bul
async function detectCamera(silent) {
  if (!media) return;
  const st = $("detStat"); st.hidden = false; st.className = "status"; st.innerHTML = '<span class="spin"></span>Kamera aranıyor…';
  $("bDetect").disabled = true;
  try {
    const { job } = await api("/api/detect", { path: media.path, start: P.range.start ?? 0, end: P.range.end ?? null });
    const j = await poll(job, () => {});
    if (j.error) throw new Error(j.error);
    const f = j.result.face;
    if (!f) { st.innerHTML = '<span class="dot" style="color:var(--focus)"></span>Kamera bulunamadı, kutuyu elle yerleştir'; if (!silent) toast("Videoda sabit bir yüz bulunamadı."); return; }
    const sa = srcAspect(), a = dstAspect("camera") || 1.6, cx = f.x + f.w / 2, cy = f.y + f.h / 2, ovl = j.result.overlay;
    let r;
    if (ovl && !S.lock) r = { ...ovl };
    else if (ovl) {
      let w = ovl.w, h = w * sa / a; if (h > ovl.h) { h = ovl.h; w = h * a / sa; }
      r = { w, h, x: clamp(cx - w / 2, ovl.x, ovl.x + ovl.w - w), y: clamp(cy - h * 0.42, ovl.y, ovl.y + ovl.h - h) };
    } else {
      const w = Math.min(0.6, Math.max(0.12, f.w * 3.4)), h = S.lock ? w * sa / a : Math.min(1, f.h * 3.0);
      r = { w, h, x: clamp(cx - w / 2, 0, 1 - w), y: clamp(cy - h * 0.42, 0, 1 - h) };
    }
    S.camera = r; save(); renderRects();
    st.className = "status ok"; st.innerHTML = `<span class="dot"></span>Kamera bulundu${ovl ? " ve pencereye oturtuldu" : ""}`;
  } catch (e) { st.textContent = "Kamera aranamadı: " + e.message; }
  finally { $("bDetect").disabled = false; }
}
$("bDetect").onclick = () => detectCamera(false);

// ---- zoom alanları
function renderZoomList() {
  const box = $("zoomList"); box.innerHTML = "";
  $("bAddZoom").disabled = !media;
  if (!P.zooms.length) { box.innerHTML = '<div class="hint">Önemli bir anı büyütmek için oynatıcıyı o ana getir ve "Şu ana ekle"ye bas. Süresini zaman çizelgesinde uzatabilir, kaynağını ve yerini kutularla ayarlayabilirsin.</div>'; return; }
  P.zooms.forEach((z, i) => {
    const it = document.createElement("div"); it.className = "item" + (z.id === P.selZoom ? " sel" : "");
    it.innerHTML = `<span class="nm">Zoom ${i + 1}</span><span class="tm">${fmtS(z.start)} – ${fmtS(z.end)}</span>`;
    const go = document.createElement("button"); go.type = "button"; go.className = "btn tiny"; go.textContent = "Seç";
    go.onclick = () => { P.selZoom = z.id; v.currentTime = z.start + 0.05; renderAll(); };
    const del = document.createElement("button"); del.type = "button"; del.className = "btn tiny ghost danger"; del.textContent = "Sil";
    del.onclick = () => { pushUndo(); P.zooms = P.zooms.filter(x => x !== z); if (P.selZoom === z.id) P.selZoom = null; renderAll(); };
    it.append(go, del); box.appendChild(it);
  });
}
$("bAddZoom").onclick = () => {
  if (!media) return;
  pushUndo();
  const t = v.currentTime, dst = { x: 0.06, y: 0.40, w: 0.88, h: 0.28 };
  const z = { id: uid(), start: t, end: Math.min(media.duration, t + 3), dst, src: fitRect({ x: 0.4, y: 0.4, w: 0.2, h: 0.2 }, rectPxAspect(dst), "c") };
  P.zooms.push(z); P.selZoom = z.id; renderAll();
  toast("Zoom eklendi: kaynaktaki turuncu kutuyu büyütmek istediğin yere taşı");
};

// ================================================================== sessizlik + kesimler
let silTimer = null, silSeq = 0;
function analyzeSilenceSoon() { clearTimeout(silTimer); silTimer = setTimeout(analyzeSilence, 700); }
async function analyzeSilence() {
  if (!media || !S.silence || !media.has_audio) { $("silStat") && ($("silStat").textContent = ""); return; }
  const seq = ++silSeq;
  try {
    const { job } = await api("/api/silence", { path: media.path, threshold_db: S.silDb, min_silence: S.silMin });
    const j = await poll(job, () => {});
    if (seq !== silSeq || j.error) return;
    SIL = j.result.silences; drawTimeline(); updRange();
  } catch (e) {}
}
const PAD = 0.15;
function silenceSpans(a, b) {
  if (!SIL || !S.silence) return [];
  const out = [];
  for (const [s, e] of SIL) { const x = Math.max(a, s + PAD), y = Math.min(b, e - PAD); if (y - x > 0.05) out.push([x, y]); }
  return out;
}
function unionSpans(list) {
  const s = list.filter(([a, b]) => b > a).sort((p, q) => p[0] - q[0]), out = [];
  for (const [a, b] of s) { if (out.length && a <= out[out.length - 1][1]) out[out.length - 1][1] = Math.max(out[out.length - 1][1], b); else out.push([a, b]); }
  return out;
}
function removedSpans(a, b) {  // sessizlik + elle kesimler, aralık içinde
  return unionSpans([...silenceSpans(a, b), ...P.cuts.map(([x, y]) => [Math.max(a, x), Math.min(b, y)])]);
}
function segments() {
  const d = media ? media.duration : 0, pts = [0, ...P.splits.filter(t => t > 0 && t < d), d];
  const out = [];
  for (let i = 0; i < pts.length - 1; i++) { const a = pts[i], b = pts[i + 1], m = (a + b) / 2; out.push({ a, b, cut: P.cuts.some(([x, y]) => m > x && m < y) }); }
  return out;
}
function splitAt(t) {
  if (!media) return;
  if (P.splits.some(s => Math.abs(s - t) < 0.05) || t < 0.1 || t > media.duration - 0.1) return;
  pushUndo(); P.splits.push(t); P.splits.sort((a, b) => a - b);
  drawTimeline(); toast("Bölündü. Silmek istediğin parçaya tıklayıp \"Parçayı sil\"e (Delete) bas.");
}
function segUnderPlayhead() { const t = v.currentTime; return segments().find(s => t >= s.a && t < s.b) || null; }
function toggleCutSelected() {
  // Silinecek parça: oynatıcının üzerinde durduğu parça (parçaya tıklamak da oynatıcıyı oraya götürür)
  const sg = segUnderPlayhead();
  if (!sg) return;
  pushUndo();
  if (sg.cut) {  // geri getir: bu parçayı kesimlerden çıkar
    const out = [];
    for (const [x, y] of P.cuts) { if (y <= sg.a || x >= sg.b) out.push([x, y]); else { if (x < sg.a) out.push([x, sg.a]); if (y > sg.b) out.push([sg.b, y]); } }
    P.cuts = out;
  } else P.cuts = unionSpans([...P.cuts.map(c => [...c]), [sg.a, sg.b]]);
  drawTimeline(); updRange();
  toast(sg.cut ? "Parça geri getirildi" : `${fmtS(sg.a)} – ${fmtS(sg.b)} arası silindi`);
}
$("bSplit").onclick = () => splitAt(v.currentTime);
$("bDelSeg").onclick = toggleCutSelected;
$("bUndo").onclick = undo;

// ================================================================== zaman çizelgesi
const view = { a: 0, b: 1 };
function resetView() { view.a = 0; view.b = media ? media.duration : 1; }
const X = (t) => ((t - view.a) / (view.b - view.a)) * 100;
const pctW = (a, b) => ((b - a) / (view.b - view.a)) * 100;
function tAtX(track, clientX) { const r = track.getBoundingClientRect(); return view.a + clamp((clientX - r.left) / r.width, 0, 1) * (view.b - view.a); }
function zoomView(f, center) {
  if (!media) return;
  const d = media.duration, span = clamp((view.b - view.a) * f, Math.min(d, 2), d);
  const c = center ?? v.currentTime, ratio = (c - view.a) / (view.b - view.a || 1);
  view.a = clamp(c - span * ratio, 0, d - span); view.b = view.a + span; drawTimeline();
}
$("bZoomIn").onclick = () => zoomView(0.5); $("bZoomOut").onclick = () => zoomView(2);
document.querySelector(".tlw").addEventListener("wheel", (e) => {
  if (!media) return;
  e.preventDefault();
  if (e.ctrlKey || e.metaKey) { zoomView(e.deltaY > 0 ? 1.25 : 0.8, tAtX($("trVid"), e.clientX)); return; }
  const span = view.b - view.a, d = media.duration, dt = (e.deltaY + e.deltaX) / 600 * span;
  view.a = clamp(view.a + dt, 0, d - span); view.b = view.a + span; drawTimeline();
}, { passive: false });

function drawTimeline() {
  const d = media ? media.duration : 0;
  const tracks = ["trRuler", "trVid", "trSub", "trZoom", "trFx", "trMus"];
  if (!media) { for (const t of tracks) $(t).innerHTML = ""; return; }
  // cetvel
  const span = view.b - view.a, steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
  const st = steps.find(s => span / s <= 10) || 3600;
  let rul = "";
  for (let t = Math.ceil(view.a / st) * st; t <= view.b; t += st) rul += `<div class="tick" style="left:${X(t)}%">${span < 120 ? fmtS(t) : fmt(t)}</div>`;
  if (HLCURVE.length && HL.rangeB > HL.rangeA) {
    const n = HLCURVE.length, dt = (HL.rangeB - HL.rangeA) / n;
    HLCURVE.forEach((c, i) => { const t = HL.rangeA + i * dt; if (c > 0.05 && t + dt >= view.a && t <= view.b) rul += `<div class="heat" style="left:${X(t)}%;width:${Math.max(0.15, pctW(t, t + dt))}%;height:${Math.round(c * 100)}%"></div>`; });
  }
  rul += HL.map(h => `<div class="hlmk" style="left:${X(h.start)}%;width:${pctW(h.start, h.end)}%" title="An ${h.n}"></div>`).join("");
  $("trRuler").innerHTML = rul;
  // video parçaları + sessizlikler + aralık
  const a = P.range.start ?? 0, b = P.range.end ?? d;
  let h = segments().map(s => `<div class="seg-v${s.cut ? " cut" : ""}" data-a="${s.a}" style="left:${X(s.a)}%;width:calc(${pctW(s.a, s.b)}% - 2px)"></div>`).join("");
  h += silenceSpans(0, d).map(([x, y]) => `<div class="silv" style="left:${X(x)}%;width:${pctW(x, y)}%"></div>`).join("");
  h += `<div class="dim" style="left:0;width:${Math.max(0, X(a))}%"></div><div class="dim" style="left:${X(b)}%;right:0"></div>`;
  h += `<div class="selr" style="left:${X(a)}%;width:${pctW(a, b)}%"></div>`;
  h += `<div class="hdl" id="hdlA" title="Klip başlangıcı" style="left:${X(a)}%"></div><div class="hdl" id="hdlB" title="Klip bitişi" style="left:calc(${X(b)}% - 12px)"></div>`;
  $("trVid").innerHTML = h;
  $("trVid").insertBefore(cvStrip, $("trVid").firstChild);
  drawStrip(); drawWave();
  // altyazı
  $("trSub").innerHTML = T ? T.chunks.filter(c => c[0]).map(c => { const s = c[0].start, e = c[c.length - 1].end;
    return `<div class="blk sub" style="left:${X(s)}%;width:${pctW(s, e)}%" title="${escHtml(c.map(w => w.text).join(" "))}">${escHtml(c.map(w => w.text).join(" "))}</div>`; }).join("") : "";
  // zoom
  $("trZoom").innerHTML = P.zooms.map((z, i) => `<div class="blk zm${z.id === P.selZoom ? " sel" : ""}" data-id="${z.id}" style="left:${X(z.start)}%;width:${pctW(z.start, z.end)}%"><div class="e l"></div>Zoom ${i + 1}<div class="e r"></div></div>`).join("");
  // efektler
  $("trFx").innerHTML = P.sfx.map(f => `<div class="mk${f.id === P.selFx ? " sel" : ""}" data-id="${f.id}" title="${escHtml(f.label)}" style="left:${X(f.time)}%">♪</div>`).join("");
  // müzik
  $("trMus").innerHTML = S.music ? `<div class="blk mus" style="left:${X(a)}%;width:${pctW(a, b)}%">${escHtml(S.music.name)}</div>` : "";
  drawPlayhead();
}
function drawPlayhead() {
  if (!media) return;
  const cur = segUnderPlayhead();
  for (const el of $("trVid").querySelectorAll(".seg-v")) el.classList.toggle("sel", !!cur && P.splits.length > 0 && Math.abs(+el.dataset.a - cur.a) < 1e-6);
  for (const id of ["trRuler", "trVid", "trAud", "trSub", "trZoom", "trFx", "trMus"]) {
    let ph = $(id).querySelector(".ph");
    if (!ph) { ph = document.createElement("div"); ph.className = "ph"; $(id).appendChild(ph); }
    const x = X(v.currentTime); ph.style.left = x + "%"; ph.hidden = x < 0 || x > 100;
  }
}
function dragOnTrack(track, e, onMove, onUp) {
  e.preventDefault(); track.setPointerCapture(e.pointerId);
  const move = (ev) => onMove(tAtX(track, ev.clientX), ev);
  const up = () => { track.removeEventListener("pointermove", move); track.removeEventListener("pointerup", up); onUp && onUp(); };
  track.addEventListener("pointermove", move); track.addEventListener("pointerup", up);
}
for (const id of ["trRuler", "trSub", "trMus", "trAud"]) $(id).addEventListener("pointerdown", (e) => { if (!media) return; dragOnTrack($(id), e, (t) => { v.currentTime = t; }); v.currentTime = tAtX($(id), e.clientX); });
$("trVid").addEventListener("pointerdown", (e) => {
  if (!media) return;
  const tr = $("trVid"), d = media.duration;
  if (e.target.id === "hdlA" || e.target.id === "hdlB") {
    const which = e.target.id === "hdlA" ? "start" : "end";
    dragOnTrack(tr, e, (t) => {
      t = snapT(t, tr, { self: which });
      if (which === "start") { P.range.start = Math.min(t, (P.range.end ?? d) - 1); if (P.range.start < 0.05) P.range.start = 0; v.currentTime = P.range.start; }
      else { P.range.end = Math.max(t, (P.range.start ?? 0) + 1); if (P.range.end > d - 0.05) P.range.end = d; v.currentTime = P.range.end; }
      updRange();
    });
    return;
  }
  const t = tAtX(tr, e.clientX);
  v.currentTime = t; drawTimeline();
  dragOnTrack(tr, e, (t2) => { v.currentTime = snapT(t2, tr, { self: "ph" }); });
});
$("trZoom").addEventListener("pointerdown", (e) => {
  if (!media) return;
  const blk = e.target.closest(".blk.zm"), tr = $("trZoom");
  if (!blk) { v.currentTime = tAtX(tr, e.clientX); return; }
  const z = P.zooms.find(x => x.id === blk.dataset.id); if (!z) return;
  pushUndo();
  P.selZoom = z.id; renderRects(); renderOutOv(); renderZoomList();
  const mode = e.target.classList.contains("l") ? "l" : e.target.classList.contains("r") ? "r" : "m";
  const t0 = tAtX(tr, e.clientX), z0 = { ...z }, d = media.duration;
  dragOnTrack(tr, e, (t) => {
    const dt = t - t0;
    const o = { zoom: z.id };
    if (mode === "l") z.start = clamp(snapT(z0.start + dt, tr, o), 0, z.end - 0.3);
    else if (mode === "r") z.end = clamp(snapT(z0.end + dt, tr, o), z.start + 0.3, d);
    else {
      const len = z0.end - z0.start; let st = z0.start + dt;
      const a = snapT(st, tr, o), b = snapT(st + len, tr, o) - len;
      st = Math.abs(a - st) <= Math.abs(b - st) ? (a !== st ? a : b) : b;
      z.start = clamp(st, 0, d - len); z.end = z.start + len;
    }
    drawTimeline();
  }, () => { renderZoomList(); });
  drawTimeline();
});
$("trFx").addEventListener("pointerdown", (e) => {
  if (!media) return;
  const mk = e.target.closest(".mk"), tr = $("trFx");
  if (!mk) { v.currentTime = tAtX(tr, e.clientX); return; }
  const f = P.sfx.find(x => x.id === mk.dataset.id); if (!f) return;
  pushUndo(); P.selFx = f.id;
  dragOnTrack(tr, e, (t) => { f.time = clamp(snapT(t, tr, { fx: f.id }), 0, media.duration); drawTimeline(); }, renderSfxList);
  drawTimeline();
});

// ---- mıknatıs: sürüklenen şey yakındaki önemli noktalara yapışır
function snapTargets(o) {
  const out = [];
  if (o.self !== "ph") out.push(v.currentTime);
  if (P.range.start != null && o.self !== "start") out.push(P.range.start);
  if (P.range.end != null && o.self !== "end") out.push(P.range.end);
  for (const x of P.splits) out.push(x);
  for (const [a, b] of P.cuts) out.push(a, b);
  for (const z of P.zooms) if (z.id !== o.zoom) out.push(z.start, z.end);
  for (const f of P.sfx) if (f.id !== o.fx) out.push(f.time);
  if (T) for (const ch of T.chunks) if (ch[0]) out.push(ch[0].start);
  for (const h of HL) out.push(h.start, h.peak);
  return out;
}
function snapT(t, track, o = {}) {
  if (!S.snap || !media) return t;
  const thr = 8 * (view.b - view.a) / Math.max(1, track.clientWidth);
  let best = t, bd = thr;
  for (const x of snapTargets(o)) { const dd = Math.abs(x - t); if (dd < bd) { bd = dd; best = x; } }
  return best;
}
function syncSnap() { $("bSnap").setAttribute("aria-pressed", !!S.snap); $("bSnap").classList.toggle("ghost", !S.snap); }
$("bSnap").onclick = () => { S.snap = !S.snap; save(); syncSnap(); toast(S.snap ? "Mıknatıs açık" : "Mıknatıs kapalı"); };

// ---- ses dalgası ve küçük kareler
const cvStrip = document.createElement("canvas"); cvStrip.setAttribute("aria-hidden", "true");
const TL = { path: null, peaks: null, rate: 20, strip: null, count: 0, loading: false };
async function loadTimelineAssets(m) {
  TL.path = m.path; TL.peaks = null; TL.strip = null; $("trVid").classList.remove("strip");
  $("audName").textContent = m.has_audio ? "Ses…" : "Ses yok";
  drawTimeline();
  try {
    const { job } = await api("/api/timeline", { path: m.path });
    const j = await poll(job, (j) => { if (TL.path === m.path) $("audName").textContent = `Ses… %${Math.round(j.progress * 100)}`; });
    if (TL.path !== m.path) return;  // bu arada başka video açıldı
    if (j.error) throw new Error(j.error);
    const r = j.result; TL.rate = r.rate; TL.count = r.count;
    if (r.strip) {
      const img = new Image(); img.src = "/cache/" + r.strip;
      img.onload = () => { if (TL.path === m.path) { TL.strip = img; $("trVid").classList.add("strip"); drawStrip(); } };
    }
    if (r.peaks) { const buf = await (await fetch("/cache/" + r.peaks)).arrayBuffer(); if (TL.path === m.path) TL.peaks = new Uint8Array(buf); }
    $("audName").textContent = "Kaynak ses";
    drawWave();
  } catch (e) { $("audName").textContent = "Kaynak ses"; console.warn(e); }
}
function fitCanvas(c, el) {
  const dpr = window.devicePixelRatio || 1, w = Math.max(1, Math.round(el.clientWidth * dpr)), h = Math.max(1, Math.round(el.clientHeight * dpr));
  if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
  return [w, h, dpr];
}
function drawStrip() {
  const tr = $("trVid"); const [w, h, dpr] = fitCanvas(cvStrip, tr), g = cvStrip.getContext("2d");
  g.clearRect(0, 0, w, h);
  if (!media || !TL.strip) return;
  const img = TL.strip, sw = img.width / TL.count, sh = img.height, tw = Math.round(h * 16 / 9), d = media.duration;
  g.globalAlpha = 0.75;
  for (let x = 0; x < w; x += tw) {
    const tc = view.a + ((x + tw / 2) / w) * (view.b - view.a);
    const i = clamp(Math.floor(tc / d * TL.count), 0, TL.count - 1);
    g.drawImage(img, i * sw, 0, sw, sh, x, 0, tw, h);
  }
  g.globalAlpha = 1;
}
function drawWave() {
  const tr = $("trAud"), c = $("cvAud"); const [w, h] = fitCanvas(c, tr), g = c.getContext("2d");
  g.clearRect(0, 0, w, h);
  if (!media || !TL.peaks) return;
  const pk = TL.peaks, rate = TL.rate, span = view.b - view.a, mid = h / 2;
  const a = P.range.start ?? 0, b = P.range.end ?? media.duration, rem = removedSpans(0, media.duration);
  let ri = 0;
  for (let x = 0; x < w; x++) {
    const t0 = view.a + (x / w) * span, t1 = view.a + ((x + 1) / w) * span;
    let i0 = Math.floor(t0 * rate), i1 = Math.max(i0 + 1, Math.ceil(t1 * rate)), m = 0;
    for (let i = Math.max(0, i0); i < Math.min(pk.length, i1); i++) if (pk[i] > m) m = pk[i];
    const tc = (t0 + t1) / 2;
    while (ri < rem.length && rem[ri][1] < tc) ri++;
    const off = tc < a || tc > b || (ri < rem.length && rem[ri][0] <= tc && tc <= rem[ri][1]);
    const hh = Math.max(1, (m / 255) * (h * 0.46));
    g.fillStyle = off ? "#3A3F49" : "#3FD0FF";
    g.fillRect(x, mid - hh, 1, hh * 2);
  }
}
window.addEventListener("resize", () => { drawStrip(); drawWave(); });

// ---- aralık
$("bIn").onclick = () => { if (!media) return; P.range.start = v.currentTime; if (P.range.end != null && P.range.end <= P.range.start + 0.5) P.range.end = null; updRange(); };
$("bOut").onclick = () => { if (!media) return; P.range.end = v.currentTime; if (P.range.start != null && P.range.start >= P.range.end - 0.5) P.range.start = null; updRange(); };
$("bSafe").onclick = () => { S.safe = !S.safe; $("bSafe").setAttribute("aria-pressed", S.safe); $("bSafe").classList.toggle("primary", S.safe); save(); };
$("bAll").onclick = () => { P.range = { start: null, end: null }; updRange(); };
function outLength() {
  const d = media.duration, a = P.range.start ?? 0, b = P.range.end ?? d;
  return { a, b, len: b - a - removedSpans(a, b).reduce((n, [x, y]) => n + (y - x), 0) };
}
function updRange() {
  drawTimeline();
  if (!media) return;
  const { a, b, len } = outLength(), whole = P.range.start == null && P.range.end == null;
  $("rangeTxt").textContent = (whole ? "Klip: tüm video" : `Klip: ${fmt(a)} – ${fmt(b)}`) + ` · ${Math.round(b - a)} sn` +
    (b - a - len > 0.5 ? ` → kesimlerle ≈${Math.round(len)} sn` : "") + (whole && media.duration > 600 ? " · uzun video, aralık seçmen önerilir" : "");
}

// ================================================================== altyazı
function chunkWords(words, maxWords = 3, gap = 0.6) {
  const out = []; let cur = [];
  for (const w of words) {
    if (cur.length && (cur.length >= maxWords || w.start - cur[cur.length - 1].end > gap || /[.!?]$/.test(cur[cur.length - 1].text))) { out.push(cur); cur = []; }
    cur.push(w);
  }
  if (cur.length) out.push(cur);
  return out;
}
async function runTranscribe() {
  if (!media) return;
  const a = P.range.start ?? 0, b = P.range.end ?? media.duration;
  $("bTr").disabled = true; $("trStat").className = "status"; $("trStat").innerHTML = '<span class="spin"></span>Altyazı oluşturuluyor… %0';
  try {
    const { job } = await api("/api/transcribe", { path: media.path, start: a, end: b, model: S.model, language: S.lang || null, translate: S.translate });
    const j = await poll(job, (j) => { $("trStat").innerHTML = `<span class="spin"></span>Altyazı oluşturuluyor… %${Math.round(j.progress * 100)}`; });
    if (j.error) throw new Error(j.error);
    const r = j.result;
    T = { start: r.start, end: r.end ?? media.duration, language: r.language, chunks: chunkWords(r.words) };
    updTrStatus(); drawTimeline();
    if (!r.words.length) toast("Bu bölümde konuşma bulunamadı.");
  } catch (e) { $("trStat").textContent = "Altyazı oluşturulamadı: " + e.message; }
  finally { $("bTr").disabled = !media; }
}
function updTrStatus() {
  $("bTr").textContent = T ? "Yeniden oluştur" : "Altyazıyı önizle";
  $("bTrEdit").hidden = !(T && T.chunks.length);
  if (!T) { $("trStat").className = "status"; $("trStat").textContent = "Önizlemede örnek yazı gösteriliyor"; $("outHint").textContent = "Altyazı burada örnek yazıyla gösterilir"; return; }
  const LN = { tr: "Türkçe", en: "İngilizce", pl: "Lehçe", de: "Almanca", es: "İspanyolca", fr: "Fransızca", ru: "Rusça", pt: "Portekizce" };
  $("trStat").className = "status ok";
  $("trStat").innerHTML = `<span class="dot"></span>${T.chunks.length} satır · ${LN[T.language] || T.language} · ${fmt(T.start)}–${fmt(T.end)}`;
  $("outHint").textContent = "Önizlemede gerçek altyazı oynuyor";
}
$("bTr").onclick = runTranscribe;
$("trRedo").onclick = () => { $("dTr").close(); runTranscribe(); };
$("bTrEdit").onclick = () => { renderChunks(); $("dTr").showModal(); };
$("trClose").onclick = () => { $("dTr").close(); drawTimeline(); };
function renderChunks() {
  const box = $("chunks"); box.innerHTML = "";
  T.chunks.forEach((ch, i) => {
    const row = document.createElement("div"); row.className = "ck"; row.dataset.i = i;
    const t = document.createElement("span"); t.className = "t"; t.textContent = fmtS(ch[0].start);
    const inp = document.createElement("input"); inp.type = "text"; inp.value = ch.map(w => w.text).join(" "); inp.setAttribute("aria-label", "Altyazı satırı " + (i + 1));
    inp.oninput = () => editChunk(i, inp.value);
    const go = document.createElement("button"); go.type = "button"; go.className = "btn small"; go.textContent = "Git"; go.onclick = () => { v.currentTime = T.chunks[i][0].start; };
    const del = document.createElement("button"); del.type = "button"; del.className = "btn small ghost"; del.textContent = "Sil";
    del.onclick = () => { T.chunks.splice(i, 1); renderChunks(); updTrStatus(); };
    row.append(t, inp, go, del); box.appendChild(row);
  });
}
function editChunk(i, text) {
  const ch = T.chunks[i], s = ch[0].start, e = ch[ch.length - 1].end, ws = text.trim().split(/\s+/).filter(Boolean);
  if (!ws.length) { T.chunks[i] = [{ start: s, end: e, text: "" }]; return; }
  const total = ws.reduce((n, w) => n + w.length + 1, 0); let t = s;
  T.chunks[i] = ws.map(w => { const d = (e - s) * (w.length + 1) / total; const o = { start: t, end: t + d, text: w }; t += d; return o; });
}
function currentChunk(t) {
  if (!T) return null;
  for (const ch of T.chunks) if (t >= ch[0].start - 0.02 && t <= ch[ch.length - 1].end + 0.15 && ch.some(w => w.text)) return ch;
  return null;
}
function syncAltyazi() {
  segButtons($("styles"), [["bold", "Kalın"], ["clean", "Sade"], ["boxed", "Kutulu"]], S.style, (id) => { S.style = id; save(); syncAltyazi(); });
  $("subOn").checked = S.subs; $("subBox").hidden = !S.subs;
  $("subLang").value = S.lang; $("subModel").value = S.model; $("subPos").value = Math.round(S.subPos * 100);
  $("tagOn").checked = S.tag; $("tagText").value = S.tagText; $("tagText").disabled = !S.tag;
  $("subAnim").value = S.anim; $("subTr").checked = S.translate;
  const hk = S.hook; $("hookOn").checked = hk.on; $("hookBox").hidden = !hk.on;
  if (document.activeElement !== $("hookText")) $("hookText").value = hk.text;
  segButtons($("hookStyle"), [["box", "Beyaz kutu"], ["title", "Kalın başlık"]], hk.style, (id) => { hk.style = id; save(); syncAltyazi(); });
  $("hookDur").value = String(hk.dur); $("hookY").value = Math.round(hk.y * 100);
  $("pbOn").checked = S.pb.on; $("pbBox").hidden = !S.pb.on; $("pbPos").value = S.pb.pos; $("pbColor").value = S.pb.color;
}
$("subAnim").onchange = (e) => { S.anim = e.target.value; save(); };
$("subTr").onchange = (e) => { S.translate = e.target.checked; save(); if (T) { T = null; updTrStatus(); drawTimeline(); toast("Altyazıyı yeniden önizle"); } };
$("hookOn").onchange = (e) => { S.hook.on = e.target.checked; save(); syncAltyazi(); if (S.hook.on) $("hookText").focus(); };
$("hookText").oninput = (e) => { S.hook.text = e.target.value; save(); };
$("hookDur").onchange = (e) => { S.hook.dur = +e.target.value; save(); };
$("hookY").oninput = (e) => { S.hook.y = e.target.value / 100; save(); };
$("pbOn").onchange = (e) => { S.pb.on = e.target.checked; save(); syncAltyazi(); };
$("pbPos").onchange = (e) => { S.pb.pos = e.target.value; save(); };
$("pbColor").oninput = (e) => { S.pb.color = e.target.value; save(); };
$("subOn").onchange = (e) => { S.subs = e.target.checked; save(); syncAltyazi(); };
$("subLang").onchange = (e) => { S.lang = e.target.value; save(); };
$("subModel").onchange = (e) => { S.model = e.target.value; save(); };
$("subPos").oninput = (e) => { S.subPos = e.target.value / 100; save(); };
$("tagOn").onchange = (e) => { S.tag = e.target.checked; save(); syncAltyazi(); if (S.tag) $("tagText").focus(); };
$("tagText").oninput = (e) => { S.tagText = e.target.value; save(); };

// ================================================================== logo
let logoCanvas = null, logoSeq = 0, logoTimer = null;
function refreshLogo() { clearTimeout(logoTimer); logoTimer = setTimeout(doRefreshLogo, 90); }
async function doRefreshLogo() {
  const seq = ++logoSeq;
  try {
    const c = await Logo.render(S.logo);
    if (seq !== logoSeq) return;
    logoCanvas = c;
    const pv = $("lpvC");
    if (c) { pv.width = c.width; pv.height = c.height; pv.getContext("2d").drawImage(c, 0, 0); pv.hidden = false; }
    else pv.hidden = true;
    if (S.logo.place.pos) placeLogo(S.logo.place.pos);
    renderOutOv();
    if (S.logo.source === "file" && c && !/\.svg$/i.test(S.logo.file?.path || "")) renderDominant();
  } catch (e) { toast("Logo hazırlanamadı: " + e.message); }
}
function placeLogo(pos) {
  const pl = S.logo.place; pl.pos = pos;
  if (!logoCanvas) return;
  const hN = pl.w * (logoCanvas.height / logoCanvas.width) * W / H, mx = 0.035, my = mx * W / H;
  const col = pos[1], row = pos[0];
  pl.x = col === "l" ? mx : col === "c" ? (1 - pl.w) / 2 : 1 - pl.w - mx;
  pl.y = row === "t" ? my : 1 - hN - my - 0.06;
}
function syncLogoPanel() {
  const L = S.logo;
  $("logoOn").checked = L.on;
  segButtons($("logoSrc"), [["gen", "Logo oluştur"], ["file", "Kendi logom"]], L.source, (id) => { L.source = id; save(); syncLogoPanel(); refreshLogo(); });
  $("genBox").hidden = L.source !== "gen"; $("fileBox").hidden = L.source !== "file";
  // oluştur
  $("lgName").value = L.gen.name || "";
  segButtons($("lgPlat"), [["kick", "Kick"], ["twitch", "Twitch"], ["yt", "YouTube"], ["none", "Yok"]], L.gen.plat, (id) => { L.gen.plat = id; save(); syncLogoPanel(); refreshLogo(); });
  const vs = Logo.variants({ ...L.gen, name: L.gen.name || "Kanal" });
  $("lgStyles").innerHTML = vs.map((x, i) => `<button class="stl${i === L.gen.style ? " on" : ""}" type="button" data-i="${i}" aria-label="${x.name}" title="${x.name}"><svg viewBox="0 0 ${x.vb[0]} ${x.vb[1]}" aria-hidden="true">${x.svg.replace(/id="g3"/g, `id="g3s${i}"`).replace(/url\(#g3\)/g, `url(#g3s${i})`)}</svg></button>`).join("");
  for (const b of $("lgStyles").children) b.onclick = () => { L.gen.style = +b.dataset.i; save(); syncLogoPanel(); refreshLogo(); };
  $("lgPal").innerHTML = Logo.PALETTES.map((p, i) => `<button class="sw${i === L.gen.pal ? " on" : ""}" type="button" data-i="${i}" title="${p[0]}" aria-label="${p[0]} renkleri"><i style="background:${p[1]}"></i><i style="background:${p[2]}"></i><i style="background:${p[3]}"></i></button>`).join("");
  for (const b of $("lgPal").children) b.onclick = () => { L.gen.pal = +b.dataset.i; save(); syncLogoPanel(); refreshLogo(); };
  $("lgIcons").innerHTML = Object.keys(Logo.ICONS).map(k => `<button class="ic${k === L.gen.icon ? " on" : ""}" type="button" data-k="${k}" aria-label="Simge"><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" aria-hidden="true">${Logo.ICONS[k]}</svg></button>`).join("");
  for (const b of $("lgIcons").children) b.onclick = () => { L.gen.icon = b.dataset.k; save(); syncLogoPanel(); refreshLogo(); };
  // dosya
  const isSvg = /\.svg$/i.test(L.file?.path || "");
  $("logoFileName").textContent = L.file ? L.file.name : "Logo dosyasını pencereye sürükleyip bırakabilirsin.";
  $("svgColorsBox").hidden = !(L.file && isSvg); $("rasterBox").hidden = !(L.file && !isSvg);
  if (L.file && isSvg) renderSvgColors();
  const R = L.raster;
  segButtons($("rMode"), [["none", "Orijinal"], ["tint", "Boya"], ["replace", "Değiştir"], ["hue", "Ton"]], R.mode, (id) => { R.mode = id; save(); syncLogoPanel(); refreshLogo(); });
  $("rTint").hidden = R.mode !== "tint"; $("rRepl").hidden = R.mode !== "replace"; $("rHue").hidden = R.mode !== "hue";
  $("rTintC").value = R.color; $("rReplC").value = R.color; $("rTol").value = R.tol;
  $("rHueV").value = R.hue; $("rSat").value = Math.round(R.sat * 100); $("rBri").value = Math.round(R.bri * 100);
  $("rBg").checked = R.bgRemove; $("rBgTolRow").hidden = !R.bgRemove; $("rBgTol").value = R.bgTol;
  // efektler + yerleşim
  const F = L.fx;
  $("fxOut").checked = F.outline.on; $("fxOutC").value = F.outline.color; $("fxOutW").value = F.outline.width; $("fxOutWRow").hidden = !F.outline.on;
  $("fxGlow").checked = F.glow.on; $("fxGlowC").value = F.glow.color; $("fxSh").checked = F.shadow.on;
  segButtons($("lgPos"), [["tl", "Sol üst"], ["tc", "Üst orta"], ["tr", "Sağ üst"], ["bl", "Sol alt"], ["bc", "Alt orta"], ["br", "Sağ alt"]], L.place.pos, (id) => { placeLogo(id); save(); syncLogoPanel(); renderOutOv(); });
  $("lgSize").value = Math.round(L.place.w * 100); $("lgOp").value = Math.round(L.place.opacity * 100); $("lgFade").checked = L.place.fade;
}
async function renderSvgColors() {
  const s = await Logo.sourceImage({ ...S.logo, svgMap: {} }).catch(() => null);
  if (!s || !s.svg) return;
  const cols = Logo.svgColors(s.svg), box = $("svgColors"); box.innerHTML = "";
  if (!cols.length) { box.innerHTML = '<div class="hint">Bu SVG\'de değiştirilebilir renk bulunamadı.</div>'; return; }
  for (const c of cols) {
    const pair = document.createElement("label"); pair.className = "cpair"; pair.title = c;
    const inp = document.createElement("input"); inp.type = "color"; inp.value = (S.logo.svgMap[c] || c).toLowerCase(); inp.setAttribute("aria-label", c + " rengini değiştir");
    inp.oninput = () => { S.logo.svgMap[c] = inp.value.toUpperCase(); save(); refreshLogo(); };
    pair.innerHTML = `<i style="background:${c}"></i>→`; pair.appendChild(inp); box.appendChild(pair);
  }
}
function renderDominant() {
  if (S.logo.raster.mode !== "replace") return;
  // renk listesi, işlenmemiş görüntüden alınır
  Logo.sourceImage(S.logo).then(s => {
    if (!s) return;
    const c = Logo.canvasOf(s.img, 300), cols = Logo.dominantColors(c, 7), box = $("rDom"); box.innerHTML = "";
    for (const col of cols) {
      const b = document.createElement("button"); b.type = "button"; b.className = "cdot" + (S.logo.raster.from === col ? " on" : "");
      b.style.background = col; b.title = col; b.setAttribute("aria-label", col + " rengini seç");
      b.onclick = () => { S.logo.raster.from = col; save(); refreshLogo(); renderDominant(); };
      box.appendChild(b);
    }
  });
}
// logoya tıklayarak renk seçme (damlalık)
$("lpv").addEventListener("click", async (e) => {
  if (S.logo.source !== "file" || S.logo.raster.mode !== "replace") return;
  const s = await Logo.sourceImage(S.logo); if (!s) return;
  const c = Logo.canvasOf(s.img), pv = $("lpvC"), r = pv.getBoundingClientRect();
  const fx = (e.clientX - r.left) / r.width, fy = (e.clientY - r.top) / r.height;
  if (fx < 0 || fy < 0 || fx > 1 || fy > 1) return;
  const p = c.getContext("2d").getImageData(Math.floor(fx * c.width), Math.floor(fy * c.height), 1, 1).data;
  if (p[3] < 20) return;
  S.logo.raster.from = "#" + [p[0], p[1], p[2]].map(n => n.toString(16).padStart(2, "0")).join("").toUpperCase();
  save(); refreshLogo(); renderDominant(); toast("Renk seçildi: " + S.logo.raster.from);
});
const L_ = () => S.logo;
$("logoOn").onchange = (e) => { L_().on = e.target.checked; if (L_().on && !L_().gen.name && media) L_().gen.name = (S.tagText || "").split("/").pop() || "Kanal"; save(); syncLogoPanel(); refreshLogo(); };
$("lgName").oninput = (e) => { L_().gen.name = e.target.value; save(); syncLogoPanel(); refreshLogo(); };
$("bLogoPick").onclick = async () => { try { const f = await api("/api/pick", { kind: "image" }); if (f.path) setLogoFile(f); } catch (e) { toast(e.message); } };
function setLogoFile(f) { const L = L_(); L.file = { path: f.path, name: f.name }; L.source = "file"; L.on = true; L.svgMap = {}; L.raster.from = null; save(); syncLogoPanel(); refreshLogo(); S.tab = "logo"; renderRail(); showTab(); }
$("bSvgReset").onclick = () => { L_().svgMap = {}; save(); renderSvgColors(); refreshLogo(); };
$("rTintC").oninput = (e) => { L_().raster.color = e.target.value; save(); refreshLogo(); };
$("rReplC").oninput = (e) => { L_().raster.color = e.target.value; save(); refreshLogo(); };
$("rTol").oninput = (e) => { L_().raster.tol = +e.target.value; save(); refreshLogo(); };
$("rHueV").oninput = (e) => { L_().raster.hue = +e.target.value; save(); refreshLogo(); };
$("rSat").oninput = (e) => { L_().raster.sat = e.target.value / 100; save(); refreshLogo(); };
$("rBri").oninput = (e) => { L_().raster.bri = e.target.value / 100; save(); refreshLogo(); };
$("rBg").onchange = (e) => { L_().raster.bgRemove = e.target.checked; $("rBgTolRow").hidden = !e.target.checked; save(); refreshLogo(); };
$("rBgTol").oninput = (e) => { L_().raster.bgTol = +e.target.value; save(); refreshLogo(); };
$("fxOut").onchange = (e) => { L_().fx.outline.on = e.target.checked; $("fxOutWRow").hidden = !e.target.checked; save(); refreshLogo(); };
$("fxOutC").oninput = (e) => { L_().fx.outline.color = e.target.value; save(); refreshLogo(); };
$("fxOutW").oninput = (e) => { L_().fx.outline.width = +e.target.value; save(); refreshLogo(); };
$("fxGlow").onchange = (e) => { L_().fx.glow.on = e.target.checked; save(); refreshLogo(); };
$("fxGlowC").oninput = (e) => { L_().fx.glow.color = e.target.value; save(); refreshLogo(); };
$("fxSh").onchange = (e) => { L_().fx.shadow.on = e.target.checked; save(); refreshLogo(); };
$("lgSize").oninput = (e) => { const pl = L_().place; pl.w = e.target.value / 100; if (pl.pos) placeLogo(pl.pos); save(); renderOutOv(); };
$("lgOp").oninput = (e) => { L_().place.opacity = e.target.value / 100; save(); };
$("lgFade").onchange = (e) => { L_().place.fade = e.target.checked; save(); };

// ================================================================== ses
function syncSes() {
  $("srcVol").value = Math.round(S.srcVol * 100); $("srcVolV").textContent = Math.round(S.srcVol * 100) + "%";
  const m = S.music;
  $("musEmpty").hidden = !!m; $("musBox").hidden = !m;
  if (m) { $("musName").textContent = m.name; $("musVol").value = Math.round(m.volume * 100); $("musDuck").checked = m.duck; $("musOff").value = m.offset || 0; }
  $("bFxPick").disabled = !media;
  $("enDen").checked = S.enhance.denoise; $("enNorm").checked = S.enhance.normalize;
  renderSfxLib();
  renderSfxList();
}
let sfxCat = "Tümü";
function renderSfxLib() {
  const cats = ["Tümü", ...new Set(SFXLIB.map(x => x.category || "Diğer"))];
  const pills = $("sfxCats"); pills.innerHTML = "";
  for (const c of cats) {
    const b = document.createElement("button"); b.type = "button"; b.textContent = c;
    b.className = c === sfxCat ? "on" : ""; b.setAttribute("aria-pressed", c === sfxCat);
    b.onclick = () => { sfxCat = c; renderSfxLib(); }; pills.appendChild(b);
  }
  const q = ($("sfxQ").value || "").trim().toLocaleLowerCase("tr");
  const box = $("sfxLib"); box.innerHTML = "";
  const items = SFXLIB.filter(it => (sfxCat === "Tümü" || (it.category || "Diğer") === sfxCat) && (!q || it.label.toLocaleLowerCase("tr").includes(q) || (it.category || "").toLocaleLowerCase("tr").includes(q)));
  if (!items.length) { box.innerHTML = '<div class="hint">Bu aramaya uyan efekt yok.</div>'; return; }
  for (const it of items) {
    const row = document.createElement("div"); row.className = "item";
    const pl = document.createElement("button"); pl.type = "button"; pl.className = "btn tiny"; pl.textContent = "▶"; pl.setAttribute("aria-label", it.label + " dinle");
    pl.onclick = () => playClip("/sfx/" + it.id + ".wav", 0.9);
    const nm = document.createElement("span"); nm.className = "nm"; nm.textContent = it.label;
    const ct = document.createElement("span"); ct.className = "cat"; ct.textContent = it.category || "Diğer"; ct.hidden = sfxCat !== "Tümü";
    const tm = document.createElement("span"); tm.className = "tm"; tm.textContent = it.duration.toFixed(1) + " sn";
    const add = document.createElement("button"); add.type = "button"; add.className = "btn tiny"; add.textContent = "Ekle"; add.disabled = !media;
    add.onclick = () => addSfx({ path: "sfx:" + it.id, label: it.label, url: "/sfx/" + it.id + ".wav" });
    row.append(pl, nm, ct, tm, add); box.appendChild(row);
  }
}
$("sfxQ").oninput = () => renderSfxLib();
function renderSfxList() {
  const box = $("sfxList"); box.innerHTML = "";
  if (!P.sfx.length) { box.innerHTML = '<div class="hint">Henüz efekt yok.</div>'; return; }
  for (const f of [...P.sfx].sort((a, b) => a.time - b.time)) {
    const row = document.createElement("div"); row.className = "item" + (f.id === P.selFx ? " sel" : "");
    row.innerHTML = `<span class="nm">${escHtml(f.label)}</span><span class="tm">${fmtS(f.time)}</span>`;
    const vol = document.createElement("input"); vol.type = "range"; vol.min = 0; vol.max = 150; vol.value = Math.round(f.volume * 100); vol.style.width = "70px"; vol.setAttribute("aria-label", "Efekt ses seviyesi");
    vol.oninput = () => { f.volume = vol.value / 100; };
    const go = document.createElement("button"); go.type = "button"; go.className = "btn tiny"; go.textContent = "Git"; go.onclick = () => { v.currentTime = Math.max(0, f.time - 1); P.selFx = f.id; drawTimeline(); };
    const del = document.createElement("button"); del.type = "button"; del.className = "btn tiny ghost danger"; del.textContent = "Sil";
    del.onclick = () => { pushUndo(); P.sfx = P.sfx.filter(x => x !== f); renderSfxList(); drawTimeline(); };
    row.append(vol, go, del); box.appendChild(row);
  }
}
function addSfx(o) { if (!media) return; pushUndo(); const f = { id: uid(), path: o.path, label: o.label, url: o.url, time: v.currentTime, volume: 0.8 }; P.sfx.push(f); P.selFx = f.id; renderSfxList(); drawTimeline(); toast(`"${o.label}" ${fmtS(f.time)} anına eklendi`); }
const clipCache = new Map();
function playClip(url, vol) { let a = clipCache.get(url); if (!a) { a = new Audio(url); clipCache.set(url, a); } try { a.currentTime = 0; a.volume = clamp(vol, 0, 1); a.play().catch(() => {}); } catch (e) {} }
$("enDen").onchange = (e) => { S.enhance.denoise = e.target.checked; save(); };
$("enNorm").onchange = (e) => { S.enhance.normalize = e.target.checked; save(); };
$("srcVol").oninput = (e) => { S.srcVol = e.target.value / 100; $("srcVolV").textContent = e.target.value + "%"; v.volume = clamp(S.srcVol, 0, 1); save(); };
$("bMusPick").onclick = async () => { try { const f = await api("/api/pick", { kind: "audio" }); if (f.path) setMusic(f); } catch (e) { toast(e.message); } };
function setMusic(f) { S.music = { path: f.path, name: f.name, volume: 0.25, duck: true, offset: 0 }; $("musA").src = "/media?path=" + encodeURIComponent(f.path); save(); syncSes(); drawTimeline(); }
$("bMusDel").onclick = () => { S.music = null; $("musA").pause(); $("musA").removeAttribute("src"); save(); syncSes(); drawTimeline(); };
$("musVol").oninput = (e) => { S.music.volume = e.target.value / 100; save(); };
$("musDuck").onchange = (e) => { S.music.duck = e.target.checked; save(); };
$("musOff").onchange = (e) => { S.music.offset = Math.max(0, +e.target.value || 0); save(); };
$("bFxPick").onclick = async () => { try { const f = await api("/api/pick", { kind: "audio" }); if (f.path) addSfx({ path: f.path, label: f.name, url: "/media?path=" + encodeURIComponent(f.path) }); } catch (e) { toast(e.message); } };

// ================================================================== renk
const COLOR_PRESETS = [["Doğal", 1, 1, 1], ["Canlı", 1.04, 1.12, 1.35], ["Sinematik", 0.95, 1.22, 0.82], ["Parlak", 1.15, 1.05, 1.1], ["Soluk", 1.05, 0.85, 0.7], ["Siyah-beyaz", 1, 1.15, 0]];
function syncRenk() {
  const c = S.color, cur = COLOR_PRESETS.find(p => Math.abs(p[1] - c.brightness) < .005 && Math.abs(p[2] - c.contrast) < .005 && Math.abs(p[3] - c.saturation) < .005);
  segButtons($("colPre"), COLOR_PRESETS.map(p => [p[0], p[0]]), cur ? cur[0] : null, (id) => { const p = COLOR_PRESETS.find(x => x[0] === id); S.color = { brightness: p[1], contrast: p[2], saturation: p[3] }; save(); syncRenk(); });
  $("cBri").value = Math.round(c.brightness * 100); $("cBriV").textContent = Math.round(c.brightness * 100);
  $("cCon").value = Math.round(c.contrast * 100); $("cConV").textContent = Math.round(c.contrast * 100);
  $("cSat").value = Math.round(c.saturation * 100); $("cSatV").textContent = Math.round(c.saturation * 100);
}
for (const [id, k] of [["cBri", "brightness"], ["cCon", "contrast"], ["cSat", "saturation"]]) $(id).oninput = (e) => { S.color[k] = e.target.value / 100; save(); syncRenk(); };
$("cReset").onclick = () => { S.color = { brightness: 1, contrast: 1, saturation: 1 }; save(); syncRenk(); };

// ================================================================== canlı önizleme
const cv = $("out"), ctx = cv.getContext("2d"), PS = cv.width / W;
function colorFilter() { const c = S.color; return (c.brightness !== 1 || c.contrast !== 1 || c.saturation !== 1) ? `brightness(${c.brightness}) contrast(${c.contrast}) saturate(${c.saturation})` : ""; }
function drawLayer(L) {
  const vw = v.videoWidth, vh = v.videoHeight;
  const sx = L.src.x * vw, sy = L.src.y * vh, sw = L.src.w * vw, sh = L.src.h * vh;
  const dx = L.dst.x * cv.width, dy = L.dst.y * cv.height, dw = L.dst.w * cv.width, dh = L.dst.h * cv.height;
  ctx.save(); ctx.beginPath(); ctx.rect(dx, dy, dw, dh); ctx.clip();
  const f = [colorFilter(), L.blur ? `blur(${L.blur * 0.5 * PS}px)` : ""].filter(Boolean).join(" ");
  if (f) ctx.filter = f;
  if (L.fit === "contain") { const s = Math.min(dw / sw, dh / sh), w = sw * s, h = sh * s; ctx.drawImage(v, sx, sy, sw, sh, dx + (dw - w) / 2, dy + (dh - h) / 2, w, h); }
  else { const s = Math.max(dw / sw, dh / sh), cw = dw / s, ch = dh / s; ctx.drawImage(v, sx + (sw - cw) / 2, sy + (sh - ch) / 2, cw, ch, dx, dy, dw, dh); }
  ctx.restore();
  if (L.dim) { ctx.fillStyle = `rgba(0,0,0,${L.dim})`; ctx.fillRect(dx, dy, dw, dh); }
  if (L.border) { const b = L.border.width * PS; ctx.lineWidth = b * 2; ctx.strokeStyle = L.border.color; ctx.strokeRect(dx - b, dy - b, dw + 2 * b, dh + 2 * b); }
}
const trUpper = (t, lang) => lang === "tr" || lang === "az" ? t.replace(/i/g, "İ").replace(/ı/g, "I").toUpperCase() : t.toUpperCase();
function drawSubs(parts, hi, o = {}) {
  const y = S.subPos * cv.height + (o.dy || 0); let fs = 84 * PS * 0.8;
  ctx.font = `700 ${fs}px Poppins, sans-serif`;
  const fit = (cv.width - 2 * 60 * PS) / ctx.measureText(parts.join(" ")).width; if (fit < 1) fs *= fit;
  ctx.font = `700 ${fs}px Poppins, sans-serif`; ctx.textBaseline = "middle"; ctx.lineJoin = "round";
  const space = ctx.measureText(" ").width, hs = o.hiScale || 1;
  const widths = parts.map((p, i) => ctx.measureText(p).width * (i === hi ? hs : 1)), total = widths.reduce((a, b) => a + b, 0) + space * (parts.length - 1);
  ctx.save(); ctx.globalAlpha = o.alpha ?? 1;
  const sc = o.scale ?? 1; ctx.translate(cv.width / 2, y); ctx.scale(sc, sc); ctx.translate(-cv.width / 2, -y);
  let x = (cv.width - total) / 2;
  if (S.style === "boxed") { ctx.fillStyle = "#FFE14D"; ctx.fillRect(x - 24 * PS, y - fs * 0.75, total + 48 * PS, fs * 1.5); }
  parts.forEach((p, i) => {
    ctx.save();
    if (i === hi && hs !== 1) { ctx.translate(x, y); ctx.scale(hs, hs); ctx.translate(-x, -y); }
    if (o.dimAfter && i > hi) ctx.globalAlpha *= 0.4;
    if (S.style !== "boxed") { ctx.lineWidth = (S.style === "bold" ? 12 : 8) * PS; ctx.strokeStyle = "#000"; ctx.strokeText(p, x, y); }
    ctx.fillStyle = i === hi ? (S.style === "boxed" ? "#D9480F" : "#C8F135") : (S.style === "boxed" ? "#111" : "#fff");
    ctx.fillText(p, x, y); ctx.restore(); x += widths[i] + space;
  });
  ctx.restore();
}
// Motorla aynı animasyon eğrileri (ASS \t etiketlerinin yaklaşık karşılığı)
const lerp = (a, b, k) => a + (b - a) * clamp(k, 0, 1);
function subAnim(t0, tw) {  // t0: grubun başından geçen sn, tw: vurgulu kelimenin başından geçen sn
  const o = {}, a = S.anim, ms = t0 * 1000;
  if (a === "pop") o.scale = ms < 110 ? lerp(0.7, 1.08, ms / 110) : lerp(1.08, 1, (ms - 110) / 70);
  if (a === "fade") o.alpha = clamp(ms / 120, 0, 1);
  if (a === "slide") { o.dy = lerp(40, 0, ms / 140) * PS; o.alpha = clamp(ms / 90, 0, 1); }
  if (a === "bounce") { const w = tw * 1000; o.hiScale = w < 80 ? lerp(1, 1.18, w / 80) : lerp(1.18, 1.08, (w - 80) / 90); }
  if (a === "karaoke") o.dimAfter = true;
  return o;
}
function drawHook(tOut, outLen) {
  const hk = S.hook; if (!hk.on || !hk.text.trim()) return;
  const dur = hk.dur > 0 ? hk.dur : Infinity; if (tOut > dur) return;
  const lines = hk.text.split(/\n/).map(l => l.trim()).filter(Boolean).slice(0, 3).map(l => trUpper(l, T ? T.language : "tr"));
  if (!lines.length) return;
  const ms = tOut * 1000, sc = ms < 140 ? lerp(0.6, 1.06, ms / 140) : lerp(1.06, 1, (ms - 140) / 80);
  const fade = dur !== Infinity && tOut > dur - 0.2 ? clamp((dur - tOut) / 0.2, 0, 1) : 1;
  const fs = 72 * PS * 0.8, lh = fs * 1.42, y0 = hk.y * cv.height - (lines.length - 1) * lh / 2;
  ctx.save(); ctx.globalAlpha = fade; ctx.translate(cv.width / 2, hk.y * cv.height); ctx.scale(sc, sc); ctx.translate(-cv.width / 2, -hk.y * cv.height);
  ctx.font = `700 ${fs}px Poppins, sans-serif`; ctx.textBaseline = "middle"; ctx.textAlign = "center"; ctx.lineJoin = "round";
  lines.forEach((l, i) => {
    const y = y0 + i * lh, w = Math.min(ctx.measureText(l).width, cv.width - 40 * PS);
    if (hk.style === "box") { const pad = 14 * PS; ctx.fillStyle = "#fff"; ctx.fillRect(cv.width / 2 - w / 2 - pad, y - fs * 0.62 - pad * 0.4, w + pad * 2, fs * 1.24 + pad * 0.8); ctx.fillStyle = "#111"; ctx.fillText(l, cv.width / 2, y, cv.width - 40 * PS); }
    else { ctx.lineWidth = 20 * PS; ctx.strokeStyle = "#000"; ctx.strokeText(l, cv.width / 2, y, cv.width - 40 * PS); ctx.fillStyle = "#fff"; ctx.fillText(l, cv.width / 2, y, cv.width - 40 * PS); }
  });
  ctx.restore();
}
function drawProgress(frac) {
  if (!S.pb.on) return;
  const h = Math.max(2, Math.round(cv.height * 0.006)), y = S.pb.pos === "top" ? 0 : cv.height - h;
  ctx.fillStyle = "rgba(0,0,0,.35)"; ctx.fillRect(0, y, cv.width, h);
  ctx.fillStyle = S.pb.color; ctx.fillRect(0, y, cv.width * clamp(frac, 0, 1), h);
}
function drawSafe() {
  if (!S.safe) return;
  // Reels / TikTok / Shorts arayüzünün kapattığı yaklaşık alanlar
  const Wc = cv.width, Hc = cv.height, zones = S.format === "9:16"
    ? [[0, 0, 1, 0.1, "Üst menü"], [0, 0.8, 1, 0.2, "Açıklama · müzik"], [0.86, 0.42, 0.14, 0.38, "Butonlar"]]
    : [[0, 0.88, 1, 0.12, "Açıklama"]];
  ctx.save(); ctx.setLineDash([6, 4]);
  for (const [x, y, w, h, l] of zones) {
    ctx.fillStyle = "rgba(255,70,70,.22)"; ctx.fillRect(x * Wc, y * Hc, w * Wc, h * Hc);
    ctx.strokeStyle = "rgba(255,120,120,.9)"; ctx.lineWidth = 2; ctx.strokeRect(x * Wc + 1, y * Hc + 1, w * Wc - 2, h * Hc - 2);
    ctx.fillStyle = "#fff"; ctx.font = `600 ${14}px "Segoe UI", sans-serif`; ctx.textBaseline = "top"; ctx.fillText(l, x * Wc + 6, y * Hc + 6);
  }
  ctx.restore();
}
function drawOverlays(t) {
  if (S.logo.on && logoCanvas) {
    const pl = S.logo.place, w = pl.w * cv.width, h = w * logoCanvas.height / logoCanvas.width;
    ctx.globalAlpha = pl.opacity; ctx.drawImage(logoCanvas, pl.x * cv.width, pl.y * cv.height, w, h); ctx.globalAlpha = 1;
  }
  if (S.subs) {
    const up = S.style !== "clean";
    if (T) { const ch = currentChunk(t); if (ch) { const ws = ch.filter(w => w.text); const hi = ws.findIndex((w, i) => t >= w.start && (i === ws.length - 1 || t < ws[i + 1].start));
      drawSubs(ws.map(w => up ? trUpper(w.text, T.language) : w.text), hi, subAnim(t - ws[0].start, hi >= 0 ? t - ws[hi].start : 1)); } }
    else { const ph = (t % 1.2); drawSubs(["altyazı", "burada", "görünür"].map(w => up ? trUpper(w, "tr") : w), Math.min(2, Math.floor(ph / 0.4)), subAnim(ph, ph % 0.4)); }
  }
  if (S.tag && S.tagText) {
    const y = (S.preset === "stack" || S.preset === "focus" ? S.ratio : 0.12) * cv.height;
    ctx.font = `700 ${54 * PS * 0.8}px Poppins, sans-serif`; ctx.textBaseline = "middle";
    const w = ctx.measureText(S.tagText).width, pad = 28 * PS;
    ctx.fillStyle = "#0E0F11"; ctx.fillRect((cv.width - w) / 2 - pad, y - 42 * PS, w + pad * 2, 84 * PS);
    ctx.fillStyle = "#C8F135"; ctx.fillText(S.tagText, (cv.width - w) / 2, y);
  }
}
let lastT = 0;
const reported = new Set();
function reportError(where, err) {
  const msg = `${where}: ${err && err.message || err}`;
  console.error(msg, err);
  if (reported.has(msg)) return;
  reported.add(msg);
  toast("Önizleme hatası: " + (err && err.message || err));
  fetch("/api/log", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ msg, stack: err && err.stack || "" }) }).catch(() => {});
}
window.addEventListener("error", (e) => reportError("sayfa", e.error || e.message));
window.addEventListener("unhandledrejection", (e) => reportError("işlem", e.reason));
function frame() {
  try { drawFrame(); } catch (e) { reportError("önizleme", e); }
  requestAnimationFrame(frame);  // bir karede hata olsa bile önizleme durmasın
}
function drawFrame() {
  ctx.fillStyle = "#000"; ctx.fillRect(0, 0, cv.width, cv.height);
  if (media && !(v.readyState >= 2 && v.videoWidth)) {
    ctx.fillStyle = "#9AA1AD"; ctx.font = `600 26px "Segoe UI", sans-serif`; ctx.textAlign = "center";
    ctx.fillText(v.error ? "Bu video önizlenemiyor" : "Video yükleniyor…", cv.width / 2, cv.height / 2);
    if (v.error) { ctx.font = `500 20px "Segoe UI", sans-serif`; ctx.fillText("Dışa aktarma yine çalışır", cv.width / 2, cv.height / 2 + 34); }
    ctx.textAlign = "start"; return;
  }
  if (media) {
    let t = v.currentTime;
    if (!v.paused) {
      const a = P.range.start ?? 0, b = P.range.end ?? media.duration;
      for (const [x, y] of (S.skipSil ? removedSpans(0, media.duration) : P.cuts)) if (t >= x && t < y - 0.04) { v.currentTime = y; t = y; syncMusic(true); break; }
      if (P.range.end != null && t >= b) { v.pause(); v.currentTime = b; }
      for (const f of P.sfx) if (f.time > lastT && f.time <= t && t - lastT < 0.6) playClip(f.url || ("/sfx/" + f.path.slice(4) + ".wav"), f.volume);
    }
    lastT = t;
    for (const L of presetLayers()) { try { drawLayer(L); } catch (e) { reportError("katman", e); } }
    for (const z of P.zooms) if (t >= z.start && t <= z.end) drawLayer({ src: z.src, dst: z.dst, fit: "cover", border: { width: 6, color: "#C8F135" } });
    drawOverlays(t);
    { const a = P.range.start ?? 0, b = P.range.end ?? media.duration; drawHook(Math.max(0, t - a), b - a); drawProgress((t - a) / Math.max(0.1, b - a)); }
    drawSafe();
    if (!LIC.licensed) { ctx.save(); ctx.font = `700 ${34 * PS * 0.8}px Poppins, sans-serif`; ctx.textAlign = "right"; ctx.textBaseline = "top";
      ctx.globalAlpha = 0.68; ctx.lineWidth = 3 * PS; ctx.strokeStyle = "rgba(0,0,0,.45)"; ctx.strokeText("Streamchisel ile yapıldı", cv.width - 28 * PS, cv.height * 0.115);
      ctx.fillStyle = "#fff"; ctx.fillText("Streamchisel ile yapıldı", cv.width - 28 * PS, cv.height * 0.115); ctx.restore(); }
    $("tNow").textContent = fmt(t);
    drawPlayhead();
    if ($("dTr").open) for (const row of $("chunks").children) { const ch = T && T.chunks[+row.dataset.i]; row.classList.toggle("cur", !!ch && ch[0] && t >= ch[0].start && t <= ch[ch.length - 1].end); }
  } else {
    ctx.fillStyle = "#3A3F49"; ctx.font = `600 28px "Segoe UI", sans-serif`; ctx.textAlign = "center"; ctx.fillText("Önizleme", cv.width / 2, cv.height / 2); ctx.textAlign = "start";
    drawSafe();
  }
}
function syncMusic(seek) {
  const m = $("musA");
  if (!S.music || !m.src) return;
  m.volume = clamp(S.music.volume, 0, 1);
  if (v.paused) { m.pause(); return; }
  const want = (S.music.offset || 0) + (v.currentTime - (P.range.start ?? 0));
  if (m.duration && isFinite(m.duration)) {
    const pos = ((want % m.duration) + m.duration) % m.duration;
    if (seek || Math.abs(m.currentTime - pos) > 0.4) m.currentTime = pos;
  }
  m.play().catch(() => {});
}

// ================================================================== oynatma
v.addEventListener("loadedmetadata", () => {
  $("tDur").textContent = "/ " + fmt(v.duration);
  $("stage").style.aspectRatio = `${v.videoWidth} / ${v.videoHeight}`;
  resetView(); relockAll(); renderAll();
  if (S.autoCam && !loadingProject && (S.preset === "stack" || S.preset === "focus")) detectCamera(true);
  loadingProject = false;
});
v.addEventListener("play", () => { $("playIco").setAttribute("d", "M6 4h4v16H6zM14 4h4v16h-4z"); syncMusic(true); });
v.addEventListener("pause", () => { $("playIco").setAttribute("d", "M7 4l13 8-13 8z"); syncMusic(); });
v.addEventListener("seeked", () => syncMusic(true));
v.addEventListener("error", () => toast("Bu video önizlenemiyor, ama dışa aktarma yine çalışır."));
$("bPlay").onclick = () => { if (!media) return; if (v.paused && P.range.end != null && v.currentTime >= P.range.end - 0.05) v.currentTime = P.range.start ?? 0; v.paused ? v.play() : v.pause(); };
const frameDur = () => 1 / ((media && media.fps) || 30);
$("bPrevF").onclick = () => { v.pause(); v.currentTime = Math.max(0, v.currentTime - frameDur()); };
$("bNextF").onclick = () => { v.pause(); v.currentTime = Math.min(media ? media.duration : 0, v.currentTime + frameDur()); };
document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, select, textarea") || document.querySelector("dialog[open]")) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); undo(); return; }
  if (!media) return;
  const k = e.key;
  if (e.code === "Space") { e.preventDefault(); $("bPlay").click(); }
  else if (k === "i" || k === "I") $("bIn").click();
  else if (k === "o" || k === "O") $("bOut").click();
  else if (k === "s" || k === "S") splitAt(v.currentTime);
  else if (k === "m" || k === "M") $("bSnap").click();
  else if (k === "Delete" || k === "Backspace") { e.preventDefault(); toggleCutSelected(); }
  else if (k === ",") $("bPrevF").click();
  else if (k === ".") $("bNextF").click();
  else if (k === "ArrowLeft") v.currentTime = Math.max(0, v.currentTime - 5);
  else if (k === "ArrowRight") v.currentTime = Math.min(media.duration, v.currentTime + 5);
});

// ================================================================== medya
function setMedia(m) {
  media = m; P = newProject(); SIL = null; T = null;
  $("fname").textContent = m.name;
  $("fmeta").textContent = `${fmt(m.duration)} · ${m.width}×${m.height} · ${Math.round(m.fps)} FPS` + (m.has_audio ? "" : " · ses yok");
  $("empty").hidden = true; v.hidden = false;
  v.src = "/media?path=" + encodeURIComponent(m.path); v.volume = clamp(S.srcVol, 0, 1);
  $("bExp").disabled = false; $("bTr").disabled = false; $("detStat").hidden = true;
  if (!loadingProject) { HL = []; HLCURVE = []; }
  $("bResume").hidden = true;
  updTrStatus(); analyzeSilence(); syncSes(); renderZoomList(); syncAnlar(); loadTimelineAssets(m);
  $("bWiz").disabled = false;
  if (!loadingProject && S.wizAuto !== false) setTimeout(openWizard, 400);
  if (S.tab === "medya") { S.tab = "kadraj"; renderRail(); showTab(); }
}
function renderRecent(list) {
  const box = $("recent"), side = $("recentList");
  box.innerHTML = ""; side.innerHTML = list.length ? "" : '<div class="hint">Henüz proje yok.</div>';
  for (const r of list) {
    const open = async () => { try { setMedia(await api("/api/open", { path: r.path })); } catch (e) { toast(e.message); } };
    const b = document.createElement("button"); b.type = "button"; b.className = "rc";
    const img = document.createElement("img"); img.alt = ""; img.loading = "lazy"; img.src = "/api/thumb?path=" + encodeURIComponent(r.path);
    img.onerror = () => { const d = document.createElement("div"); d.className = "ph0"; img.replaceWith(d); };
    const n = document.createElement("b"); n.textContent = r.name;
    const s = document.createElement("span"); s.textContent = r.duration ? fmt(r.duration) : "";
    b.append(img, n, s); b.onclick = open; box.appendChild(b);
    const it = document.createElement("button"); it.type = "button"; it.className = "item"; it.style.textAlign = "left";
    it.innerHTML = `<span class="nm">${escHtml(r.name)}</span><span class="tm">${r.duration ? fmt(r.duration) : ""}</span>`; it.onclick = open; side.appendChild(it);
  }
}
async function pickVideo() { try { const m = await api("/api/pick", { kind: "video" }); if (m.path) setMedia(m); } catch (e) { toast(e.message); } }
$("bOpen").onclick = pickVideo;
document.querySelector('[data-act="open"]').onclick = pickVideo;
document.querySelector('[data-act="dl"]').onclick = () => $("bDl").click();

let dragDepth = 0;
document.addEventListener("dragenter", (e) => { if ([...(e.dataTransfer?.types || [])].includes("Files")) { dragDepth++; $("drop").hidden = false; } });
document.addEventListener("dragleave", () => { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) $("drop").hidden = true; });
document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => {
  e.preventDefault(); dragDepth = 0; $("drop").hidden = true;
  const f = e.dataTransfer?.files?.[0]; if (!f) return;
  if (!/\.(mp4|mkv|mov|webm|flv|ts|avi|m4v|png|jpe?g|webp|svg|mp3|wav|m4a|aac|ogg|flac|opus)$/i.test(f.name)) { toast("Bu dosya türü desteklenmiyor."); return; }
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload"); xhr.setRequestHeader("X-Filename", encodeURIComponent(f.name));
  xhr.upload.onprogress = (ev) => { if (ev.lengthComputable) toast(`Dosya alınıyor… %${Math.round(ev.loaded / ev.total * 100)}`); };
  xhr.onload = () => {
    let j = {}; try { j = JSON.parse(xhr.responseText); } catch (er) {}
    if (xhr.status !== 200 || j.error) { toast(j.error || "Dosya alınamadı"); return; }
    if (j.kind === "image") { setLogoFile(j); toast("Logo eklendi"); }
    else if (j.kind === "audio") { if (S.tab === "ses" && media && !e.shiftKey) { addSfx({ path: j.path, label: j.name, url: "/media?path=" + encodeURIComponent(j.path) }); } else { setMusic(j); toast("Müzik eklendi"); } }
    else { setMedia(j); toast("Video açıldı"); }
  };
  xhr.onerror = () => toast("Dosya alınamadı");
  xhr.send(f);
});

$("bDl").onclick = () => { $("dlErr").textContent = ""; $("dlProg").hidden = true; $("dlGo").disabled = false; $("dDl").showModal(); };
$("dlClose").onclick = () => $("dDl").close();
$("fDl").onsubmit = async (e) => {
  e.preventDefault(); $("dlErr").textContent = ""; $("dlGo").disabled = true; $("dlProg").hidden = false;
  try {
    const { job } = await api("/api/download", { url: $("dlUrl").value, quality: $("dlQ").value });
    const j = await poll(job, (j) => { const p = Math.round(j.progress * 100); $("dlBar").style.width = p + "%"; $("dlPct").textContent = p + "%"; $("dlStat").textContent = j.stage === "download" ? "İndiriliyor…" : "Hazırlanıyor…"; });
    if (j.error) throw new Error(j.error);
    setMedia(await api("/api/open", { path: j.result.path })); $("dDl").close(); toast("Video indirildi ve açıldı.");
  } catch (err) { $("dlErr").textContent = err.message; }
  $("dlGo").disabled = false;
};

// ================================================================== dışa aktarma
const STAGE = { queued: "Sıraya alındı…", silence: "Kesimler hesaplanıyor…", transcribe: "Altyazı oluşturuluyor…", render: "Video oluşturuluyor…", done: "Bitti", error: "Hata" };
const WEIGHT = { silence: [0, .05], transcribe: [.05, .45], render: [.45, 1] };
const transcriptCovers = (a, b) => T && T.start <= a + 0.5 && T.end >= b - 0.5;
function project(over = {}) {
  const rng = over.range || P.range;
  const a = rng.start ?? 0, b = rng.end ?? media.duration;
  const sub = { enabled: S.subs, language: S.lang || null, model: S.model, style: S.style, position_y: S.subPos,
                animation: S.anim, translate: S.translate };
  if (S.subs && transcriptCovers(a, b)) { sub.chunks = T.chunks; sub.detected_language = T.language; }
  const p = {
    input: media.path, output_name: over.name || $("expName").value, format: S.format,
    range: rng.start != null || rng.end != null ? { start: a, end: b } : null,
    hook: { enabled: S.hook.on && !!S.hook.text.trim(), text: S.hook.text, style: S.hook.style, duration: S.hook.dur, y: S.hook.y },
    progress: { enabled: S.pb.on, position: S.pb.pos, color: S.pb.color },
    layout: { preset: S.preset === "free" ? "stack" : S.preset, camera: S.camera, game: S.game, focus: S.focus, camera_ratio: S.ratio, game_fit: S.gameFit, blur: S.blur },
    silence: { enabled: S.silence, threshold_db: S.silDb, min_silence: S.silMin },
    subtitles: sub,
    tag: { enabled: S.tag && !!S.tagText.trim(), text: S.tagText.trim() },
    cuts: P.cuts, zooms: P.zooms.map(z => ({ start: z.start, end: z.end, src: z.src, dst: z.dst })),
    color: S.color,
    audio: { source_volume: S.srcVol, enhance: { ...S.enhance }, music: S.music ? { path: S.music.path, volume: S.music.volume, duck: S.music.duck, offset: S.music.offset || 0 } : null,
             sfx: P.sfx.map(f => ({ path: f.path, time: f.time, volume: f.volume })) },
    export: { quality: over.quality || $("expQ").value, encoder: "auto" },
  };
  if (S.preset === "free") p.layers = presetLayers();
  if (S.logo.on && logoCanvas) {
    const pl = S.logo.place;
    p.logo = { x: pl.x, y: pl.y, w: pl.w, opacity: pl.opacity, fade: pl.fade };
    p.logo_png = logoCanvas.toDataURL("image/png");
  }
  return p;
}
let lastOut = null;
$("bExp").onclick = () => {
  if (!media) return;
  const { a, b, len } = outLength(), parts = [`${fmt(a)} – ${fmt(b)} · ≈${Math.round(len)} sn`];
  if (P.cuts.length) parts.push(`${P.cuts.length} elle kesim`);
  if (P.zooms.length) parts.push(`${P.zooms.length} zoom`);
  if (S.logo.on) parts.push("logo");
  if (S.music) parts.push("müzik");
  if (P.sfx.length) parts.push(`${P.sfx.length} efekt`);
  if (S.subs) parts.push(transcriptCovers(a, b) ? "önizlediğin altyazı" : "altyazı oluşturulacak");
  $("expInfo").textContent = parts.join(" · ");
  $("expName").value = media.name.replace(/\.[^.]+$/, "") + "_dikey";
  $("expProg").hidden = true; $("expDone").hidden = true; $("expErr").textContent = "";
  $("expReveal").hidden = $("expPlay").hidden = $("expQr").hidden = true; $("expGo").hidden = false; $("expGo").disabled = false; $("expQueue").hidden = false;
  $("sugTitles").innerHTML = ""; $("sugTags").hidden = true;
  $("expFree").hidden = LIC.licensed; $("expFree").innerHTML = freeText(); loadLicense().then(() => { $("expFree").innerHTML = freeText(); });
  $("dExp").showModal();
};
$("expClose").onclick = () => $("dExp").close();
$("expReveal").onclick = () => api("/api/reveal", { path: lastOut }).catch(e => toast(e.message));
$("expPlay").onclick = () => api("/api/play", { path: lastOut }).catch(e => toast(e.message));
$("fExp").onsubmit = async (e) => {
  e.preventDefault(); $("expErr").textContent = ""; $("expGo").disabled = true; $("expProg").hidden = false;
  try {
    const { job } = await api("/api/render", { project: project() });
    const j = await poll(job, (j) => {
      const w = WEIGHT[j.stage], p = w ? w[0] + (w[1] - w[0]) * j.progress : (j.done ? 1 : 0);
      $("expBar").style.width = Math.round(p * 100) + "%"; $("expPct").textContent = Math.round(p * 100) + "%"; $("expStat").textContent = STAGE[j.stage] || j.stage;
    });
    if (j.error) throw new Error(j.error);
    const r = j.result; lastOut = r.output;
    const removed = Math.max(0, r.source_duration - r.duration);
    $("expDone").innerHTML = `<div class="ok">Video hazır</div><div class="hint">${r.duration.toFixed(1)} sn` + (removed > 0.5 ? ` · ${removed.toFixed(1)} sn kesildi` : "") + ` · ${r.elapsed.toFixed(0)} sn sürdü</div>`;
    const pth = document.createElement("div"); pth.className = "hint"; pth.style.wordBreak = "break-all"; pth.textContent = r.output; $("expDone").appendChild(pth);
    $("expDone").hidden = false; $("expReveal").hidden = $("expPlay").hidden = $("expQr").hidden = false; $("expGo").hidden = true; $("expQueue").hidden = true;
    refreshQueue();
  } catch (err) { $("expErr").textContent = err.message; $("expGo").disabled = false; }
};


// ================================================================== kuyruk (toplu dışa aktarma)
let qTimer = null, QJOBS = [];
async function refreshQueue() {
  try { QJOBS = (await api("/api/jobs")).items; } catch (e) { return; }
  const open = QJOBS.filter(j => !j.done).length;
  if (!LIC.licensed && QJOBS.length) loadLicense();
  $("bQueue").hidden = !QJOBS.length; $("qCount").textContent = open || "✓";
  if ($("dQueue").open) renderQueue();
  clearTimeout(qTimer);
  if (open || $("dQueue").open) qTimer = setTimeout(refreshQueue, 1200);
}
const QSTAGE = { queued: "Sırada", silence: "Kesimler", transcribe: "Altyazı", render: "Video", done: "Hazır", error: "Hata" };
function renderQueue() {
  const box = $("qList"); box.innerHTML = QJOBS.length ? "" : '<div class="hint">Kuyruk boş.</div>';
  for (const j of [...QJOBS].reverse()) {
    const w = WEIGHT[j.stage], p = j.done ? 1 : w ? w[0] + (w[1] - w[0]) * j.progress : 0;
    const it = document.createElement("div"); it.className = "qi";
    const nm = document.createElement("b"); nm.textContent = (j.kind === "thumbnail" ? "🖼 " : "") + (j.label || "Klip");
    const st = document.createElement("span"); st.className = j.error ? "err" : j.done ? "ok" : "hint";
    st.textContent = j.error ? (j.error === "İptal edildi." ? "İptal edildi" : "Hata") : j.done ? "Hazır" : `${QSTAGE[j.stage] || j.stage} %${Math.round(p * 100)}`;
    it.append(nm, st);
    if (!j.done) { const bar = document.createElement("div"); bar.className = "bar"; bar.innerHTML = `<i style="width:${Math.round(p * 100)}%"></i>`; it.appendChild(bar); }
    const acts = document.createElement("div"); acts.className = "acts";
    const out = j.result && j.result.output;
    const btn = (label, fn, cls = "btn tiny") => { const b = document.createElement("button"); b.type = "button"; b.className = cls; b.textContent = label; b.onclick = fn; acts.appendChild(b); };
    if (out) { btn("Oynat", () => api("/api/play", { path: out }).catch(e => toast(e.message))); btn("Klasörde göster", () => api("/api/reveal", { path: out }).catch(e => toast(e.message))); btn("Telefona gönder", () => shareQr(out)); }
    if (j.stage === "queued" && !j.done) btn("İptal", async () => { await api("/api/cancel", { job: j.id }); toast("Sıradaki iş iptal edilecek"); }, "btn tiny ghost danger");
    if (j.error && j.error !== "İptal edildi.") { const e = document.createElement("div"); e.className = "hint"; e.style.gridColumn = "1/-1"; e.textContent = j.error.slice(0, 300); it.appendChild(e); }
    if (acts.children.length) it.appendChild(acts);
    box.appendChild(it);
  }
}
$("bQueue").onclick = () => { $("dQueue").showModal(); renderQueue(); refreshQueue(); };
$("qClose").onclick = () => $("dQueue").close();
$("qClear").onclick = async () => { await api("/api/jobs/clear", {}); refreshQueue(); };
$("qDir").onclick = async () => { const done = QJOBS.find(j => j.result && j.result.output); if (done) api("/api/reveal", { path: done.result.output }).catch(e => toast(e.message)); else toast("Henüz biten video yok"); };
async function enqueue(over, label) {
  const { job } = await api("/api/render", { project: project(over), label });
  refreshQueue(); return job;
}
$("expQueue").onclick = async () => {
  if (!media) return;
  try { await enqueue({ name: $("expName").value }, $("expName").value); $("dExp").close(); toast("Sıraya eklendi — üstteki Kuyruk'tan takip edebilirsin"); }
  catch (e) { $("expErr").textContent = e.message; }
};

// ================================================================== telefona gönder (QR)
async function shareQr(path) {
  try {
    const r = await api("/api/share", { path });
    $("qrBox").innerHTML = r.svg || '<div class="hint" style="color:#111;padding:20px">QR için "guncelle.bat" çalıştır (segno). Bağlantıyı telefona yazabilirsin.</div>';
    $("qrUrl").value = r.url; if (!$("dQr").open) $("dQr").showModal();
  } catch (e) { toast(e.message); }
}
$("expQr").onclick = () => lastOut && shareQr(lastOut);
$("qrClose").onclick = () => $("dQr").close();
$("qrCopy").onclick = () => { navigator.clipboard?.writeText($("qrUrl").value).then(() => toast("Kopyalandı"), () => { $("qrUrl").select(); }); };

// ================================================================== kapak
let thumbOut = null, thStyle = "title";
$("expThumb").onclick = () => {
  if (!media) return;
  $("thErr").textContent = ""; $("thImg").hidden = true; $("thReveal").hidden = $("thQr").hidden = true; $("thProg").hidden = true; $("thGo").disabled = false;
  if (!$("thTitle").value && S.hook.text) $("thTitle").value = S.hook.text;
  syncThumb(); $("dThumb").showModal();
};
function syncThumb() { segButtons($("thStyle"), [["title", "Büyük başlık"], ["box", "Beyaz kutu"]], thStyle, (id) => { thStyle = id; syncThumb(); }); }
$("thClose").onclick = () => $("dThumb").close();
$("thReveal").onclick = () => thumbOut && api("/api/reveal", { path: thumbOut }).catch(e => toast(e.message));
$("thQr").onclick = () => thumbOut && shareQr(thumbOut);
$("fThumb").onsubmit = async (e) => {
  e.preventDefault(); $("thErr").textContent = ""; $("thGo").disabled = true; $("thProg").hidden = false; $("thImg").hidden = true;
  try {
    const pr = project({ name: ($("expName").value || media.name.replace(/\.[^.]+$/, "")) });
    const { job } = await api("/api/thumbnail", { project: pr, title: $("thTitle").value, style: thStyle,
      time: $("thWhen").value === "now" ? v.currentTime : null, label: "Kapak" });
    refreshQueue();
    const j = await poll(job, () => {});
    if (j.error) throw new Error(j.error);
    thumbOut = j.result.output;
    $("thImg").src = "/media?path=" + encodeURIComponent(thumbOut) + "&t=" + Date.now(); $("thImg").hidden = false;
    $("thReveal").hidden = $("thQr").hidden = false;
  } catch (err) { $("thErr").textContent = err.message; }
  $("thProg").hidden = true; $("thGo").disabled = false;
};

// ================================================================== başlık / hashtag önerisi
$("bSug").onclick = async () => {
  const a = P.range.start ?? 0, b = P.range.end ?? (media ? media.duration : 0);
  const words = T ? T.chunks.flat().filter(w => w.start >= a - 0.5 && w.end <= b + 0.5) : [];
  const text = words.map(w => w.text).join(" ") + " " + S.hook.text;
  const plat = $("sugPlat").value, channel = S.tag ? S.tagText : "";
  try {
    const r = await api("/api/suggest", { text, language: T ? T.language : (S.lang || "tr"), platform: plat, channel, game: $("sugGame").value });
    const box = $("sugTitles"); box.innerHTML = "";
    for (const t of r.titles) { const bt = document.createElement("button"); bt.type = "button"; bt.className = "t"; bt.textContent = t;
      bt.onclick = () => navigator.clipboard?.writeText(t).then(() => toast("Başlık kopyalandı"), () => {}); box.appendChild(bt); }
    $("sugTags").value = r.hashtags.join(" "); $("sugTags").hidden = false;
    $("sugHint").textContent = words.length ? "Başlığa tıklayınca kopyalanır; hashtagleri düzenleyip kopyalayabilirsin." : "Altyazıyı önizlersen konuşulanlara göre daha iyi öneri çıkar.";
  } catch (e) { toast(e.message); }
};

// ================================================================== en iyi anlar
let HL = [], HLCURVE = [];
function syncAnlar() {
  $("bHl").disabled = !media;
  if (!media) $("hlStat").textContent = "Önce bir video aç.";
  renderHl();
}
async function findHighlights(opt = {}) {
  if (!media) return;
  const inRange = (opt.inRange ?? $("hlRange").checked) && (P.range.start != null || P.range.end != null);
  const a = inRange ? (P.range.start ?? 0) : 0, b = inRange ? (P.range.end ?? media.duration) : null;
  $("bHl").disabled = true; $("hlStat").className = "status"; $("hlStat").innerHTML = '<span class="spin"></span>Yayın taranıyor… %0';
  try {
    const words = T ? T.chunks.flat().map(w => ({ start: w.start, text: w.text })) : null;
    const { job } = await api("/api/highlights", { path: media.path, start: a, end: b, clip_len: opt.len || +$("hlLen").value || 45, count: opt.count || +$("hlCount").value || 6, words });
    const j = await poll(job, (j) => { $("hlStat").innerHTML = `<span class="spin"></span>Yayın taranıyor… %${Math.round(j.progress * 100)}`; });
    if (j.error) throw new Error(j.error);
    HL = j.result.items.map((h, i) => ({ ...h, id: uid(), n: i + 1, on: true })); HLCURVE = j.result.curve; HL.rangeA = a; HL.rangeB = b ?? media.duration;
    $("hlStat").className = "status ok";
    $("hlStat").innerHTML = HL.length ? `<span class="dot"></span>${HL.length} an bulundu · zaman çizelgesinde kırmızı` : "Belirgin bir heyecan anı bulunamadı. Klip uzunluğunu kısaltmayı dene.";
    renderHl(); drawTimeline();
  } catch (e) { $("hlStat").className = "status"; $("hlStat").textContent = "Taranamadı: " + e.message; }
  finally { $("bHl").disabled = !media; }
}
function renderHl() {
  const box = $("hlList"); box.innerHTML = HL.length ? "" : '<div class="hint">Henüz tarama yapılmadı.</div>';
  $("bHlAll").hidden = !HL.length;
  for (const h of HL) {
    const it = document.createElement("div"); it.className = "hl" + (h.on ? " sel" : "");
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = h.on; cb.setAttribute("aria-label", `An ${h.n} seçili`);
    cb.onchange = () => { h.on = cb.checked; renderHl(); };
    const nm = document.createElement("span"); nm.innerHTML = `<b>An ${h.n}</b> <span class="hint">${fmt(h.start)} – ${fmt(h.end)}</span>`;
    const lv = document.createElement("span"); lv.className = "lv " + (h.level === "çok yüksek" ? "l3" : h.level === "yüksek" ? "l2" : ""); lv.textContent = h.level;
    const acts = document.createElement("div"); acts.className = "acts";
    const b1 = document.createElement("button"); b1.type = "button"; b1.className = "btn tiny"; b1.textContent = "▶ Zirveyi izle";
    b1.onclick = () => { v.currentTime = Math.max(h.start, h.peak - 3); v.play(); };
    const b2 = document.createElement("button"); b2.type = "button"; b2.className = "btn tiny"; b2.textContent = "Klip aralığı yap";
    b2.onclick = () => { P.range = { start: h.start, end: h.end }; v.currentTime = h.start; view.a = Math.max(0, h.start - (h.end - h.start)); view.b = Math.min(media.duration, h.end + (h.end - h.start)); updRange(); toast(`Aralık: An ${h.n}`); };
    const b3 = document.createElement("button"); b3.type = "button"; b3.className = "btn tiny"; b3.textContent = "Dışa aktar";
    b3.onclick = () => exportMoments([h]);
    acts.append(b1, b2, b3);
    it.append(cb, nm, lv, acts); box.appendChild(it);
  }
  const n = HL.filter(h => h.on).length;
  $("bHlExp").disabled = !n; $("bHlExp").textContent = n ? `Seçilen ${n} anı dışa aktar` : "Seçilenleri dışa aktar";
}
async function exportMoments(list) {
  const base = media.name.replace(/\.[^.]+$/, "");
  try {
    for (const h of list) await enqueue({ range: { start: h.start, end: h.end }, name: `${base}_an${h.n}` }, `An ${h.n} · ${fmt(h.start)}`);
    toast(`${list.length} klip sıraya eklendi`); $("dQueue").showModal(); renderQueue(); refreshQueue();
  } catch (e) { toast(e.message); }
}
$("bHl").onclick = findHighlights;
$("bHlAll").onclick = () => { const all = HL.every(h => h.on); HL.forEach(h => h.on = !all); renderHl(); };
$("bHlExp").onclick = () => exportMoments(HL.filter(h => h.on));

// ================================================================== proje kaydet / aç / otomatik kayıt
function projectData() {
  return { version: 1, app: "streamchisel", media: { path: media.path, name: media.name }, S,
           P: { range: P.range, splits: P.splits, cuts: P.cuts, zooms: P.zooms, sfx: P.sfx }, T, HL: HL.map(h => ({ ...h })) };
}
let loadingProject = false;
function loadProject(d) {
  const keepTab = S.tab;
  S = deepMerge(structuredClone(DEF), d.S || {}); S.tab = keepTab === "medya" ? "kadraj" : keepTab;
  loadingProject = true;
  setMedia(d.media);
  Object.assign(P, d.P || {}); P.undo = [];
  T = d.T || null; HL = d.HL || []; HLCURVE = [];
  applyFormat(); syncAll(); updTrStatus(); renderHl(); renderZoomList(); updRange(); save();
  if (S.music) $("musA").src = "/media?path=" + encodeURIComponent(S.music.path);
  refreshLogo();
}
async function renderProjects() {
  const box = $("projList"); box.innerHTML = '<div class="hint">Yükleniyor…</div>';
  try {
    const r = await api("/api/projects"); box.innerHTML = r.items.length ? "" : '<div class="hint">Henüz kayıtlı proje yok.</div>';
    for (const it of r.items) {
      const row = document.createElement("button"); row.type = "button"; row.className = "item"; row.style.textAlign = "left";
      row.innerHTML = `<span class="nm">${escHtml(it.name)}</span><span class="tm">${escHtml(it.video || "")} · ${new Date(it.saved * 1000).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" })}</span>`;
      row.onclick = () => openProject(it.path);
      box.appendChild(row);
    }
  } catch (e) { box.textContent = e.message; }
}
async function openProject(path, picked) {
  try { const r = await api("/api/project/open", { path, picked: !!picked }); loadProject(r.data); $("projName").value = r.name; $("dProj").close(); toast(`"${r.name}" açıldı`); }
  catch (e) { toast(e.message); }
}
$("bProj").onclick = () => { $("projName").value = $("projName").value || (media ? media.name.replace(/\.[^.]+$/, "") : ""); $("projSave").disabled = !media; renderProjects(); $("dProj").showModal(); };
$("projClose").onclick = () => $("dProj").close();
$("fProj").onsubmit = async (e) => {
  e.preventDefault(); if (!media) return;
  try { const r = await api("/api/project/save", { name: $("projName").value || media.name, data: projectData() }); toast(`Proje kaydedildi: ${r.name}`); renderProjects(); }
  catch (err) { toast(err.message); }
};
$("projPick").onclick = async () => { try { const r = await api("/api/project/pick", {}); if (r.path) openProject(r.path, true); } catch (e) { toast(e.message); } };
document.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); $("bProj").click(); } });
setInterval(() => { if (media) api("/api/autosave", { data: projectData() }).catch(() => {}); }, 20000);
window.addEventListener("beforeunload", () => { if (media) navigator.sendBeacon?.("/api/autosave", new Blob([JSON.stringify({ data: projectData() })], { type: "application/json" })); });
$("bDemo").onclick = async () => {
  try { const r = await api("/api/demo", {}); loadProject(r.data); toast("Örnek yayın açıldı — Dışa aktar'a basıp sonucu gör ya da ✨ Hızlı klip'i dene"); }
  catch (e) { toast(e.message); }
};
async function checkResume() {
  try {
    const r = await api("/api/autosave"); const d = r.data;
    if (!d || !d.media) return;
    $("bResume").hidden = false; $("bResume").textContent = `Son çalışmaya devam et: ${d.media.name}`;
    $("bResume").onclick = async () => { try { d.media = await api("/api/open", { path: d.media.path }); loadProject(d); } catch (e) { toast(e.message); } };
  } catch (e) {}
}


// ================================================================== hızlı klip sihirbazı
const WZ = { step: 1, mode: null };
function openWizard() {
  if (!media) return;
  const long = media.duration > 180, hasRange = P.range.start != null || P.range.end != null;
  WZ.step = 1; WZ.mode = long && !hasRange ? "moments" : "single"; $("wzNext").onclick = null;
  $("wzInfo").textContent = `${media.name} · ${fmt(media.duration)}`;
  $("wzRec").textContent = long ? "ÖNERİLEN" : "";
  $("wzSingleTxt").textContent = hasRange ? `Seçtiğin aralığı (${fmt(P.range.start ?? 0)} – ${fmt(P.range.end ?? media.duration)}) dikey videoya çevirir.`
    : long ? "Videonun tamamını tek dikey videoya çevirir. Uzun videoda önce aralık seçmen önerilir." : "Videonun tamamını tek dikey videoya çevirir.";
  $("wzSubs").checked = S.subs; $("wzSil").checked = S.silence; $("wzLang").value = S.lang; $("wzHook").value = S.hook.text;
  $("wzAuto").checked = S.wizAuto !== false; $("wzErr").textContent = "";
  wzShow(); if (!$("dWiz").open) $("dWiz").showModal();
}
function wzShow() {
  for (const sec of $("fWiz").querySelectorAll("section[data-step]")) sec.hidden = +sec.dataset.step !== WZ.step;
  [...$("fWiz").querySelectorAll(".wz-steps i")].forEach((el, i) => el.classList.toggle("on", i < Math.min(3, WZ.step)));
  for (const m of $("fWiz").querySelectorAll(".mode")) { m.classList.toggle("on", m.dataset.mode === WZ.mode); m.setAttribute("aria-pressed", m.dataset.mode === WZ.mode); }
  renderPacks($("wzPacks"), (id) => { S.pack = id; wzShow(); });
  segButtons($("wzFmt"), Object.keys(FORMATS).map(k => [k, k]), S.format, (id) => { S.format = id; wzShow(); });
  $("wzMomRow").hidden = WZ.mode !== "moments";
  $("wzBack").hidden = WZ.step === 1 || WZ.step === 4;
  $("wzSkip").hidden = WZ.step === 4;
  $("wzNext").hidden = false;
  $("wzNext").textContent = WZ.step === 3 ? (WZ.mode === "moments" ? "Klipleri oluştur" : "Klibi oluştur") : WZ.step === 4 ? "Kapat" : "İleri";
  $("wzNext").disabled = WZ.step === 2 && !S.pack;
}
for (const m of document.querySelectorAll("#fWiz .mode")) m.onclick = () => { WZ.mode = m.dataset.mode; wzShow(); };
$("wzBack").onclick = () => { WZ.step = Math.max(1, WZ.step - 1); wzShow(); };
$("wzSkip").onclick = () => $("dWiz").close();
$("wzAuto").onchange = (e) => { S.wizAuto = e.target.checked; save(); };
$("bWiz").onclick = openWizard;
$("fWiz").onsubmit = async (e) => {
  e.preventDefault();
  if (WZ.step === 4) { $("dWiz").close(); return; }
  if (WZ.step < 3) { WZ.step++; if (WZ.step === 2 && !S.pack) S.pack = "enerjik"; wzShow(); return; }
  // uygula ve oluştur
  const fmtSel = S.format, pack = S.pack;
  applyPack(pack); S.format = fmtSel; applyFormat(); relockAll();
  S.subs = $("wzSubs").checked; S.lang = $("wzLang").value; S.silence = $("wzSil").checked;
  const hook = $("wzHook").value.trim(); S.hook.text = hook; S.hook.on = !!hook;
  save(); syncAll(); WZ.step = 4; wzShow(); $("wzNext").hidden = true; $("wzErr").textContent = "";
  try {
    if (S.autoCam && (S.preset === "stack" || S.preset === "focus") && !$("detStat").hidden && $("detStat").querySelector(".spin")) {
      $("wzStat").innerHTML = '<span class="spin"></span>Kamera aranıyor…';
      for (let i = 0; i < 80 && $("detStat").querySelector(".spin"); i++) await new Promise(r => setTimeout(r, 250));
    }
    if (WZ.mode === "moments") {
      $("hlLen").value = $("wzLen").value; $("hlCount").value = $("wzCount").value;
      $("wzDoneT").textContent = "En iyi anlar aranıyor…";
      const tick = setInterval(() => { $("wzStat").innerHTML = $("hlStat").innerHTML; }, 300);
      try { await findHighlights({ len: +$("wzLen").value, count: +$("wzCount").value, inRange: false }); } finally { clearInterval(tick); }
      if (!HL.length) throw new Error("Belirgin bir heyecan anı bulunamadı. Tek klip modunu dene ya da klip uzunluğunu kısalt.");
      HL.forEach(h => h.on = true); renderHl();
      const base = media.name.replace(/\.[^.]+$/, "");
      for (const h of HL) await enqueue({ range: { start: h.start, end: h.end }, name: `${base}_an${h.n}` }, `An ${h.n} · ${fmt(h.start)}`);
      $("wzDoneT").textContent = `${HL.length} klip sıraya eklendi 🎉`;
    } else {
      await enqueue({ name: media.name.replace(/\.[^.]+$/, "") + "_dikey" }, media.name.replace(/\.[^.]+$/, ""));
      $("wzDoneT").textContent = "Klip sıraya eklendi 🎉";
    }
    $("wzStat").className = "status ok";
    $("wzStat").innerHTML = '<span class="dot"></span>Videolar sırayla oluşturuluyor. Üstteki <b>Kuyruk</b>\'tan takip edebilir, bu arada editörde düzenlemeye devam edebilirsin.';
    $("wzNext").hidden = false; $("wzNext").textContent = "Kuyruğu göster";
    $("wzNext").onclick = (ev) => { ev.preventDefault(); $("dWiz").close(); $("wzNext").onclick = null; $("bQueue").click(); };
  } catch (err) { $("wzErr").textContent = err.message; WZ.step = 3; wzShow(); }
};


// ================================================================== lisans
let LIC = { mode: "dev", licensed: true };
async function loadLicense(refresh) {
  try { LIC = refresh ? await api("/api/license/refresh", {}) : await api("/api/license"); } catch (e) { return; }
  syncLicense();
}
function freeText() {
  if (LIC.licensed) return "";
  const left = LIC.left_today ?? 0;
  return `Ücretsiz sürüm: videonun köşesinde küçük "Streamchisel" yazısı olur · bugün <b>${left}/${LIC.free_daily}</b> video hakkın kaldı.` + (LIC.buy_url ? ` <a id="freeBuy">Lisans al →</a>` : "");
}
function syncLicense() {
  const b = $("bLic"); b.hidden = LIC.mode === "dev";
  const left = (sec) => { sec = Math.max(0, sec); const d = Math.floor(sec / 86400), h = Math.floor(sec % 86400 / 3600), m = Math.floor(sec % 3600 / 60);
    return d ? `${d} gün ${h} saat` : h ? `${h} saat ${m} dk` : `${m} dk`; };
  const trial = LIC.mode === "trial", tl = trial ? (LIC.expires - Date.now() / 1000) : 0;
  b.classList.toggle("free", !LIC.licensed || (trial && tl < 6 * 3600));
  b.textContent = trial ? `Deneme · ${left(tl)} kaldı` : LIC.licensed ? "✓ Lisanslı" : LIC.mode === "expired" ? "Deneme bitti · Lisans al" : "Ücretsiz sürüm";
  const box = $("licBox");
  if (trial) box.innerHTML = `<b class="big">Deneme sürümü</b><span class="hint">Kalan süre: <b>${left(tl)}</b> · Bitiş: ${new Date(LIC.expires * 1000).toLocaleString("tr-TR", { dateStyle: "medium", timeStyle: "short" })}</span><span class="hint">Deneme boyunca her şey sınırsız ve yazısız. Süre bitince program ücretsiz sürüme döner; beğendiysen lisans anahtarını buraya gir.</span>`;
  else if (LIC.licensed) box.innerHTML = `<b class="big">✓ Lisanslı</b><span class="hint">Anahtar: <code>${escHtml(LIC.key || "")}</code> · Ömür boyu</span><span class="hint">Sınırsız video, filigran yok, tüm güncellemeler dahil.</span>`;
  else box.innerHTML = `<b class="big">Ücretsiz sürüm</b><span class="hint">${LIC.message ? escHtml(LIC.message) + "<br>" : ""}Tüm özellikleri deneyebilirsin. Günde ${LIC.free_daily ?? 3} video, köşede küçük "Streamchisel" yazısıyla.</span><span class="hint">Bugün kalan: <b>${LIC.left_today ?? 0}</b></span>`;
  $("licForm").hidden = LIC.licensed && !trial; $("licGo").hidden = LIC.licensed && !trial; $("licOff").hidden = !LIC.licensed || trial;
  $("licBuy").hidden = (LIC.licensed && !trial) || !LIC.buy_url;
  $("licVer").textContent = "Sürüm " + (LIC.version || "");
  const up = LIC.update;
  if (up && localStorage.getItem("sc.skipUpdate") !== up.version) {
    $("updTxt").textContent = `Yeni sürüm hazır: ${up.version}` + (up.notes ? ` — ${up.notes.split("\n")[0].slice(0, 120)}` : "");
    $("updBar").hidden = false;
  } else $("updBar").hidden = true;
}
const openUrl = (url) => api("/api/openurl", { url }).catch(e => toast(e.message));
$("bLic").onclick = () => { $("licErr").textContent = ""; syncLicense(); $("dLic").showModal(); loadLicense(true); };
$("licClose").onclick = () => $("dLic").close();
$("licBuy").onclick = () => LIC.buy_url && openUrl(LIC.buy_url);
$("fLic").onsubmit = async (e) => {
  e.preventDefault(); $("licErr").textContent = ""; $("licGo").disabled = true;
  try {
    LIC = { ...LIC, ...(await api("/api/license/activate", { key: $("licKey").value })) }; syncLicense(); $("licKey").value = "";
    toast(LIC.mode === "trial" ? "Deneme başladı — iyi kullanımlar! 🎬" : "Lisans etkinleştirildi. Teşekkürler! 🎉"); loadLicense();
  }
  catch (err) { $("licErr").textContent = err.message; }
  $("licGo").disabled = false;
};
$("licOff").onclick = async () => {
  if (!confirm("Lisans bu bilgisayardan kaldırılsın mı? Başka bilgisayarda kullanmak için yer açılır.")) return;
  try { LIC = { ...LIC, ...(await api("/api/license/deactivate", {})) }; syncLicense(); toast("Lisans bu bilgisayardan kaldırıldı"); }
  catch (err) { $("licErr").textContent = err.message; }
};
$("updGo").onclick = () => LIC.update && openUrl(LIC.update.url);
$("updLater").onclick = () => { try { localStorage.setItem("sc.skipUpdate", LIC.update.version); } catch (e) {} $("updBar").hidden = true; };
document.addEventListener("click", (e) => { if (e.target.id === "freeBuy") { e.preventDefault(); openUrl(LIC.buy_url); } });

// ================================================================== başlangıç
function renderAll() { syncKadraj(); renderRects(); renderOutOv(); drawTimeline(); updRange(); renderSfxList(); }
function syncAll() { applyFormat(); syncSnap(); syncAnlar(); $("bSafe").setAttribute("aria-pressed", S.safe); $("bSafe").classList.toggle("primary", !!S.safe); renderRail(); showTab(); syncKadraj(); syncAltyazi(); syncLogoPanel(); syncSes(); syncRenk(); renderRects(); renderOutOv(); drawTimeline(); }
(async function init() {
  let st = {};
  try { st = await api("/api/state"); } catch (e) {}
  let s = st.settings;
  if (!s) { try { s = JSON.parse(localStorage.getItem("streamchisel.settings") || "null"); } catch (e) {} }
  if (s) S = deepMerge(structuredClone(DEF), s);
  LAYOUTS = st.layouts || [];
  try { SFXLIB = (await api("/api/sfx")).items; } catch (e) {}
  if (S.music) $("musA").src = "/media?path=" + encodeURIComponent(S.music.path);
  renderRecent(st.recent || []); renderLayouts(); syncAll();
  document.fonts.ready.then(() => { syncLogoPanel(); refreshLogo(); });
  requestAnimationFrame(frame);
  checkResume(); refreshQueue(); loadLicense(); setTimeout(() => loadLicense(), 8000); setInterval(() => loadLicense(), 60000);
})();
