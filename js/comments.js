/* ============================================================
   Comments client
   - Tries a local Flask backend at http://localhost:8765/api
   - Falls back to localStorage so it still works in the preview
   - Adds a gutter "comment" button to every [data-cid] block
   ============================================================ */
(function () {
  // When the page is served by serve.py, the API is on the same origin —
  // use a relative URL so it works regardless of host/port.
  // When the page is opened as a file:// URL, fall back to the default port.
  const API_BASE =
    location.protocol === "file:"
      ? "http://localhost:8765/api"
      : `${location.origin}/api`;
  const LS_KEY = "ts-comments-v1";
  const PAGE = document.body && document.body.getAttribute("data-page");
  const BOOK = document.body && document.body.getAttribute("data-book");

  if (!PAGE || !BOOK) {
    // Page isn't tagged with both data-book and data-page — nothing to do.
    return;
  }

  // ---------- storage layer ----------
  let backendOnline = false;

  async function probe() {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 700);
      const r = await fetch(`${API_BASE}/health`, { signal: ctrl.signal });
      clearTimeout(t);
      backendOnline = r.ok;
    } catch (_) {
      backendOnline = false;
    }
    paintBadge();
  }

  function paintBadge() {
    let badge = document.querySelector(".cmt-storage-badge");
    if (!badge) {
      const nav = document.querySelector(".site-header nav");
      if (!nav) return;
      badge = document.createElement("span");
      badge.className = "cmt-storage-badge";
      nav.insertBefore(badge, nav.firstChild);
    }
    badge.classList.toggle("online", backendOnline);
    badge.classList.toggle("offline", !backendOnline);
    badge.textContent = backendOnline ? "● comments synced" : "○ comments local-only";
    badge.title = backendOnline
      ? "Comments are saved to the comments_server backend (persistent)."
      : "Backend not reachable — comments are stored in this browser only. Run python comments_server.py to persist.";
  }

  // Storage interface
  function lsLoad() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      return raw ? JSON.parse(raw) : { comments: [] };
    } catch (_) {
      return { comments: [] };
    }
  }
  function lsSave(d) {
    localStorage.setItem(LS_KEY, JSON.stringify(d));
  }

  async function listComments(page) {
    if (backendOnline) {
      try {
        const r = await fetch(
          `${API_BASE}/comments?book=${encodeURIComponent(BOOK)}&page=${encodeURIComponent(page)}`
        );
        if (r.ok) {
          const d = await r.json();
          return d.comments || [];
        }
      } catch (_) {
        backendOnline = false;
        paintBadge();
      }
    }
    const all = lsLoad().comments;
    return all
      .filter((c) => c.book === BOOK && c.page === page)
      .sort((a, b) => a.created_at.localeCompare(b.created_at));
  }

  async function addComment(payload) {
    if (backendOnline) {
      try {
        const r = await fetch(`${API_BASE}/comments`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (r.ok) {
          const d = await r.json();
          return d.comment;
        }
      } catch (_) {
        backendOnline = false;
        paintBadge();
      }
    }
    const rec = {
      id: "c_" + Math.random().toString(36).slice(2, 14),
      book: payload.book,
      page: payload.page,
      cid: payload.cid,
      text: payload.text,
      block_excerpt: payload.block_excerpt || "",
      created_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
      updated_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
      _local: true,
    };
    const d = lsLoad();
    d.comments.push(rec);
    lsSave(d);
    return rec;
  }

  async function deleteComment(id) {
    if (backendOnline) {
      try {
        const r = await fetch(`${API_BASE}/comments/${encodeURIComponent(id)}`, { method: "DELETE" });
        if (r.ok) return true;
      } catch (_) {
        backendOnline = false;
        paintBadge();
      }
    }
    const d = lsLoad();
    const before = d.comments.length;
    d.comments = d.comments.filter((c) => c.id !== id);
    lsSave(d);
    return d.comments.length !== before;
  }

  // ---------- UI ----------
  function excerptOf(el) {
    const t = (el.textContent || "").trim().replace(/\s+/g, " ");
    return t.length > 200 ? t.slice(0, 200) + "…" : t;
  }

  function fmtDate(iso) {
    try {
      const d = new Date(iso);
      return d.toLocaleString();
    } catch (_) {
      return iso;
    }
  }

  function makeButton(block, cid) {
    const btn = document.createElement("button");
    btn.className = "cmt-btn";
    btn.type = "button";
    btn.setAttribute("aria-label", "Add a comment on this block");
    btn.innerHTML = '<span class="cmt-icon">💬</span><span class="cmt-count" style="display:none">0</span>';
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      togglePanel(block, cid);
    });
    return btn;
  }

  function ensurePanel(block, cid) {
    let panel = block.nextElementSibling;
    if (panel && panel.classList && panel.classList.contains("cmt-panel") && panel.dataset.cid === cid) {
      return panel;
    }
    panel = document.createElement("div");
    panel.className = "cmt-panel hidden";
    panel.dataset.cid = cid;

    const list = document.createElement("div");
    list.className = "cmt-list";

    const form = document.createElement("form");
    form.className = "cmt-form";
    form.innerHTML = `
      <textarea placeholder="What didn't make sense? What needs unpacking? Be as specific as possible."></textarea>
      <div class="cmt-actions">
        <span class="cmt-status"></span>
        <button type="button" class="cmt-cancel">Cancel</button>
        <button type="submit" class="primary">Save comment</button>
      </div>
    `;

    panel.appendChild(list);
    panel.appendChild(form);
    block.insertAdjacentElement("afterend", panel);

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const ta = form.querySelector("textarea");
      const status = form.querySelector(".cmt-status");
      const text = ta.value.trim();
      if (!text) {
        status.textContent = "Write something first.";
        status.className = "cmt-status err";
        return;
      }
      status.textContent = "Saving…";
      status.className = "cmt-status";
      try {
        const rec = await addComment({
          book: BOOK,
          page: PAGE,
          cid: cid,
          text: text,
          block_excerpt: excerptOf(block),
        });
        appendComment(list, rec, block);
        ta.value = "";
        status.textContent = backendOnline ? "Saved." : "Saved (local only).";
        status.className = "cmt-status ok";
        updateButtonCount(block);
        block.classList.add("cmt-has");
        setTimeout(() => { status.textContent = ""; }, 2000);
      } catch (err) {
        console.error(err);
        status.textContent = "Failed to save.";
        status.className = "cmt-status err";
      }
    });

    form.querySelector(".cmt-cancel").addEventListener("click", (e) => {
      e.preventDefault();
      panel.classList.add("hidden");
      block.classList.remove("cmt-active");
    });

    return panel;
  }

  function appendComment(list, rec, block) {
    const empty = list.querySelector(".cmt-empty");
    if (empty) empty.remove();
    const item = document.createElement("div");
    item.className = "cmt-item";
    item.dataset.id = rec.id;
    item.innerHTML = `
      <div class="cmt-text"></div>
      <div class="cmt-meta">
        <span>${fmtDate(rec.created_at)}${rec._local ? " · local" : ""}</span>
        <button type="button" class="cmt-del">Delete</button>
      </div>
    `;
    item.querySelector(".cmt-text").textContent = rec.text;
    item.querySelector(".cmt-del").addEventListener("click", async () => {
      if (!confirm("Delete this comment?")) return;
      const ok = await deleteComment(rec.id);
      if (ok) {
        item.remove();
        if (!list.querySelector(".cmt-item")) {
          const e = document.createElement("div");
          e.className = "cmt-empty";
          e.textContent = "No comments yet on this block.";
          list.appendChild(e);
          block.classList.remove("cmt-has");
        }
        updateButtonCount(block);
      }
    });
    list.appendChild(item);
  }

  async function loadIntoPanel(panel, block) {
    const list = panel.querySelector(".cmt-list");
    list.innerHTML = "";
    const all = await listComments(PAGE);
    const mine = all.filter((c) => c.cid === panel.dataset.cid);
    if (!mine.length) {
      const e = document.createElement("div");
      e.className = "cmt-empty";
      e.textContent = "No comments yet on this block. Be the first.";
      list.appendChild(e);
    } else {
      mine.forEach((rec) => appendComment(list, rec, block));
    }
  }

  async function togglePanel(block, cid) {
    const panel = ensurePanel(block, cid);
    const open = !panel.classList.contains("hidden");
    if (open) {
      panel.classList.add("hidden");
      block.classList.remove("cmt-active");
      return;
    }
    panel.classList.remove("hidden");
    block.classList.add("cmt-active");
    await loadIntoPanel(panel, block);
    const ta = panel.querySelector("textarea");
    setTimeout(() => ta && ta.focus(), 50);
  }

  function updateButtonCount(block) {
    const cid = block.getAttribute("data-cid");
    const btn = block.querySelector(":scope > .cmt-btn");
    if (!btn) return;
    listComments(PAGE).then((all) => {
      const n = all.filter((c) => c.cid === cid).length;
      const span = btn.querySelector(".cmt-count");
      if (n > 0) {
        span.style.display = "inline-flex";
        span.textContent = n;
        block.classList.add("cmt-has");
      } else {
        span.style.display = "none";
        block.classList.remove("cmt-has");
      }
    });
  }

  async function init() {
    await probe();
    // Pre-load all comments for this page so we can mark blocks that have them
    const all = await listComments(PAGE);
    const byCid = new Map();
    all.forEach((c) => {
      byCid.set(c.cid, (byCid.get(c.cid) || 0) + 1);
    });

    const blocks = document.querySelectorAll("[data-cid]");
    blocks.forEach((block) => {
      const cid = block.getAttribute("data-cid");
      // Skip the body itself if it accidentally got a cid
      if (block === document.body) return;
      const btn = makeButton(block, cid);
      block.appendChild(btn);
      const n = byCid.get(cid) || 0;
      const span = btn.querySelector(".cmt-count");
      if (n > 0) {
        span.style.display = "inline-flex";
        span.textContent = n;
        block.classList.add("cmt-has");
      }
    });

    // Keyboard shortcut: pressing "c" while hovering a block opens its comments
    document.addEventListener("keydown", (e) => {
      if (e.key !== "c" && e.key !== "C") return;
      if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
      const hovered = document.querySelector("[data-cid]:hover");
      if (hovered) {
        e.preventDefault();
        togglePanel(hovered, hovered.getAttribute("data-cid"));
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
