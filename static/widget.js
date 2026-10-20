(function () {
  var s = document.currentScript, key = s.getAttribute("data-key"), base = new URL(s.src).origin;
  fetch(base + "/api/widget/" + key).then(function (r) { return r.json(); }).catch(function () { return {}; }).then(function (c) { start(c || {}); });
  function start(cfg) {
  var color = cfg.color || s.getAttribute("data-color") || "#4f46e5";
  var api = base + "/api/chat/" + key, SK = "sb_" + key, sess, msgs = [], isOpen = false;
  try { sess = localStorage.getItem("sb_s") || (localStorage.setItem("sb_s", Math.random().toString(36).slice(2)), localStorage.getItem("sb_s")); } catch (e) { sess = "anon"; }
  try { var st = JSON.parse(sessionStorage.getItem(SK) || "{}"); msgs = st.msgs || []; isOpen = !!st.open; } catch (e) {}
  function save() { try { sessionStorage.setItem(SK, JSON.stringify({ msgs: msgs.slice(-30), open: isOpen })); } catch (e) {} }
  var css = document.createElement("style");
  css.textContent = ".sb-b{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border-radius:50%;border:0;background:" + color + ";color:#fff;font-size:26px;cursor:pointer;box-shadow:0 4px 16px #0003;z-index:99999}" +
    ".sb-p{position:fixed;right:20px;bottom:88px;width:360px;max-width:calc(100vw - 40px);height:480px;max-height:70vh;background:#fff;border-radius:14px;box-shadow:0 8px 32px #0003;display:none;flex-direction:column;overflow:hidden;font:14px system-ui,sans-serif;z-index:99999}" +
    ".sb-h{background:" + color + ";color:#fff;padding:14px;font-weight:600}.sb-m{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:8px;background:#f8fafc}" +
    ".sb-x{max-width:85%;padding:8px 12px;border-radius:12px;white-space:pre-wrap;line-height:1.4}.sb-u{align-self:flex-end;background:" + color + ";color:#fff}.sb-a{align-self:flex-start;background:#fff;border:1px solid #e2e8f0;color:#111}" +
    ".sb-go{display:inline-block;margin:6px 6px 0 0;padding:7px 12px;border:0;border-radius:99px;background:" + color + ";color:#fff;font:600 13px system-ui,sans-serif;cursor:pointer}" +
    ".sb-fb{font-size:12px;color:#64748b;margin-top:6px}.sb-fb button{border:0;background:none;cursor:pointer;font-size:15px;padding:0 4px}.sb-lead input{display:block;width:100%;box-sizing:border-box;margin:4px 0;padding:7px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}.sb-lead .sb-go{margin:4px 0 0}" +
    ".sb-f{display:flex;border-top:1px solid #e2e8f0}.sb-f input{flex:1;border:0;padding:14px;font:inherit;outline:0}.sb-f button{border:0;background:none;color:" + color + ";font-weight:600;padding:0 14px;cursor:pointer}" +
    "@keyframes sbp{0%,100%{box-shadow:0 0 0 0 " + color + "99}50%{box-shadow:0 0 0 10px " + color + "00}}" +
    ".sb-hl{outline:3px solid " + color + "!important;outline-offset:3px!important;border-radius:6px;animation:sbp 1s infinite;position:relative;z-index:99990}" +
    ".sb-tip{position:absolute;background:" + color + ";color:#fff;font:600 12px system-ui,sans-serif;padding:4px 9px;border-radius:6px;z-index:99998;white-space:nowrap;pointer-events:none}";
  document.head.appendChild(css);
  function el(t, c, x) { var e = document.createElement(t); if (c) e.className = c; if (x) e.textContent = x; return e; }
  var btn = el("button", "sb-b", "💬"), p = el("div", "sb-p"), mbox = el("div", "sb-m"), f = el("form", "sb-f"), i = el("input"), sendBtn = el("button", "", "Send");
  i.placeholder = "Ask us anything…"; sendBtn.type = "submit"; p.append(el("div", "sb-h", cfg.title || s.getAttribute("data-title") || "Chat with us"), mbox, f); f.append(i, sendBtn);
  document.body.append(btn, p);

  // ---- navigation helpers: take the visitor to a page and point at the right menu item / button
  function norm(u) { try { var x = new URL(u, location.href); return (x.origin + x.pathname).replace(/\/$/, "").toLowerCase(); } catch (e) { return ""; } }
  function visible(e) { var r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden"; }
  function findTarget(a) {
    var found = null, hidden = null, q = "a[href],button,[role=button],summary,input[type=submit],input[type=button]";
    function take(e) { if (e === btn || p.contains(e)) return; if (visible(e)) { found = found || e; } else { hidden = hidden || e; } }
    if (a.target && /^[#.\[]/.test(a.target)) { try { var e0 = document.querySelector(a.target); if (e0) take(e0); } catch (e) {} }
    var list = [].slice.call(document.querySelectorAll(q)), u = a.url ? norm(a.url) : "";
    if (!found && u) list.forEach(function (e) { var h = e.getAttribute("href"); if (h && norm(h) === u) take(e); });
    var t = (a.target && !/^[#.\[]/.test(a.target) ? a.target : a.label || "").toLowerCase().trim();
    if (!found && t) {
      var lab = function (e) { return ((e.textContent || "") + " " + (e.getAttribute("aria-label") || "") + " " + (e.getAttribute("title") || "") + " " + (e.value || "")).replace(/\s+/g, " ").toLowerCase().trim(); };
      list.forEach(function (e) { if (lab(e).indexOf(t) === 0 || lab(e) === t) take(e); });
      if (!found) list.forEach(function (e) { if (lab(e).length < 60 && lab(e).indexOf(t) > -1) take(e); });
    }
    return { el: found, hidden: !found && hidden };
  }
  function highlight(a) {
    var r = findTarget(a);
    if (r.el) {
      r.el.scrollIntoView({ behavior: "smooth", block: "center" }); r.el.classList.add("sb-hl");
      var tip = el("div", "sb-tip", "👉 Here it is"), b = r.el.getBoundingClientRect(); tip.style.top = (b.top + scrollY - 30) + "px"; tip.style.left = (b.left + scrollX) + "px"; document.body.appendChild(tip);
      setTimeout(function () { r.el.classList.remove("sb-hl"); tip.remove(); }, 9000);
    } else if (r.hidden) { add("assistant", "It's inside a menu on this page. Open the menu (☰ or your profile icon) and look for “" + (a.label || a.target) + "”."); }
  }
  function go(a) {
    if (innerWidth < 600) { isOpen = false; p.style.display = "none"; }
    if (a.url && /^https?:/.test(a.url) && norm(a.url) !== norm(location.href)) {
      try { sessionStorage.setItem(SK + "_hl", JSON.stringify(a)); } catch (e) {} save(); location.href = a.url; return;
    }
    highlight(a);
  }
  // ---- chat UI
  function post(path, body) { return fetch(api + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(function (r) { return r.json(); }); }
  function leadForm(m) {
    var f2 = el("form", "sb-lead"), n = el("input"), em = el("input"), go2 = el("button", "sb-go", "Send to the team");
    n.placeholder = "Your name (optional)"; em.placeholder = "Your email"; em.type = "email"; em.required = true; go2.type = "submit";
    f2.append(el("div", "sb-fb", "Want a person to follow up? Leave your email (used only to reply)."), n, em, go2);
    f2.onsubmit = function (e) {
      e.preventDefault(); go2.disabled = true;
      post("/lead", { name: n.value, email: em.value, question: m.question || "", message: m.question || "" }).then(function (d) {
        if (d.detail) { go2.disabled = false; go2.textContent = d.detail; return; }
        m.sent = em.value; save(); f2.replaceWith(el("div", "sb-fb", "✅ Thanks! The team will reply to " + em.value));
      }).catch(function () { go2.disabled = false; });
    };
    return f2;
  }
  function render(m) {
    var d = el("div", "sb-x " + (m.role == "user" ? "sb-u" : "sb-a"), m.content);
    (m.actions || []).forEach(function (a) { var g = el("button", "sb-go", "➡ " + (a.label || "Take me there")); g.type = "button"; g.onclick = function () { go(a); }; d.appendChild(el("br")); d.appendChild(g); });
    if (m.role == "assistant" && m.id && !m.rated) {
      var fb = el("div", "sb-fb", "Helpful? ");
      [["👍", 1], ["👎", -1]].forEach(function (x) { var b = el("button", "", x[0]); b.type = "button"; b.onclick = function () { m.rated = true; save(); post("/feedback", { id: m.id, helpful: x[1] }); fb.textContent = "Thanks for the feedback!"; }; fb.appendChild(b); });
      d.appendChild(fb);
    }
    if (m.handoff && !m.sent) d.appendChild(leadForm(m)); else if (m.sent) d.appendChild(el("div", "sb-fb", "✅ Thanks! The team will reply to " + m.sent));
    m.role && (mbox.appendChild(d), mbox.scrollTop = mbox.scrollHeight); return d;
  }
  function add(role, text, actions, extra) { var m = Object.assign({ role: role, content: text, actions: actions || [] }, extra || {}); msgs.push(m); save(); return render(m); }
  function setOpen(v) { isOpen = v; p.style.display = v ? "flex" : "none"; save(); if (v) i.focus(); }
  if (!msgs.length) add("assistant", cfg.greeting || s.getAttribute("data-greeting") || "Hi! How can I help you today?"); else msgs.forEach(render);
  if (isOpen) setOpen(true);
  btn.onclick = function () { setOpen(p.style.display != "flex"); };
  f.onsubmit = function (e) {
    e.preventDefault(); var q = i.value.trim(); if (!q) return; i.value = "";
    var hist = msgs.slice(-8).map(function (x) { return { role: x.role, content: x.content }; });
    add("user", q); var t = render({ role: "assistant", content: "…" });
    post("", { message: q, session: sess, history: hist }).then(function (d) {
      t.remove(); add("assistant", d.answer || d.detail || "Something went wrong.", d.actions, { id: d.id, handoff: !!d.handoff && !!d.id, question: q });
    }).catch(function () { t.textContent = "Sorry, I'm offline right now."; });
  };
  // after navigating to a new page, point at the item the visitor asked for
  try { var hl = sessionStorage.getItem(SK + "_hl"); if (hl) { sessionStorage.removeItem(SK + "_hl"); hl = JSON.parse(hl); [900, 2500].forEach(function (ms) { setTimeout(function () { if (!document.querySelector(".sb-hl")) highlight(hl); }, ms); }); } } catch (e) {}
  }
})();
