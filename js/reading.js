/* ============================================================
   reading.js — per-paper read / unread status
   Adds a "Mark as read" control at the end of a paper. The status
   is stored server-side (/api/reading-status) keyed by the paper
   slug, with a localStorage fallback when the backend is offline,
   mirroring comments.js / highlights.js. The homepage catalog reads
   the same store to badge and filter read vs. unread papers.
   Only papers (data-page="main") get the control.
   ============================================================ */
(function () {
  const API = location.protocol === "file:"
    ? "http://localhost:8765/api"
    : `${location.origin}/api`;
  const LS_KEY = "ts-reading-v1";
  const BOOK = document.body && document.body.getAttribute("data-book");
  const PAGE = document.body && document.body.getAttribute("data-page");

  // Papers only — the control is submitted "at the end of the paper".
  if (!BOOK || PAGE !== "main") return;

  let backendOnline = false;
  let isRead = false;

  // ---------- backend probe ----------
  async function probe() {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 700);
      const r = await fetch(`${API}/health`, { signal: ctrl.signal });
      clearTimeout(t);
      backendOnline = r.ok;
    } catch (_) {
      backendOnline = false;
    }
  }

  // ---------- localStorage fallback ----------
  function lsLoad() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); }
    catch (_) { return {}; }
  }
  function lsSave(map) {
    localStorage.setItem(LS_KEY, JSON.stringify(map));
  }

  // ---------- storage API ----------
  async function loadStatus() {
    if (backendOnline) {
      try {
        const r = await fetch(`${API}/reading-status?book=${encodeURIComponent(BOOK)}`);
        if (r.ok) {
          const d = await r.json();
          const rec = (d.reading || []).find((x) => x.book === BOOK);
          return !!(rec && rec.read);
        }
      } catch (_) { backendOnline = false; }
    }
    return !!lsLoad()[BOOK];
  }

  async function saveStatus(read) {
    if (backendOnline) {
      try {
        const r = await fetch(`${API}/reading-status`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ book: BOOK, read }),
        });
        if (r.ok) return true;
      } catch (_) { backendOnline = false; }
    }
    const map = lsLoad();
    map[BOOK] = read;
    lsSave(map);
    return true;
  }

  // ---------- UI ----------
  let wrap, btn, label;

  function render() {
    wrap.classList.toggle("is-read", isRead);
    btn.textContent = isRead ? "✓ Read — mark as unread" : "Mark as read";
    label.textContent = isRead
      ? "You've marked this paper as read."
      : "Finished? Mark this paper as read to track it on the home page.";
  }

  function mount() {
    const article = document.querySelector("article.content") || document.querySelector("main");
    if (!article) return;

    wrap = document.createElement("div");
    wrap.className = "reading-status";

    label = document.createElement("p");
    label.className = "reading-status-label";

    btn = document.createElement("button");
    btn.type = "button";
    btn.className = "reading-status-btn";
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      const next = !isRead;
      const ok = await saveStatus(next);
      if (ok) isRead = next;
      btn.disabled = false;
      render();
    });

    wrap.appendChild(btn);
    wrap.appendChild(label);
    article.appendChild(wrap);
    render();
  }

  async function init() {
    await probe();
    isRead = await loadStatus();
    mount();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
