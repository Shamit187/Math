/* ============================================================
   highlights.js — persistent highlighter + notes
   - Highlighter: select text inside a [data-cid] block, choose
     "Highlight" or "Note" from the floating toolbar.
   - Notes are attached to a specific highlight (one note per
     highlight). They live in a separate store from comments —
     comments are for the agent, notes are for the reader.
   ============================================================ */
(function () {
  const API = location.protocol === "file:"
    ? "http://localhost:8765/api"
    : `${location.origin}/api`;
  const HL_LS_KEY = "ts-highlights-v1";
  const NOTE_LS_KEY = "ts-notes-v1";
  const BOOK = document.body && document.body.getAttribute("data-book");
  const PAGE = document.body && document.body.getAttribute("data-page");

  // Skip elements that aren't part of the readable text content.
  const EXCLUDE_SEL =
    ".tts-btn, .cmt-btn, .note-pin, .hl-toolbar, .katex, .katex-display, " +
    ".cmt-panel, .note-panel, .hl-popover";

  if (!PAGE || !BOOK) return;

  let backendOnline = false;
  let highlightsCache = [];   // current page's highlights
  let notesCache = [];        // current page's notes (keyed by hid)

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

  // ---------- localStorage helpers ----------
  function lsLoad(key) {
    try { return JSON.parse(localStorage.getItem(key) || "[]"); }
    catch (_) { return []; }
  }
  function lsSave(key, arr) {
    localStorage.setItem(key, JSON.stringify(arr));
  }
  function uid(prefix) {
    return prefix + Math.random().toString(36).slice(2, 14);
  }
  function nowIso() {
    return new Date().toISOString().replace(/\.\d+Z$/, "Z");
  }

  // ---------- storage API ----------
  async function listHighlights() {
    if (backendOnline) {
      try {
        const r = await fetch(
          `${API}/highlights?book=${encodeURIComponent(BOOK)}&page=${encodeURIComponent(PAGE)}`
        );
        if (r.ok) {
          const d = await r.json();
          return d.highlights || [];
        }
      } catch (_) { backendOnline = false; }
    }
    return lsLoad(HL_LS_KEY).filter(h => h.book === BOOK && h.page === PAGE);
  }

  async function saveHighlight(payload) {
    if (backendOnline) {
      try {
        const r = await fetch(`${API}/highlights`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (r.ok) return (await r.json()).highlight;
      } catch (_) { backendOnline = false; }
    }
    const rec = {
      id: uid("h_"),
      book: payload.book, page: payload.page, cid: payload.cid,
      start: payload.start, end: payload.end,
      text: payload.text, color: payload.color || "yellow",
      created_at: nowIso(), _local: true,
    };
    const all = lsLoad(HL_LS_KEY);
    all.push(rec);
    lsSave(HL_LS_KEY, all);
    return rec;
  }

  async function deleteHighlight(hid) {
    if (backendOnline) {
      try {
        const r = await fetch(`${API}/highlights/${encodeURIComponent(hid)}`, { method: "DELETE" });
        if (r.ok) {
          // Cascade locally too in case both stores coexist
          lsSave(NOTE_LS_KEY, lsLoad(NOTE_LS_KEY).filter(n => n.hid !== hid));
          return true;
        }
      } catch (_) { backendOnline = false; }
    }
    lsSave(HL_LS_KEY, lsLoad(HL_LS_KEY).filter(h => h.id !== hid));
    lsSave(NOTE_LS_KEY, lsLoad(NOTE_LS_KEY).filter(n => n.hid !== hid));
    return true;
  }

  async function listNotes() {
    if (backendOnline) {
      try {
        const r = await fetch(
          `${API}/notes?book=${encodeURIComponent(BOOK)}&page=${encodeURIComponent(PAGE)}`
        );
        if (r.ok) return (await r.json()).notes || [];
      } catch (_) { backendOnline = false; }
    }
    return lsLoad(NOTE_LS_KEY).filter(n => n.book === BOOK && n.page === PAGE);
  }

  async function saveNote(payload) {
    if (backendOnline) {
      try {
        const r = await fetch(`${API}/notes`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (r.ok) return (await r.json()).note;
      } catch (_) { backendOnline = false; }
    }
    const rec = {
      id: uid("n_"),
      book: payload.book, page: payload.page, cid: payload.cid, hid: payload.hid,
      text: payload.text,
      created_at: nowIso(), updated_at: nowIso(), _local: true,
    };
    const all = lsLoad(NOTE_LS_KEY);
    all.push(rec);
    lsSave(NOTE_LS_KEY, all);
    return rec;
  }

  async function updateNote(nid, text) {
    if (backendOnline) {
      try {
        const r = await fetch(`${API}/notes/${encodeURIComponent(nid)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        if (r.ok) return (await r.json()).note;
      } catch (_) { backendOnline = false; }
    }
    const all = lsLoad(NOTE_LS_KEY);
    const n = all.find(x => x.id === nid);
    if (!n) return null;
    n.text = text;
    n.updated_at = nowIso();
    lsSave(NOTE_LS_KEY, all);
    return n;
  }

  async function deleteNote(nid) {
    if (backendOnline) {
      try {
        const r = await fetch(`${API}/notes/${encodeURIComponent(nid)}`, { method: "DELETE" });
        if (r.ok) return true;
      } catch (_) { backendOnline = false; }
    }
    lsSave(NOTE_LS_KEY, lsLoad(NOTE_LS_KEY).filter(n => n.id !== nid));
    return true;
  }

  // ---------- text offset model ----------
  // Offsets are character indices within the block's text content, skipping
  // anything matching EXCLUDE_SEL. We re-derive them from the DOM whenever
  // we save or render, so injected UI buttons don't shift positions.

  function isExcludedText(textNode) {
    const p = textNode.parentElement;
    return !!(p && p.closest(EXCLUDE_SEL));
  }

  function makeWalker(block) {
    return document.createTreeWalker(block, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => isExcludedText(n) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
    });
  }

  function offsetWithin(block, container, offset) {
    if (container.nodeType !== Node.TEXT_NODE) return -1;
    if (isExcludedText(container)) return -1;
    const walker = makeWalker(block);
    let total = 0;
    let node;
    while ((node = walker.nextNode())) {
      if (node === container) return total + offset;
      total += node.nodeValue.length;
    }
    return -1;
  }

  function rangeFromOffsets(block, start, end) {
    const walker = makeWalker(block);
    let total = 0;
    let startNode = null, startOff = 0;
    let endNode = null, endOff = 0;
    let node;
    while ((node = walker.nextNode())) {
      const len = node.nodeValue.length;
      const ns = total, ne = total + len;
      if (startNode === null && start >= ns && start <= ne) {
        startNode = node; startOff = start - ns;
      }
      if (end >= ns && end <= ne) {
        endNode = node; endOff = end - ns;
        break;
      }
      total = ne;
    }
    if (!startNode || !endNode) return null;
    const r = document.createRange();
    r.setStart(startNode, startOff);
    r.setEnd(endNode, endOff);
    return r;
  }

  // Wrap [start, end) inside `block` with one or more `<span class="hl">`.
  // Returns the array of span elements that were inserted.
  function wrapRange(block, start, end, hid, color) {
    const segments = [];
    const walker = makeWalker(block);
    let total = 0;
    let node;
    while ((node = walker.nextNode())) {
      const len = node.nodeValue.length;
      const ns = total, ne = total + len;
      total = ne;
      if (ne <= start) continue;
      if (ns >= end) break;
      segments.push({
        node,
        from: Math.max(0, start - ns),
        to: Math.min(len, end - ns),
      });
    }

    const spans = [];
    // Process in reverse so splitText() in later (DOM order) segments doesn't
    // disturb the offsets we computed for earlier segments.
    for (let i = segments.length - 1; i >= 0; i--) {
      const { node, from, to } = segments[i];
      let target = node;
      if (to < target.nodeValue.length) target.splitText(to);
      if (from > 0) target = target.splitText(from);
      const span = document.createElement("span");
      span.className = "hl";
      span.dataset.hid = hid;
      if (color) span.dataset.color = color;
      target.parentNode.insertBefore(span, target);
      span.appendChild(target);
      spans.unshift(span);
    }
    return spans;
  }

  function blockForCid(cid) {
    return document.querySelector(`[data-cid="${CSS.escape(cid)}"]`);
  }

  // ---------- rendering ----------
  function clearRendered() {
    document.querySelectorAll("span.hl").forEach(span => {
      const parent = span.parentNode;
      while (span.firstChild) parent.insertBefore(span.firstChild, span);
      parent.removeChild(span);
      parent.normalize();
    });
    document.querySelectorAll(".note-pin").forEach(p => p.remove());
  }

  function renderAll() {
    clearRendered();
    const notesByHid = new Map();
    notesCache.forEach(n => notesByHid.set(n.hid, n));

    // Render in document order within each block by sorting on start.
    const byBlock = new Map();
    highlightsCache.forEach(h => {
      const arr = byBlock.get(h.cid) || [];
      arr.push(h);
      byBlock.set(h.cid, arr);
    });

    for (const [cid, items] of byBlock.entries()) {
      const block = blockForCid(cid);
      if (!block) continue;
      // Apply from the right so earlier wraps aren't disturbed by later ones.
      items.sort((a, b) => a.start - b.start);
      for (let i = items.length - 1; i >= 0; i--) {
        const h = items[i];
        const spans = wrapRange(block, h.start, h.end, h.id, h.color);
        if (!spans.length) continue;
        const hasNote = notesByHid.has(h.id);
        spans.forEach(s => s.classList.toggle("hl--has-note", hasNote));
        if (hasNote) {
          // Append a pin marker at the end of the highlight to make notes discoverable.
          const last = spans[spans.length - 1];
          const pin = document.createElement("button");
          pin.type = "button";
          pin.className = "note-pin";
          pin.dataset.hid = h.id;
          pin.title = "View note";
          pin.setAttribute("aria-label", "View note");
          pin.textContent = "📝";
          pin.addEventListener("click", e => {
            e.stopPropagation();
            openPopover(spans[0], h.id);
          });
          last.insertAdjacentElement("afterend", pin);
        }
      }
    }
  }

  // ---------- selection toolbar ----------
  let toolbar = null;
  let pendingRange = null;   // { block, cid, start, end, text, rect }

  function hideToolbar() {
    if (toolbar) { toolbar.remove(); toolbar = null; }
    pendingRange = null;
  }

  function buildToolbar(rect) {
    if (toolbar) { toolbar.remove(); toolbar = null; }
    toolbar = document.createElement("div");
    toolbar.className = "hl-toolbar";
    toolbar.innerHTML = `
      <button type="button" class="hl-toolbar-hl" title="Highlight selection">🖍 Highlight</button>
      <button type="button" class="hl-toolbar-note" title="Highlight + add a note">📝 Note</button>
      <button type="button" class="hl-toolbar-cancel" title="Dismiss">✕</button>
    `;
    document.body.appendChild(toolbar);
    // Position above the selection, falling back to below if off-screen
    const tw = toolbar.offsetWidth, th = toolbar.offsetHeight;
    const scrollY = window.scrollY || document.documentElement.scrollTop;
    const scrollX = window.scrollX || document.documentElement.scrollLeft;
    let top = rect.top + scrollY - th - 8;
    if (top < scrollY + 8) top = rect.bottom + scrollY + 8;
    let left = rect.left + scrollX + rect.width / 2 - tw / 2;
    left = Math.max(scrollX + 8, Math.min(left, scrollX + window.innerWidth - tw - 8));
    toolbar.style.top = `${top}px`;
    toolbar.style.left = `${left}px`;

    toolbar.querySelector(".hl-toolbar-hl").addEventListener("mousedown", e => {
      e.preventDefault(); e.stopPropagation();
      commitHighlight(false);
    });
    toolbar.querySelector(".hl-toolbar-note").addEventListener("mousedown", e => {
      e.preventDefault(); e.stopPropagation();
      commitHighlight(true);
    });
    toolbar.querySelector(".hl-toolbar-cancel").addEventListener("mousedown", e => {
      e.preventDefault(); e.stopPropagation();
      hideToolbar();
      window.getSelection()?.removeAllRanges();
    });
  }

  function rangeOverlapsExisting(cid, start, end) {
    return highlightsCache.some(h =>
      h.cid === cid && start < h.end && end > h.start
    );
  }

  function onSelectionDone() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) { hideToolbar(); return; }
    const range = sel.getRangeAt(0);
    if (range.collapsed) { hideToolbar(); return; }

    // Both endpoints must live inside the same [data-cid] block,
    // and the selection must not contain an excluded zone (math, UI, etc).
    const startEl = range.startContainer.nodeType === Node.TEXT_NODE
      ? range.startContainer.parentElement : range.startContainer;
    const endEl = range.endContainer.nodeType === Node.TEXT_NODE
      ? range.endContainer.parentElement : range.endContainer;
    const block = startEl.closest("[data-cid]");
    if (!block || block !== endEl.closest("[data-cid]")) { hideToolbar(); return; }
    if (block === document.body) { hideToolbar(); return; }
    if (startEl.closest(EXCLUDE_SEL) || endEl.closest(EXCLUDE_SEL)) { hideToolbar(); return; }

    const start = offsetWithin(block, range.startContainer, range.startOffset);
    const end = offsetWithin(block, range.endContainer, range.endOffset);
    if (start < 0 || end < 0 || end <= start) { hideToolbar(); return; }

    const text = range.toString().replace(/\s+/g, " ").trim();
    if (text.length < 1) { hideToolbar(); return; }

    const cid = block.getAttribute("data-cid");
    if (rangeOverlapsExisting(cid, start, end)) { hideToolbar(); return; }

    const rect = range.getBoundingClientRect();
    pendingRange = { block, cid, start, end, text, rect };
    buildToolbar(rect);
  }

  async function commitHighlight(withNote) {
    if (!pendingRange) return;
    const { cid, start, end, text } = pendingRange;
    hideToolbar();
    window.getSelection()?.removeAllRanges();

    const rec = await saveHighlight({
      book: BOOK, page: PAGE, cid, start, end, text, color: "yellow",
    });
    highlightsCache.push(rec);
    renderAll();

    if (withNote) {
      const firstSpan = document.querySelector(`span.hl[data-hid="${CSS.escape(rec.id)}"]`);
      if (firstSpan) openPopover(firstSpan, rec.id, /*editing*/ true);
    }
  }

  // ---------- highlight popover (view/edit note, delete highlight) ----------
  let popover = null;
  let popoverHid = null;

  function hidePopover() {
    if (popover) { popover.remove(); popover = null; popoverHid = null; }
  }

  function openPopover(anchorSpan, hid, startEditing) {
    if (popover && popoverHid === hid && !startEditing) { hidePopover(); return; }
    hidePopover();
    popoverHid = hid;
    const note = notesCache.find(n => n.hid === hid) || null;

    popover = document.createElement("div");
    popover.className = "hl-popover";

    const renderView = () => {
      popover.innerHTML = note
        ? `
          <div class="hl-popover-note-text"></div>
          <div class="hl-popover-meta"></div>
          <div class="hl-popover-actions">
            <button type="button" class="hl-popover-edit">Edit note</button>
            <button type="button" class="hl-popover-del-note">Remove note</button>
            <button type="button" class="hl-popover-del-hl">Delete highlight</button>
          </div>`
        : `
          <div class="hl-popover-empty">No note on this highlight.</div>
          <div class="hl-popover-actions">
            <button type="button" class="hl-popover-add">📝 Add note</button>
            <button type="button" class="hl-popover-del-hl">Delete highlight</button>
          </div>`;
      if (note) {
        popover.querySelector(".hl-popover-note-text").textContent = note.text;
        popover.querySelector(".hl-popover-meta").textContent =
          `Noted ${fmtDate(note.updated_at || note.created_at)}${note._local ? " · local" : ""}`;
        popover.querySelector(".hl-popover-edit").addEventListener("click", () => renderEdit(note.text));
        popover.querySelector(".hl-popover-del-note").addEventListener("click", onDeleteNote);
      } else {
        popover.querySelector(".hl-popover-add").addEventListener("click", () => renderEdit(""));
      }
      popover.querySelector(".hl-popover-del-hl").addEventListener("click", onDeleteHighlight);
    };

    const renderEdit = (initialText) => {
      popover.innerHTML = `
        <textarea class="hl-popover-textarea"
                  placeholder="Your note — only you read this. Comments are a separate, agent-readable thing."></textarea>
        <div class="hl-popover-actions">
          <span class="hl-popover-status"></span>
          <button type="button" class="hl-popover-cancel">Cancel</button>
          <button type="button" class="hl-popover-save">Save</button>
        </div>`;
      const ta = popover.querySelector(".hl-popover-textarea");
      ta.value = initialText;
      setTimeout(() => ta.focus(), 30);
      popover.querySelector(".hl-popover-cancel").addEventListener("click", renderView);
      popover.querySelector(".hl-popover-save").addEventListener("click", async () => {
        const text = ta.value.trim();
        const status = popover.querySelector(".hl-popover-status");
        if (!text) {
          status.textContent = "Write something first.";
          status.className = "hl-popover-status err";
          return;
        }
        status.textContent = "Saving…";
        const existing = notesCache.find(n => n.hid === hid);
        let saved;
        if (existing) {
          saved = await updateNote(existing.id, text);
          if (saved) {
            const idx = notesCache.findIndex(n => n.id === existing.id);
            notesCache[idx] = saved;
          }
        } else {
          saved = await saveNote({ book: BOOK, page: PAGE, cid: anchorSpan.parentElement.closest("[data-cid]")?.getAttribute("data-cid"), hid, text });
          if (saved) notesCache.push(saved);
        }
        renderAll();
        // The anchor span was replaced by renderAll(), so re-resolve before re-opening.
        const fresh = document.querySelector(`span.hl[data-hid="${CSS.escape(hid)}"]`);
        hidePopover();
        if (fresh) openPopover(fresh, hid);
      });
    };

    const onDeleteHighlight = async () => {
      if (!confirm("Delete this highlight (and its note, if any)?")) return;
      await deleteHighlight(hid);
      highlightsCache = highlightsCache.filter(h => h.id !== hid);
      notesCache = notesCache.filter(n => n.hid !== hid);
      hidePopover();
      renderAll();
    };

    const onDeleteNote = async () => {
      const n = notesCache.find(x => x.hid === hid);
      if (!n) return;
      if (!confirm("Remove the note? (The highlight stays.)")) return;
      await deleteNote(n.id);
      notesCache = notesCache.filter(x => x.id !== n.id);
      renderAll();
      const fresh = document.querySelector(`span.hl[data-hid="${CSS.escape(hid)}"]`);
      hidePopover();
      if (fresh) openPopover(fresh, hid);
    };

    document.body.appendChild(popover);
    renderView();
    positionPopover(anchorSpan);
  }

  function positionPopover(anchorSpan) {
    if (!popover || !anchorSpan) return;
    const rect = anchorSpan.getBoundingClientRect();
    const pw = popover.offsetWidth, ph = popover.offsetHeight;
    const scrollY = window.scrollY || document.documentElement.scrollTop;
    const scrollX = window.scrollX || document.documentElement.scrollLeft;
    let top = rect.bottom + scrollY + 6;
    if (top + ph > scrollY + window.innerHeight - 8) {
      top = rect.top + scrollY - ph - 6;
    }
    let left = rect.left + scrollX;
    left = Math.max(scrollX + 8, Math.min(left, scrollX + window.innerWidth - pw - 8));
    popover.style.top = `${top}px`;
    popover.style.left = `${left}px`;
  }

  function fmtDate(iso) {
    try { return new Date(iso).toLocaleString(); }
    catch (_) { return iso; }
  }

  // ---------- event wiring ----------
  function onClickAnywhere(e) {
    // Clicks inside the popover/toolbar shouldn't dismiss them
    if (e.target.closest(".hl-popover, .hl-toolbar, .note-pin")) return;
    // Click a highlight → open popover
    const span = e.target.closest("span.hl");
    if (span) {
      e.stopPropagation();
      const hid = span.dataset.hid;
      openPopover(span, hid);
      return;
    }
    // Otherwise dismiss popover
    hidePopover();
  }

  async function init() {
    await probe();
    const [hl, nt] = await Promise.all([listHighlights(), listNotes()]);
    highlightsCache = hl;
    notesCache = nt;

    // Defer first render slightly so KaTeX has finished rendering math.
    setTimeout(renderAll, 0);

    // Selection: wait for mouseup to finalize the selection before showing the toolbar.
    document.addEventListener("mouseup", () => {
      // Tiny delay so getSelection() reflects the final state.
      setTimeout(onSelectionDone, 10);
    });

    document.addEventListener("click", onClickAnywhere);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { hideToolbar(); hidePopover(); }
    });
    window.addEventListener("resize", () => {
      hideToolbar();
      if (popover && popoverHid) {
        const span = document.querySelector(`span.hl[data-hid="${CSS.escape(popoverHid)}"]`);
        if (span) positionPopover(span);
      }
    });
    window.addEventListener("scroll", () => {
      if (popover && popoverHid) {
        const span = document.querySelector(`span.hl[data-hid="${CSS.escape(popoverHid)}"]`);
        if (span) positionPopover(span);
      }
    }, { passive: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
