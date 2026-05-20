/* tts.js — Read-aloud TTS player for Slow Books */
(function () {
  const BOOK = document.body?.getAttribute("data-book");
  const PAGE = document.body?.getAttribute("data-page");
  if (!BOOK || !PAGE) return;

  const API = location.protocol === "file:"
    ? "http://localhost:8765/api"
    : `${location.origin}/api`;

  const SPEED_MIN = 0.25;
  const SPEED_MAX = 4.0;
  const SPEED_KEY = "tts-speed";
  const VOICE_KEY = "tts-voice";

  let blocks = [];
  let currentIdx = -1;
  let isActive = false;
  let isPlaying = false;
  let currentAudio = null;
  let audioResolve = null;
  let nextUrl = null;
  let nextUrlIdx = -1;
  let speedVal = parseFloat(localStorage.getItem(SPEED_KEY) || "1");
  if (isNaN(speedVal) || speedVal < SPEED_MIN || speedVal > SPEED_MAX) speedVal = 1.0;

  let voices = [];                                            // [{id, label, grade, lang}]
  let currentVoice = localStorage.getItem(VOICE_KEY) || "";   // resolved once voices arrive

  function speed() { return speedVal; }

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

  async function fetchVoices() {
    try {
      const r = await fetch(`${API}/tts/voices`, {
        signal: AbortSignal.timeout(3000),
      });
      if (!r.ok) return null;
      return await r.json();
    } catch (_) {
      return null;
    }
  }

  async function fetchAudio(text) {
    const r = await fetch(`${API}/tts/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice: currentVoice }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return URL.createObjectURL(await r.blob());
  }

  // ---- Text extraction ----

  function getText(el) {
    const clone = el.cloneNode(true);

    // Remove nested blocks — their text is read when those blocks are reached individually
    clone.querySelectorAll("[data-cid]").forEach(nested => nested.remove());

    // Replace math: use data-tts description when present, else generic placeholder
    clone.querySelectorAll(".katex").forEach(k => {
      // Walk up to the nearest .tts-math wrapper (set by content authors)
      const wrapper = k.closest(".tts-math");
      const desc = wrapper?.dataset?.tts?.trim();
      const s = document.createElement("span");
      s.textContent = desc ? ` ${desc} ` : " math expression ";
      k.replaceWith(s);
    });

    // Remove any UI buttons / pins we injected
    clone.querySelectorAll(".tts-btn, .cmt-btn, .note-pin, .hl-toolbar").forEach(b => b.remove());

    return clone.textContent.replace(/\s+/g, " ").trim();
  }

  // ---- Visual state ----

  function refreshUI() {
    document.body.classList.toggle("tts-active", isActive);

    const progressBar = document.getElementById("tts-progress-bar");
    if (progressBar) {
      const pct = isActive && blocks.length > 0
        ? ((currentIdx + 1) / blocks.length * 100)
        : 0;
      progressBar.style.width = pct + "%";
    }

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
      if (speedLabel) speedLabel.textContent = `${+speedVal.toFixed(2)}×`;
      const slider = bar.querySelector(".tts-speed-slider");
      if (slider) slider.value = speedVal;
    }

    if (headerBtn) {
      headerBtn.textContent = idle ? "🔊 Read" : "⏹ Stop";
      headerBtn.title = idle ? "Read this page aloud" : "Stop reading";
    }
  }

  function highlight(idx) {
    document.querySelectorAll(".tts-reading-ancestor").forEach(el => el.classList.remove("tts-reading-ancestor"));
    blocks.forEach((b, i) => b.classList.toggle("tts-reading", i === idx));
    if (idx >= 0 && idx < blocks.length) {
      // Mark [data-cid] ancestors so they are not blurred (CSS filter on a parent propagates)
      let el = blocks[idx].parentElement;
      while (el && el !== document.body) {
        if (el.hasAttribute("data-cid")) el.classList.add("tts-reading-ancestor");
        el = el.parentElement;
      }
      const rect = blocks[idx].getBoundingClientRect();
      if (rect.top < 90 || rect.bottom > window.innerHeight - 90) {
        blocks[idx].scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  }

  // ---- Playback engine ----

  function goToNextPage() {
    const nextLink = document.querySelector("nav.chapter-nav a.next");
    if (!nextLink) { stop(); return; }
    const url = new URL(nextLink.href, location.href);
    url.searchParams.set("autoplay", "1");
    stop();
    location.href = url.toString();
  }

  async function playBlock(idx) {
    if (!isActive || idx >= blocks.length) {
      if (isActive) goToNextPage();
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
    audio.playbackRate = speed();
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

  function discardPrefetch() {
    if (nextUrl) { URL.revokeObjectURL(nextUrl); nextUrl = null; nextUrlIdx = -1; }
  }

  function changeVoice(voiceId) {
    if (!voiceId || voiceId === currentVoice) return;
    currentVoice = voiceId;
    localStorage.setItem(VOICE_KEY, voiceId);
    discardPrefetch();   // pre-fetched audio was in the old voice
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

    const voiceOptions = voices.map(v =>
      `<option value="${v.id}"${v.id === currentVoice ? " selected" : ""}>${v.label}</option>`
    ).join("");

    bar.innerHTML = `
      <span class="tts-label"></span>
      <span class="tts-voice-ctrl" title="Reader voice">
        <span class="tts-voice-icon">👤</span>
        <select class="tts-voice-sel" aria-label="Reader voice">${voiceOptions}</select>
      </span>
      <span class="tts-speed-ctrl" title="Playback speed">
        <span class="tts-speed-val">${+speedVal.toFixed(2)}×</span>
        <input class="tts-speed-slider" type="range" min="${SPEED_MIN}" max="${SPEED_MAX}" step="any" value="${speedVal}" aria-label="Playback speed">
      </span>
      <button class="tts-focus" title="Scroll to current block">⊙ Focus</button>
      <button class="tts-play" title="Pause or Resume">⏸ Pause</button>
      <button class="tts-stop" title="Stop reading">⏹ Stop</button>
    `;
    bar.querySelector(".tts-play").addEventListener("click", pauseResume);
    bar.querySelector(".tts-stop").addEventListener("click", stop);
    bar.querySelector(".tts-focus").addEventListener("click", focusCurrentBlock);
    bar.querySelector(".tts-speed-slider").addEventListener("input", e => {
      speedVal = parseFloat(e.target.value);
      localStorage.setItem(SPEED_KEY, speedVal);
      if (currentAudio) currentAudio.playbackRate = speedVal;
      refreshUI();
    });
    bar.querySelector(".tts-voice-sel").addEventListener("change", e => changeVoice(e.target.value));
    document.body.appendChild(bar);
  }

  function buildProgressBar() {
    const header = document.querySelector(".site-header");
    if (!header) return;
    const el = document.createElement("div");
    el.id = "tts-progress-bar";
    header.appendChild(el);
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

  // ---- Keyboard shortcuts ----

  function setupKeyboard() {
    document.addEventListener("keydown", function (e) {
      // Don't intercept while typing in a form field
      const active = document.activeElement;
      const tag = active ? active.tagName : "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || active?.isContentEditable) return;

      switch (e.key) {
        case " ":
        case "Spacebar":       // legacy Firefox
        case "MediaPlayPause": // dedicated media key
          e.preventDefault();
          if (!isActive) startFrom(currentIdx >= 0 ? currentIdx : 0);
          else pauseResume();
          break;

        case "ArrowRight":
          if (isActive) {
            e.preventDefault();
            startFrom(Math.min(currentIdx + 1, blocks.length - 1));
          }
          break;

        case "ArrowLeft":
          if (isActive) {
            e.preventDefault();
            startFrom(Math.max(currentIdx - 1, 0));
          }
          break;
      }
    });
  }

  // ---- Init ----

  async function init() {
    const status = await fetchStatus();
    if (!status || !status.enabled || status.state !== "ready") return;

    const voiceData = await fetchVoices();
    voices = voiceData?.voices || [];
    const defaultVoice = voiceData?.default || (voices[0] && voices[0].id) || "";
    // Validate the saved voice is still in the catalog; fall back to default otherwise
    if (!voices.some(v => v.id === currentVoice)) currentVoice = defaultVoice;

    blocks = [...document.querySelectorAll("[data-cid]")].filter(el => el !== document.body);
    if (!blocks.length) return;

    buildBar();
    buildProgressBar();
    addHeaderBtn();
    blocks.forEach((b, i) => addBlockBtn(b, i));
    setupKeyboard();

    if (new URLSearchParams(location.search).get("autoplay") === "1") {
      // Strip the param from the address bar without adding a history entry
      history.replaceState(null, "", location.pathname);
      startFrom(0);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
