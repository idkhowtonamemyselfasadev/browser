// What a themed website reads like, measured in the page itself.
//
// Run in the main world after the site theme has settled. It walks
// every element that shows text of its own, works out what colour the
// text is really drawn in (-webkit-text-fill-color, alpha blended,
// through any opacity on the way up) and what is really behind it (the
// first opaque background walking up, translucent ones blended over
// it; a photo or a gradient means "cannot be judged"), and measures
// the WCAG contrast between the two. It returns totals weighted by the
// number of characters -- one unreadable headline matters more than
// one unreadable footnote -- and a list of the worst offenders with
// where they are on screen, so the rig can look at the pixels there
// as well. Form fields and placeholders are measured the same way.
//
// This is the measuring tape, not the paint: it must never change the
// page, and it must not trust the theme's own bookkeeping.
(function () {
  function p(s) {
    s = s || "";
    var m = /rgba?\(([\d.]+)[, ]+([\d.]+)[, ]+([\d.]+)(?:[,/ ]+([\d.]+%?))?\)/.exec(s);
    if (!m) return null;
    var a = m[4] === undefined ? 1
      : (m[4].indexOf("%") >= 0 ? parseFloat(m[4]) / 100 : parseFloat(m[4]));
    return { r: +m[1], g: +m[2], b: +m[3], a: isNaN(a) ? 1 : a };
  }
  function over(t, u) {
    var a = t.a;
    return { r: t.r * a + u.r * (1 - a), g: t.g * a + u.g * (1 - a),
             b: t.b * a + u.b * (1 - a), a: 1 };
  }
  function ch(v) { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }
  function L(c) { return .2126 * ch(c.r) + .7152 * ch(c.g) + .0722 * ch(c.b); }
  function ratio(a, b) {
    var x = L(a) + .05, y = L(b) + .05;
    return x > y ? x / y : y / x;
  }
  function hex(c) {
    function h(v) { v = Math.round(v); return (v < 16 ? "0" : "") + v.toString(16); }
    return "#" + h(c.r) + h(c.g) + h(c.b);
  }
  var csCache = new Map();
  function cs(el) {
    var c = csCache.get(el);
    if (c === undefined) { try { c = getComputedStyle(el); } catch (e) { c = null; } csCache.set(el, c); }
    return c;
  }
  var WHITE = { r: 255, g: 255, b: 255, a: 1 };
  var htmlBg = p(cs(document.documentElement).backgroundColor);
  var canvas = (htmlBg && htmlBg.a > .995) ? htmlBg : WHITE;
  if (htmlBg && htmlBg.a > .004 && htmlBg.a <= .995) canvas = over(htmlBg, WHITE);

  // what is behind an element, and how see-through the way up is
  var bgCache = new Map();
  function behind(el) {
    var stack = [], n = el, hit;
    while (n && n.nodeType === 1) {
      var known = bgCache.get(n);
      if (known !== undefined) { hit = known; break; }
      var s = cs(n);
      if (!s) break;
      var bgi = s.backgroundImage;
      // a gradient cut into an element's own letters (background-clip:
      // text) is ink, not a backdrop for what is inside it
      if (bgi && bgi !== "none" && (bgi.indexOf("url(") >= 0 || bgi.indexOf("gradient") >= 0)
          && !clipped(s)) {
        hit = null; break;
      }
      var c = p(s.backgroundColor);
      if (c && c.a > .004) {
        if (c.a > .995) { hit = c; break; }
        stack.push(c);
      }
      n = n.parentElement;
    }
    if (hit === undefined) hit = canvas;
    if (hit === null) { bgCache.set(el, null); return null; }
    for (var i = stack.length - 1; i >= 0; i--) hit = over(stack[i], hit);
    bgCache.set(el, hit);
    return hit;
  }
  var opCache = new Map();
  function opacityOf(el) {
    var known = opCache.get(el);
    if (known !== undefined) return known;
    var s = cs(el), own = s ? parseFloat(s.opacity) : 1;
    if (isNaN(own)) own = 1;
    var up = el.parentElement ? opacityOf(el.parentElement) : 1;
    var o = own * up;
    opCache.set(el, o);
    return o;
  }
  var vw = window.innerWidth, vh = window.innerHeight;

  var clipped = function (st) {
    return ((st.webkitBackgroundClip || st.backgroundClip || "") + "").indexOf("text") >= 0;
  };
  var out = { chars: 0, judged: 0, bad: 0, weak: 0, unjudged: 0,
              elements: 0, badElements: 0, inputs: 0, badInputs: 0,
              iframes: 0, worst: [], boxes: [], themed: !!document.getElementById("__sitetheme"),
              bodyBg: cs(document.body || document.documentElement).backgroundColor,
              htmlBg: cs(document.documentElement).backgroundColor,
              title: (document.title || "").slice(0, 80), url: location.href.slice(0, 160) };
  var FIELD = { INPUT: 1, TEXTAREA: 1, SELECT: 1 };
  var SKIP = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, TEMPLATE: 1, SVG: 1, svg: 1, TITLE: 1, HEAD: 1, META: 1, LINK: 1 };
  var all = document.querySelectorAll("body *");
  var hits = [];
  for (var i = 0; i < all.length; i++) {
    var el = all[i];
    if (SKIP[el.tagName] === 1) continue;
    var text = "";
    var isField = FIELD[el.tagName] === 1;
    if (isField) {
      text = el.tagName === "SELECT" ? (el.options[el.selectedIndex] || {}).text || "" : (el.value || "");
      if (el.type === "hidden" || el.type === "checkbox" || el.type === "radio"
          || el.type === "range" || el.type === "color" || el.type === "file") continue;
    } else {
      for (var k = 0; k < el.childNodes.length; k++) {
        var n = el.childNodes[k];
        if (n.nodeType === 3) text += n.nodeValue;
      }
      text = text.replace(/\s+/g, " ").trim();
      if (!text && !isField) continue;
    }
    var s = cs(el);
    if (!s || s.visibility === "hidden" || s.display === "none") continue;
    var r;
    try { r = el.getBoundingClientRect(); } catch (e) { continue; }
    if (r.width < 2 || r.height < 2) continue;
    if (r.right < 0 || r.bottom < 0) continue;              // parked off the page
    var fs = parseFloat(s.fontSize);
    if (fs < 6) continue;
    if (s.clip && s.clip.indexOf("rect(0px, 0px, 0px, 0px)") >= 0) continue;
    if (parseFloat(s.textIndent) < -999) continue;
    var op = opacityOf(el);
    if (op < .08) continue;
    var fg = p(s.webkitTextFillColor) || p(s.color);
    if (!fg) continue;
    // letters cut out of a gradient (background-clip: text over a
    // transparent fill): the gradient's stops are the ink, and the
    // worst of them is what is judged; a photo cut into letters
    // cannot be judged and is skipped
    var stops = null, inherited = false;
    if (fg.a < .08 && !isField) {
      // the gradient may be the element's own, or an ancestor's (the
      // words of such a headline are spans with an inherited
      // transparent fill)
      var g = el, gs = s, guardG = 0;
      while (g && guardG++ < 7) {
        var bgiT = gs.backgroundImage;
        var clipT = (gs.webkitBackgroundClip || gs.backgroundClip || "") + "";
        if (bgiT && bgiT !== "none") {
          if (bgiT.indexOf("gradient") >= 0 && clipT.indexOf("text") >= 0) {
            stops = [];
            var mm, reT = /rgba?\([^)]*\)/g;
            while ((mm = reT.exec(bgiT)) && stops.length < 12) {
              var sc = p(mm[0]);
              if (sc && sc.a > .08) stops.push(sc);
            }
            inherited = g !== el;
          }
          break;
        }
        g = g.parentElement; gs = g ? cs(g) : null;
        if (!gs) break;
      }
      if (!stops || !stops.length) continue;
    }
    var chars = isField ? Math.max(text.length, 8) : text.length;
    // a field's own fill is what its text sits on; and on screen the
    // stack under one point of the text is asked as well, the same
    // way the pass asks it: a picture lying under the element that
    // is not an ancestor is still what the text sits on
    var bg = behind(stops && !inherited && el.parentElement ? el.parentElement : el);
    var inView0 = r.top < vh && r.left < vw && r.bottom > 0 && r.right > 0;
    if (inView0 && document.elementsFromPoint) {
      var px = Math.min(Math.max(r.left + Math.min(r.width / 2, 12), 0), vw - 1);
      var py = Math.min(Math.max(r.top + Math.min(r.height / 2, 10), 0), vh - 1);
      var stack = null;
      try { stack = document.elementsFromPoint(px, py); } catch (e) {}
      if (stack) {
        var belowSelf = false;
        for (var q = 0; q < stack.length; q++) {
          var e2 = stack[q];
          if (e2 === el) { belowSelf = true; continue; }
          if (!belowSelf) continue;
          var s2 = cs(e2);
          if (!s2) continue;
          var bgi2 = s2.backgroundImage;
          var pic2 = bgi2 && bgi2 !== "none" && (bgi2.indexOf("url(") >= 0 || bgi2.indexOf("gradient") >= 0)
                     && !clipped(s2);
          if (e2.contains(el)) {
            if (pic2) { bg = null; break; }
            var ac = p(s2.backgroundColor);
            if (ac && ac.a > .995) break;
            continue;
          }
          if (/^(IMG|PICTURE|CANVAS|VIDEO|svg|SVG)$/.test(e2.tagName) || pic2) { bg = null; break; }
          var c2 = p(s2.backgroundColor);
          if (c2 && c2.a > .995) { bg = c2; break; }
        }
      }
    }
    if (isField) { out.inputs++; }
    out.elements++;
    out.chars += chars;
    if (!bg) { out.unjudged += chars; continue; }
    if (stops) {
      var worstC = 99;
      for (var si = 0; si < stops.length; si++) {
        var sb = stops[si].a < .995 ? over(stops[si], bg) : stops[si];
        var rc = ratio(sb, bg);
        if (rc < worstC) { worstC = rc; fg = sb; }
      }
    }
    if (fg.a < .995) fg = over(fg, bg);
    if (op < 1) fg = over({ r: fg.r, g: fg.g, b: fg.b, a: op }, bg);
    var c = ratio(fg, bg);
    out.judged += chars;
    var inView = r.top < vh && r.left < vw && r.bottom > 0 && r.right > 0;
    if (c < 3) { out.bad += chars; out.badElements++; if (isField) out.badInputs++; }
    else if (c < 4.5) out.weak += chars;
    var row = { tag: el.tagName, id: (el.id || "").slice(0, 30),
                cls: (typeof el.className === "string" ? el.className : "").slice(0, 40),
                text: text.slice(0, 50), fg: hex(fg), bg: hex(bg), ratio: Math.round(c * 100) / 100,
                chars: chars, fs: fs, inView: inView,
                rect: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)] };
    if (c < 4.5) hits.push(row);
    // a placeholder is text too, and the one most often lost
    if (isField && !el.value && el.placeholder) {
      var ps = null;
      try { ps = getComputedStyle(el, "::placeholder"); } catch (e) {}
      var pc = ps && (p(ps.webkitTextFillColor) || p(ps.color));
      if (pc) {
        if (pc.a < .995) pc = over(pc, bg);
        var pr = ratio(pc, bg);
        var n2 = el.placeholder.length;
        out.chars += n2; out.judged += n2;
        if (pr < 3) { out.bad += n2; out.badElements++; out.badInputs++; }
        else if (pr < 4.5) out.weak += n2;
        if (pr < 4.5) hits.push({ tag: "PLACEHOLDER", id: (el.id || "").slice(0, 30),
          cls: (typeof el.className === "string" ? el.className : "").slice(0, 40),
          text: el.placeholder.slice(0, 50), fg: hex(pc), bg: hex(bg),
          ratio: Math.round(pr * 100) / 100, chars: n2, fs: fs, inView: inView,
          rect: row.rect });
      }
    }
    // the boxes the rig looks at in the screenshot: visible text, in view
    if (inView && chars >= 3 && r.width >= 16 && r.height >= 8 && r.height <= 120
        && out.boxes.length < 400)
      out.boxes.push([Math.max(0, Math.round(r.left)), Math.max(0, Math.round(r.top)),
                      Math.round(Math.min(r.right, vw) - Math.max(0, r.left)),
                      Math.round(Math.min(r.bottom, vh) - Math.max(0, r.top)),
                      hex(fg), hex(bg), Math.round(c * 10) / 10, text.slice(0, 24)]);
  }
  hits.sort(function (a, b) { return (a.ratio - b.ratio) || (b.chars - a.chars); });
  out.worst = hits.slice(0, 40);
  var frames = document.querySelectorAll("iframe");
  var fr = [];
  for (var f = 0; f < frames.length; f++) {
    var fr0 = frames[f].getBoundingClientRect();
    if (fr0.width > 60 && fr0.height > 40 && fr0.top < vh && fr0.left < vw) {
      out.iframes++;
      if (fr.length < 6) fr.push((frames[f].src || "").slice(0, 80));
    }
  }
  out.iframeSrcs = fr;
  return JSON.stringify(out);
})()
