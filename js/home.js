/* ============================================================
   Homepage catalog browser.
   Talks to /api/catalog (server-side search + facets + paging) so it
   stays fast as the library grows to thousands of items. State lives in
   the URL hash, so any filtered view is shareable and back/forward works.
   ============================================================ */
(function () {
  const API_BASE =
    location.protocol === "file:"
      ? "http://localhost:8765/api"
      : `${location.origin}/api`;
  const PAGE_SIZE = 24;

  const els = {};
  let state = defaultState();
  let lastTotal = 0;

  function defaultState() {
    return { q: "", type: "", read: "", topic: "", tags: [], sort: "relevance", offset: 0 };
  }

  // ---------- helpers ----------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }
  function debounce(fn, ms) {
    let t;
    return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  }

  // ---------- URL hash <-> state ----------
  function readHash() {
    const h = location.hash.replace(/^#/, "");
    const p = new URLSearchParams(h);
    const s = defaultState();
    s.q = p.get("q") || "";
    s.type = ["book", "paper"].includes(p.get("type")) ? p.get("type") : "";
    s.read = ["read", "unread"].includes(p.get("read")) ? p.get("read") : "";
    s.topic = p.get("topic") || "";
    s.sort = p.get("sort") || "relevance";
    s.tags = (p.get("tags") || "").split(",").map((t) => t.trim()).filter(Boolean);
    return s;
  }
  function writeHash() {
    const p = new URLSearchParams();
    if (state.q) p.set("q", state.q);
    if (state.type) p.set("type", state.type);
    if (state.read) p.set("read", state.read);
    if (state.topic) p.set("topic", state.topic);
    if (state.tags.length) p.set("tags", state.tags.join(","));
    if (state.sort && state.sort !== "relevance") p.set("sort", state.sort);
    const str = p.toString();
    const target = str ? "#" + str : "#";
    if (location.hash !== target) {
      suppressHash = true;
      location.hash = target;
    }
  }
  let suppressHash = false;

  // ---------- fetch ----------
  function queryString(offset) {
    const p = new URLSearchParams();
    if (state.q) p.set("q", state.q);
    if (state.type) p.set("type", state.type);
    if (state.read) p.set("read", state.read);
    if (state.topic) p.set("topic", state.topic);
    state.tags.forEach((t) => p.append("tag", t));
    if (state.sort) p.set("sort", state.sort);
    p.set("offset", offset);
    p.set("limit", PAGE_SIZE);
    return p.toString();
  }

  async function load(append) {
    const offset = append ? state.offset : 0;
    let data;
    try {
      const r = await fetch(`${API_BASE}/catalog?${queryString(offset)}`);
      if (!r.ok) throw new Error("bad status");
      data = await r.json();
    } catch (err) {
      els.results.innerHTML = "";
      els.empty.hidden = false;
      els.empty.innerHTML =
        "Couldn't reach the catalog API. Start the server with <code>python serve.py</code>.";
      els.loadMore.hidden = true;
      els.resultMeta.textContent = "";
      return;
    }
    state.offset = offset + data.items.length;
    lastTotal = data.total;
    renderResults(data.items, append);
    renderFacets(data.facets);
    renderActive();
    els.resultMeta.textContent = data.total
      ? `${data.total} result${data.total === 1 ? "" : "s"}`
      : "";
    els.loadMore.hidden = state.offset >= data.total;
    els.empty.hidden = data.total > 0;
    if (!data.total) {
      els.empty.innerHTML = "No matches. Try clearing a filter or searching for something broader.";
    }
  }

  // ---------- render: results ----------
  function card(it) {
    const li = document.createElement("li");
    const crumb = (it.topics && it.topics[0])
      ? `<span class="card-crumb">${it.topics[0].map((s, i, a) =>
          i === a.length - 1 ? `<b>${esc(s)}</b>` : esc(s)).join(" › ")}</span>`
      : "";
    const meta = it.type === "book"
      ? (it.subtitle ? esc(it.subtitle) : "") + (it.n_chapters ? ` · ${it.n_chapters} chapters` : "")
      : esc(it.authors || "") + (it.venue ? ` · ${esc(it.venue)}` : "");
    const year = it.year ? `<span>${it.year}</span>` : "";
    const tags = (it.tags || []).slice(0, 5).map((t) =>
      `<span class="ct" data-tag="${esc(t)}">${esc(t)}</span>`).join("");
    const readBadge = it.read ? `<span class="card-badge read" title="Marked as read">✓ read</span>` : "";
    li.innerHTML = `
      <div class="card-head">
        <span class="card-badge ${it.type}">${it.type}</span>
        ${readBadge}
        <h3 class="card-title"><a href="${esc(it.url)}">${esc(it.title)}</a></h3>
      </div>
      ${meta ? `<p class="card-sub">${meta}</p>` : ""}
      ${it.description ? `<p class="card-desc">${esc(it.description)}</p>` : ""}
      <div class="card-foot">
        ${crumb}
        ${year}
        ${tags ? `<span class="card-tags">${tags}</span>` : ""}
      </div>`;
    li.querySelectorAll(".ct").forEach((c) =>
      c.addEventListener("click", () => toggleTag(c.dataset.tag)));
    return li;
  }

  function renderResults(items, append) {
    if (!append) els.results.innerHTML = "";
    items.forEach((it) => els.results.appendChild(card(it)));
  }

  // ---------- render: facets ----------
  function renderFacets(facets) {
    // type
    els.typeFacet.querySelectorAll("button").forEach((b) => {
      const t = b.dataset.type;
      const n = t === "" ? facets.types.all : facets.types[t] || 0;
      b.querySelector(".cnt").textContent = n;
      b.classList.toggle("active", state.type === t);
    });
    // reading
    if (els.readingFacet) {
      els.readingFacet.querySelectorAll("button").forEach((b) => {
        const r = b.dataset.read;
        const n = r === "" ? facets.reading.all : facets.reading[r] || 0;
        b.querySelector(".cnt").textContent = n;
        b.classList.toggle("active", state.read === r);
      });
    }
    // topics
    els.topicTree.innerHTML = "";
    facets.topics.forEach((n) => els.topicTree.appendChild(topicNode(n)));
    // tags
    els.tagList.innerHTML = "";
    facets.tags.forEach((t) => {
      const c = document.createElement("span");
      c.className = "tag-chip" + (state.tags.includes(t.name) ? " active" : "");
      c.innerHTML = `${esc(t.name)}<span class="tc">${t.count}</span>`;
      c.addEventListener("click", () => toggleTag(t.name));
      els.tagList.appendChild(c);
    });
  }

  function topicNode(n) {
    const wrap = document.createElement("div");
    wrap.className = "topic-node";
    const selected = state.topic === n.path;
    const onPath = state.topic && (state.topic + "/").startsWith(n.path + "/");
    if (selected) wrap.classList.add("selected");
    if (onPath || selected) wrap.classList.add("open");
    const hasKids = n.children && n.children.length;
    const row = document.createElement("div");
    row.className = "topic-row";
    row.innerHTML =
      `<span class="twirl${hasKids ? "" : " leaf"}">▶</span>` +
      `<span class="tname">${esc(n.name)}</span>` +
      `<span class="tcount">${n.count}</span>`;
    row.querySelector(".twirl").addEventListener("click", (e) => {
      e.stopPropagation();
      if (hasKids) wrap.classList.toggle("open");
    });
    row.addEventListener("click", () => selectTopic(selected ? "" : n.path));
    wrap.appendChild(row);
    if (hasKids) {
      const kids = document.createElement("div");
      kids.className = "topic-children";
      n.children.forEach((c) => kids.appendChild(topicNode(c)));
      wrap.appendChild(kids);
    }
    return wrap;
  }

  // ---------- render: active filters ----------
  function renderActive() {
    const chips = [];
    if (state.q) chips.push(chip("search", `“${state.q}”`, () => { state.q = ""; els.search.value = ""; apply(); }));
    if (state.type) chips.push(chip("type", state.type, () => { state.type = ""; apply(); }));
    if (state.read) chips.push(chip("read", state.read, () => { state.read = ""; apply(); }));
    if (state.topic) chips.push(chip("topic", state.topic.split("/").join(" › "), () => { state.topic = ""; apply(); }));
    state.tags.forEach((t) => chips.push(chip("tag", t, () => toggleTag(t))));
    els.active.innerHTML = "";
    chips.forEach((c) => els.active.appendChild(c));
    if (chips.length > 1) {
      const clr = document.createElement("span");
      clr.className = "afilter clear-all";
      clr.textContent = "Clear all";
      clr.addEventListener("click", clearAll);
      els.active.appendChild(clr);
    }
  }
  function chip(kind, label, onRemove) {
    const s = document.createElement("span");
    s.className = "afilter";
    s.innerHTML = `<span>${esc(label)}</span><button aria-label="remove">×</button>`;
    s.querySelector("button").addEventListener("click", onRemove);
    return s;
  }

  // ---------- state mutations ----------
  function apply() { writeHash(); load(false); }
  function selectTopic(path) { state.topic = path; apply(); }
  function toggleTag(tag) {
    const i = state.tags.indexOf(tag);
    if (i >= 0) state.tags.splice(i, 1);
    else state.tags.push(tag);
    apply();
  }
  function setType(t) { state.type = t; apply(); }
  function setRead(r) { state.read = r; apply(); }
  function clearAll() {
    const sort = state.sort;
    state = defaultState();
    state.sort = sort;
    els.search.value = "";
    apply();
  }

  // ---------- init ----------
  function init() {
    els.results = document.getElementById("results");
    els.empty = document.getElementById("empty");
    els.resultMeta = document.getElementById("result-meta");
    els.loadMore = document.getElementById("load-more");
    els.search = document.getElementById("search");
    els.sort = document.getElementById("sort");
    els.typeFacet = document.getElementById("type-facet");
    els.readingFacet = document.getElementById("reading-facet");
    els.topicTree = document.getElementById("topic-tree");
    els.tagList = document.getElementById("tag-list");
    els.active = document.getElementById("active-filters");
    if (!els.results) return;

    state = readHash();
    els.search.value = state.q;
    els.sort.value = state.sort;

    els.search.addEventListener("input", debounce((e) => {
      state.q = e.target.value.trim();
      apply();
    }, 220));
    els.sort.addEventListener("change", (e) => { state.sort = e.target.value; apply(); });
    els.loadMore.addEventListener("click", () => load(true));
    els.typeFacet.querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => setType(b.dataset.type)));
    if (els.readingFacet) els.readingFacet.querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => setRead(b.dataset.read)));

    const ft = document.getElementById("filters-toggle");
    if (ft) ft.addEventListener("click", () => {
      const f = document.getElementById("facets");
      f.hidden = !f.hidden;
    });

    window.addEventListener("hashchange", () => {
      if (suppressHash) { suppressHash = false; return; }
      state = readHash();
      els.search.value = state.q;
      els.sort.value = state.sort;
      load(false);
    });

    load(false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
