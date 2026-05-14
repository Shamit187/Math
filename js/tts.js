/* tts.js — Read-aloud TTS player for Slow Books */
(function () {
  const BOOK = document.body?.getAttribute("data-book");
  const PAGE = document.body?.getAttribute("data-page");
  if (!BOOK || !PAGE) return;

  const API = location.protocol === "file:"
    ? "http://localhost:8765/api"
    : `${location.origin}/api`;

  const SPEED_STEPS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0];
  const SPEED_KEY = "tts-speed";

  let blocks = [];
  let currentIdx = -1;
  let isActive = false;
  let isPlaying = false;
  let currentAudio = null;
  let audioResolve = null;
  let nextUrl = null;
  let nextUrlIdx = -1;
  let speedIdx = Math.max(
    0,
    SPEED_STEPS.indexOf(parseFloat(localStorage.getItem(SPEED_KEY) || "1"))
  );
  if (speedIdx < 0) speedIdx = 2; // default 1.0×

  function speed() { return SPEED_STEPS[speedIdx]; }

  // ---- API helpers ----

  async function fetchStatus() {
    try {
      const r = await fetch(`${API}/tts/status`, {
        signal: AbortSignal.timeout(3000),
      });
      return r.ok ? r.json() : null;
    } catch (_) {
      return null;
    }
  }

  async function fetchAudio(text) {
    const r = await fetch(`${API}/tts/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, speed: speed() }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return URL.createObjectURL(await r.blob());
  }

  // ---- Text extraction ----

  function getText(el) {
    const clone = el.cloneNode(true);

    // Replace math: use data-tts description when present, else generic placeholder
    clone.querySelectorAll(".katex").forEach(k => {
      // Walk up to the nearest .tts-math wrapper (set by content authors)
      const wrapper = k.closest(".tts-math");
      const desc = wrapper?.dataset?.tts?.trim();
      const s = document.createElement("span");
      s.textContent = desc ? ` ${desc} ` : " math expression ";
      k.replaceWith(s);
    });

    // Remove any UI buttons we injected
    clone.querySelectorAll(".tts-btn, .cmt-btn").forEach(b => b.remove());

    return clone.textContent.replace(/\s+/g, " ").trim();
  }

  // ---- Visual state ----

  function refreshUI() {
    const bar = document.getElementById("tts-bar");
    const headerBtn = document.getElementById("tts-header-btn");
    const idle = !isActive && currentIdx < 0;

    if (bar) {
      bar.classList.toggle("tts-bar--hidden", idle);
      const label = bar.querySelector(".tts-label");
      const playBtn = bar.querySelector(".tts-play");
      const speedLabel = bar.querySelector(".tts-speed-val");
      if (label) {
        label.textContent = idle ? "" : `Block ${currentIdx + 1} / ${blocks.length}`;
      }
      if (playBtn) playBtn.textContent = isPlaying ? "⏸ Pause" : "▶ Resume";
      if (speedLabel) speedLabel.textContent = `${speed()}×`;
    }

    if (headerBtn) {
      headerBtn.textContent = idle ? "🔊 Read" : "⏹ Stop";
      headerBtn.title = idle ? "Read this page aloud" : "Stop reading";
    }
  }

  function highlight(idx) {
    blocks.forEach((b, i) => b.classList.toggle("tts-reading", i === idx));
    if (idx >= 0 && idx < blocks.length) {
      const rect = blocks[idx].getBoundingClientRect();
      if (rect.top < 90 || rect.bottom > window.innerHeight - 90) {
        blocks[idx].scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  }

  // ---- Playback engine ----

  async function playBlock(idx) {
    if (!isActive || idx >= blocks.length) {
      if (isActive) stop();
      return;
    }

    currentIdx = idx;
    isPlaying = true;
    highlight(idx);
    refreshUI();

    let url;
    try {
      if (nextUrlIdx === idx && nextUrl) {
        url = nextUrl;
        nextUrl = null;
        nextUrlIdx = -1;
      } else {
        const text = getText(blocks[idx]);
        if (!text || text.length < 5) { playBlock(idx + 1); return; }
        url = await fetchAudio(text);
      }
    } catch (err) {
      if (!isActive) return;
      console.warn("[TTS] fetch failed for block", idx, err);
      playBlock(idx + 1);
      return;
    }

    if (!isActive) { URL.revokeObjectURL(url); return; }

    // Pre-fetch next block in the background
    const prefetchIdx = idx + 1;
    if (prefetchIdx < blocks.length) {
      const nextText = getText(blocks[prefetchIdx]);
      if (nextText && nextText.length >= 5) {
        fetchAudio(nextText).then(u => {
          if (isActive && nextUrlIdx < 0) { nextUrl = u; nextUrlIdx = prefetchIdx; }
          else URL.revokeObjectURL(u);
        }).catch(() => {});
      }
    }

    const audio = new Audio(url);
    currentAudio = audio;

    await new Promise(resolve => {
      audioResolve = resolve;
      audio.onended = resolve;
      audio.onerror = resolve;
      audio.play().catch(resolve);
    });

    audioResolve = null;
    currentAudio = null;
    URL.revokeObjectURL(url);

    if (isActive && isPlaying) playBlock(idx + 1);
  }

  function stop() {
    isActive = false;
    isPlaying = false;
    if (audioResolve) { audioResolve(); audioResolve = null; }
    if (currentAudio) { currentAudio.pause(); currentAudio.src = ""; currentAudio = null; }
    if (nextUrl) { URL.revokeObjectURL(nextUrl); nextUrl = null; nextUrlIdx = -1; }
    highlight(-1);
    currentIdx = -1;
    refreshUI();
  }

  function pauseResume() {
    if (!currentAudio) return;
    if (isPlaying) { currentAudio.pause(); isPlaying = false; }
    else           { currentAudio.play();  isPlaying = true;  }
    refreshUI();
  }

  function changeSpeed(delta) {
    const next = speedIdx + delta;
    if (next < 0 || next >= SPEED_STEPS.length) return;
    speedIdx = next;
    localStorage.setItem(SPEED_KEY, speed());
    // Discard pre-fetched audio since it was at the old speed
    if (nextUrl) { URL.revokeObjectURL(nextUrl); nextUrl = null; nextUrlIdx = -1; }
    refreshUI();
  }

  function startFrom(idx) {
    stop();
    setTimeout(() => { isActive = true; isPlaying = true; playBlock(idx); }, 30);
  }

  // ---- DOM construction ----

  function focusCurrentBlock() {
    if (currentIdx >= 0 && currentIdx < blocks.length) {
      blocks[currentIdx].scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  function buildBar() {
    const bar = document.createElement("div");
    bar.id = "tts-bar";
    bar.className = "tts-bar tts-bar--hidden";
    bar.innerHTML = `
      <span class="tts-label"></span>
      <span class="tts-speed-ctrl">
        <button class="tts-speed-dec" title="Slower">−</button>
        <span class="tts-speed-val">${speed()}×</span>
        <button class="tts-speed-inc" title="Faster">+</button>
      </span>
      <button class="tts-focus" title="Scroll to current block">⊙ Focus</button>
      <button class="tts-play" title="Pause or Resume">⏸ Pause</button>
      <button class="tts-stop" title="Stop reading">⏹ Stop</button>
    `;
    bar.querySelector(".tts-play").addEventListener("click", pauseResume);
    bar.querySelector(".tts-stop").addEventListener("click", stop);
    bar.querySelector(".tts-focus").addEventListener("click", focusCurrentBlock);
    bar.querySelector(".tts-speed-dec").addEventListener("click", () => changeSpeed(-1));
    bar.querySelector(".tts-speed-inc").addEventListener("click", () => changeSpeed(+1));
    document.body.appendChild(bar);
  }

  function addBlockBtn(block, idx) {
    const btn = document.createElement("button");
    btn.className = "tts-btn";
    btn.type = "button";
    btn.title = "Read from here";
    btn.setAttribute("aria-label", "Read from this block");
    btn.textContent = "🔊";
    btn.addEventListener("click", e => { e.stopPropagation(); startFrom(idx); });
    block.appendChild(btn);
  }

  function addHeaderBtn() {
    const nav = document.querySelector(".site-header nav");
    if (!nav) return;
    const btn = document.createElement("button");
    btn.id = "tts-header-btn";
    btn.className = "theme-toggle tts-header-btn";
    btn.textContent = "🔊 Read";
    btn.title = "Read this page aloud";
    btn.addEventListener("click", () => {
      if (isActive || currentIdx >= 0) stop();
      else startFrom(0);
    });
    nav.insertBefore(btn, nav.firstChild);
  }

  // ---- Init ----

  async function init() {
    const status = await fetchStatus();
    if (!status || !status.enabled || status.state !== "ready") return;

    blocks = [...document.querySelectorAll("[data-cid]")].filter(el => el !== document.body);
    if (!blocks.length) return;

    buildBar();
    addHeaderBtn();
    blocks.forEach((b, i) => addBlockBtn(b, i));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
