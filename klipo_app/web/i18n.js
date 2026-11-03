// Arayüz dili: Türkçe yazılmış arayüzü seçilen dile (İngilizce / Rusça) çevirir.
// Kaynak metinler Türkçe kalır; ekrana gelen her yazı (sonradan eklenenler dahil) sözlükten çevrilir.
// Sözlük: i18n/en.json, i18n/ru.json → {"tam": {türkçe: çeviri}, "kalip": [[türkçe {0}, çeviri {0}], ...]}
(function () {
  const ATTRS = ["placeholder", "title", "aria-label"];
  const I18N = { lang: "tr", exact: new Map(), pats: [] };
  window.I18N = I18N;

  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  function compile(src) {
    const parts = src.split(/\{(\d)\}/);
    let re = "^";
    for (let i = 0; i < parts.length; i++) re += i % 2 ? "([\\s\\S]+?)" : esc(parts[i]);
    return new RegExp(re + "$");
  }

  function tr(s) {
    if (I18N.lang === "tr" || !s) return s;
    const m = s.match(/^(\s*)([\s\S]*?)(\s*)$/), core = m[2];
    if (!core || !/[A-Za-zÇĞİÖŞÜçğıöşü]/.test(core)) return s;
    let out = I18N.exact.get(core);
    if (out === undefined) {
      for (const [re, to] of I18N.pats) {
        const g = core.match(re);
        if (g) { out = to.replace(/\{(\d)\}/g, (_, i) => tr(g[+i + 1])); break; }
      }
    }
    return out === undefined ? s : m[1] + out + m[3];
  }
  I18N.t = tr;

  // Her metin düğümü / özellik için: Türkçe aslı ve en son bizim yazdığımız değer.
  // Ekrandaki değer ikisinden de farklıysa uygulama yeni bir metin yazmıştır → yeni asıl budur.
  // (Yalnızca "şu anki dilin çevirisi" ile karşılaştırmak dil değiştirirken eski dili asıl sanıyordu.)
  const orig = new WeakMap();
  function doText(n) {
    let o = orig.get(n);
    if (!o || (n.nodeValue !== o.src && n.nodeValue !== o.out)) { o = { src: n.nodeValue, out: n.nodeValue }; orig.set(n, o); }
    const want = tr(o.src);
    o.out = want;
    if (n.nodeValue !== want) n.nodeValue = want;
  }
  const origAttr = new WeakMap();
  function doEl(el) {
    for (const a of ATTRS) {
      if (!el.hasAttribute(a)) continue;
      let m = origAttr.get(el);
      if (!m) { m = {}; origAttr.set(el, m); }
      const cur = el.getAttribute(a);
      let o = m[a];
      if (!o || (cur !== o.src && cur !== o.out)) { o = m[a] = { src: cur, out: cur }; }
      const want = tr(o.src);
      o.out = want;
      if (cur !== want) el.setAttribute(a, want);
    }
  }
  function walk(root) {
    if (root.nodeType === 3) { doText(root); return; }
    if (root.nodeType !== 1 || root.closest?.("[data-no-tr]")) return;
    if (root.tagName === "SCRIPT" || root.tagName === "STYLE") return;
    doEl(root);
    const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      if (n.nodeType === 3) { const p = n.parentElement; if (p && !p.closest("script,style,[data-no-tr]")) doText(n); }
      else if (!n.closest("[data-no-tr]")) doEl(n);
    }
  }

  let busy = false;
  const obs = new MutationObserver((list) => {
    if (busy || I18N.lang === "tr") return;
    busy = true;
    try {
      for (const r of list) {
        if (r.type === "characterData") doText(r.target);
        else if (r.type === "attributes") doEl(r.target);
        else r.addedNodes.forEach(walk);
      }
    } finally { busy = false; }
  });

  I18N.set = async function (lang) {
    lang = ["tr", "en", "ru"].includes(lang) ? lang : "tr";
    if (lang !== "tr") {
      try {
        const d = await (await fetch(`/static/i18n/${lang}.json`)).json();
        I18N.exact = new Map(Object.entries(d.tam || {}));
        I18N.pats = (d.kalip || []).map(([a, b]) => [compile(a), b]);
      } catch (e) { console.warn("dil dosyası yüklenemedi", e); lang = "tr"; }
    }
    I18N.lang = lang;
    document.documentElement.lang = lang;
    busy = true;
    try { walk(document.body); } finally { busy = false; }
    // Türkçe'ye dönüşte saklanan asıllar kullanılır (tr() kimlik döndürür)
  };

  obs.observe(document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
})();
