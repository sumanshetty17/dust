(function () {
  var s = document.currentScript, key = s.getAttribute("data-key"), color = s.getAttribute("data-color") || "#4f46e5";
  var api = new URL(s.src).origin + "/api/chat/" + key, history = [], sess;
  try { sess = localStorage.getItem("sb_s") || (localStorage.setItem("sb_s", Math.random().toString(36).slice(2)), localStorage.getItem("sb_s")); } catch (e) { sess = "anon"; }
  var css = document.createElement("style");
  css.textContent = ".sb-b{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border-radius:50%;border:0;background:" + color + ";color:#fff;font-size:26px;cursor:pointer;box-shadow:0 4px 16px #0003;z-index:99999}" +
    ".sb-p{position:fixed;right:20px;bottom:88px;width:360px;max-width:calc(100vw - 40px);height:480px;max-height:70vh;background:#fff;border-radius:14px;box-shadow:0 8px 32px #0003;display:none;flex-direction:column;overflow:hidden;font:14px system-ui,sans-serif;z-index:99999}" +
    ".sb-h{background:" + color + ";color:#fff;padding:14px;font-weight:600}.sb-m{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:8px;background:#f8fafc}" +
    ".sb-x{max-width:85%;padding:8px 12px;border-radius:12px;white-space:pre-wrap;line-height:1.4}.sb-u{align-self:flex-end;background:" + color + ";color:#fff}.sb-a{align-self:flex-start;background:#fff;border:1px solid #e2e8f0;color:#111}" +
    ".sb-f{display:flex;border-top:1px solid #e2e8f0}.sb-f input{flex:1;border:0;padding:14px;font:inherit;outline:0}.sb-f button{border:0;background:none;color:" + color + ";font-weight:600;padding:0 14px;cursor:pointer}";
  document.head.appendChild(css);
  function el(t, c, x) { var e = document.createElement(t); if (c) e.className = c; if (x) e.textContent = x; return e; }
  var btn = el("button", "sb-b", "💬"), p = el("div", "sb-p"), m = el("div", "sb-m"), f = el("form", "sb-f"), i = el("input"), go = el("button", "", "Send");
  i.placeholder = "Ask us anything…"; go.type = "submit"; p.append(el("div", "sb-h", s.getAttribute("data-title") || "Chat with us"), m, f); f.append(i, go);
  document.body.append(btn, p);
  function add(role, text) { var d = el("div", "sb-x " + (role == "user" ? "sb-u" : "sb-a"), text); m.appendChild(d); m.scrollTop = m.scrollHeight; return d; }
  add("assistant", s.getAttribute("data-greeting") || "Hi! How can I help you today?");
  btn.onclick = function () { p.style.display = p.style.display == "flex" ? "none" : "flex"; if (p.style.display == "flex") i.focus(); };
  f.onsubmit = function (e) {
    e.preventDefault(); var q = i.value.trim(); if (!q) return; i.value = ""; add("user", q);
    var t = add("assistant", "…");
    fetch(api, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: q, session: sess, history: history }) })
      .then(function (r) { return r.json(); }).then(function (d) {
        t.textContent = d.answer || d.detail || "Something went wrong."; history.push({ role: "user", content: q }, { role: "assistant", content: t.textContent });
      }).catch(function () { t.textContent = "Sorry, I'm offline right now."; });
  };
})();
