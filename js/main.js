/* Theme toggle */
(function () {
  const KEY = "ts-theme";
  const root = document.documentElement;
  const saved = localStorage.getItem(KEY);
  if (saved) root.setAttribute("data-theme", saved);

  function setupToggle() {
    const btn = document.querySelector(".theme-toggle");
    if (!btn) return;
    function sync() {
      const cur = root.getAttribute("data-theme") || "light";
      btn.textContent = cur === "dark" ? "☀ Light" : "☾ Dark";
    }
    sync();
    btn.addEventListener("click", () => {
      const cur = root.getAttribute("data-theme") || "light";
      const next = cur === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      localStorage.setItem(KEY, next);
      sync();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupToggle);
  } else {
    setupToggle();
  }
})();

/* Sidebar active-section highlight */
(function () {
  function setup() {
    const links = document.querySelectorAll(".sidebar a[href^='#']");
    if (!links.length) return;
    const sections = [...links]
      .map((a) => {
        const id = a.getAttribute("href").slice(1);
        const el = document.getElementById(id);
        return el ? { el, link: a } : null;
      })
      .filter(Boolean);
    if (!sections.length) return;

    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          const match = sections.find((s) => s.el === e.target);
          if (!match) return;
          if (e.isIntersecting) {
            sections.forEach((s) => s.link.classList.remove("active"));
            match.link.classList.add("active");
          }
        });
      },
      { rootMargin: "-30% 0px -55% 0px", threshold: 0 }
    );
    sections.forEach((s) => obs.observe(s.el));
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup);
  } else {
    setup();
  }
})();

/* KaTeX auto-render */
(function () {
  function run() {
    if (window.renderMathInElement) {
      window.renderMathInElement(document.body, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "\\[", right: "\\]", display: true },
          { left: "$", right: "$", display: false },
          { left: "\\(", right: "\\)", display: false },
        ],
        throwOnError: false,
      });
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
