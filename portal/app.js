/*
 * app.js — renders the portal from KR_DATA and wires up interactivity:
 * theme toggle, app search/filter, scrollspy, reveal animations,
 * PWA install prompt and service-worker registration.
 */

(function () {
  "use strict";

  const D = window.KR_DATA;
  const $ = (sel) => document.querySelector(sel);

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  /* ---------- Theme ---------- */

  const THEME_KEY = "kr-portal-theme";

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    $("#theme-toggle").textContent = theme === "dark" ? "☀️" : "🌙";
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", theme === "dark" ? "#101418" : "#f7f7f5");
  }

  function initTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    const preferred = saved ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    applyTheme(preferred);
    $("#theme-toggle").addEventListener("click", () => {
      const next =
        document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      localStorage.setItem(THEME_KEY, next);
      applyTheme(next);
    });
  }

  /* ---------- Hero + summary ---------- */

  function renderHero() {
    $(".hero-name").textContent = D.name;
    $(".hero-title").textContent = D.title;
    $(".hero-tagline").textContent = D.tagline;
    const badges = $(".hero-badges");
    D.badges.forEach((b) => {
      const span = el("span", "badge", b);
      span.setAttribute("role", "listitem");
      badges.appendChild(span);
    });
  }

  function renderStats() {
    const grid = $("#stat-grid");
    D.stats.forEach((s) => {
      const tile = el("div", "stat-tile reveal");
      tile.appendChild(el("span", "value", s.value));
      tile.appendChild(el("span", "label", s.label));
      grid.appendChild(tile);
    });
  }

  function renderSummary() {
    const wrap = $("#summary-copy");
    D.summary.forEach((p) => wrap.appendChild(el("p", null, p)));
  }

  /* ---------- Impact ---------- */

  function renderImpact() {
    const grid = $("#impact-grid");
    D.impact.forEach((i) => {
      const card = el("div", "impact-card reveal");
      card.appendChild(el("div", "metric", i.metric));
      card.appendChild(el("h3", null, i.title));
      card.appendChild(el("p", null, i.detail));
      grid.appendChild(card);
    });
  }

  /* ---------- Career ---------- */

  function renderCareer() {
    const list = $("#timeline");
    D.career.forEach((c) => {
      const li = el("li", "reveal");
      li.appendChild(el("div", "period", c.period));
      const h = el("h3", null, c.role + " ");
      h.appendChild(el("span", "org", "· " + c.org));
      li.appendChild(h);
      li.appendChild(el("p", null, c.detail));
      list.appendChild(li);
    });
  }

  /* ---------- Frameworks ---------- */

  function renderFrameworks() {
    const grid = $("#framework-grid");
    D.frameworks.forEach((f) => {
      const card = el("div", "framework-card reveal");
      const head = el("div", null);
      head.appendChild(el("span", "code", f.code));
      head.appendChild(el("span", "area", f.area));
      card.appendChild(head);
      card.appendChild(el("p", null, f.detail));
      if (f.pillars.length) {
        const row = el("div", "pillar-row");
        f.pillars.forEach((p) => row.appendChild(el("span", "pillar", p)));
        card.appendChild(row);
      }
      grid.appendChild(card);
    });
  }

  /* ---------- Apps directory ---------- */

  const appState = { query: "", category: "All" };

  function appMatches(app) {
    if (appState.category !== "All" && app.category !== appState.category) return false;
    if (!appState.query) return true;
    const q = appState.query.toLowerCase();
    return (
      app.name.toLowerCase().includes(q) ||
      app.detail.toLowerCase().includes(q) ||
      app.category.toLowerCase().includes(q)
    );
  }

  function renderApps() {
    const grid = $("#app-grid");
    grid.textContent = "";
    const visible = D.apps.filter(appMatches);
    $("#app-empty").hidden = visible.length > 0;

    visible.forEach((app) => {
      const card = el("a", "app-card");
      card.href = app.url || D.digitalHubUrl;
      if (!app.local) {
        card.target = "_blank";
        card.rel = "noopener";
      }

      const top = el("div", "app-top");
      top.appendChild(el("span", "emoji", app.emoji));
      top.appendChild(el("h3", null, app.name));
      if (app.local) top.appendChild(el("span", "badge-local", "IN THIS REPO"));
      card.appendChild(top);

      card.appendChild(el("span", "cat", app.category));
      card.appendChild(el("p", null, app.detail));
      card.appendChild(
        el("span", "go", app.local ? "Play now →" : app.url ? "Visit →" : "Via Digital Hub ↗")
      );
      grid.appendChild(card);
    });
  }

  function initAppControls() {
    const chips = $("#app-chips");
    D.appCategories.forEach((cat) => {
      const chip = el("button", "chip", cat);
      chip.type = "button";
      chip.setAttribute("aria-pressed", String(cat === appState.category));
      chip.addEventListener("click", () => {
        appState.category = cat;
        chips
          .querySelectorAll(".chip")
          .forEach((c) => c.setAttribute("aria-pressed", String(c.textContent === cat)));
        renderApps();
      });
      chips.appendChild(chip);
    });

    $("#app-search").addEventListener("input", (e) => {
      appState.query = e.target.value.trim();
      renderApps();
    });
  }

  /* ---------- Books, recommendations, awards, links ---------- */

  function renderBooks() {
    const grid = $("#book-grid");
    const amazon = D.links.find((l) => l.label === "Amazon Author");
    D.books.forEach((b) => {
      const card = el("div", "book-card reveal");
      card.appendChild(el("span", "emoji", b.emoji));
      card.appendChild(el("h3", null, b.title));
      card.appendChild(el("span", "pub", b.publisher));
      card.appendChild(el("p", null, b.detail));
      const a = el("a", null, "Get the book →");
      a.href = amazon ? amazon.url : "#";
      a.target = "_blank";
      a.rel = "noopener";
      card.appendChild(a);
      grid.appendChild(card);
    });
  }

  function renderRecommendations() {
    const grid = $("#rec-grid");
    D.recommendations.forEach((r) => {
      const card = el("div", "rec-card reveal");
      card.appendChild(el("blockquote", null, "“" + r.quote + "”"));
      card.appendChild(el("div", "who", r.who));
      card.appendChild(el("div", "role", r.role));
      grid.appendChild(card);
    });
  }

  function renderAwards() {
    const grid = $("#award-grid");
    D.awards.forEach((a) => {
      const card = el("div", "award-card reveal");
      card.appendChild(el("div", "by", a.by));
      card.appendChild(el("h3", null, a.title));
      card.appendChild(el("p", null, a.detail));
      grid.appendChild(card);
    });
  }

  function renderConnect() {
    $("#location-note").textContent = D.location + ".";
    $("#email-link").href = "mailto:" + D.email;
    const grid = $("#link-grid");
    D.links.forEach((l) => {
      const pill = el("a", "link-pill");
      pill.href = l.url;
      pill.target = "_blank";
      pill.rel = "noopener";
      pill.appendChild(el("span", null, l.emoji));
      pill.appendChild(el("span", null, l.label));
      grid.appendChild(pill);
    });
    document.querySelectorAll("[data-hub-link]").forEach((a) => (a.href = D.digitalHubUrl));
  }

  /* ---------- Scrollspy + reveal ---------- */

  function initScrollspy() {
    const links = Array.from(document.querySelectorAll(".topnav a"));
    const sections = links
      .map((a) => document.querySelector(a.getAttribute("href")))
      .filter(Boolean);

    const spy = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          links.forEach((a) =>
            a.classList.toggle("active", a.getAttribute("href") === "#" + entry.target.id)
          );
        });
      },
      { rootMargin: "-30% 0px -60% 0px" }
    );
    sections.forEach((s) => spy.observe(s));
  }

  function initReveal() {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("shown");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.08 }
    );
    document.querySelectorAll(".reveal").forEach((n) => io.observe(n));
  }

  /* ---------- PWA ---------- */

  function initPwa() {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("sw.js").catch(() => {});
    }

    let deferredPrompt = null;
    const btn = $("#install-btn");
    window.addEventListener("beforeinstallprompt", (e) => {
      e.preventDefault();
      deferredPrompt = e;
      btn.hidden = false;
    });
    btn.addEventListener("click", async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      await deferredPrompt.userChoice;
      deferredPrompt = null;
      btn.hidden = true;
    });
    window.addEventListener("appinstalled", () => (btn.hidden = true));
  }

  /* ---------- Boot ---------- */

  initTheme();
  renderHero();
  renderStats();
  renderSummary();
  renderImpact();
  renderCareer();
  renderFrameworks();
  initAppControls();
  renderApps();
  renderBooks();
  renderRecommendations();
  renderAwards();
  renderConnect();
  initScrollspy();
  initReveal();
  initPwa();
  $("#year").textContent = String(new Date().getFullYear());
})();
