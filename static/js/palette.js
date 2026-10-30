/* Global command palette 2.0: Ctrl+K / Spotlight with Quick Actions & Live Search */
(function () {
  const ACTIONS = [
    { title: "Нов инцидент / тикет", sub: "Отвори листа и форма за тикет (кратенка: c)", url: "/incidents", kind: "action", icon: "i-plus" },
    { title: "Задолжи уред (Checkout)", sub: "Задолжување опрема на вработен", url: "/assign", kind: "action", icon: "i-user-plus" },
    { title: "Раздолжи опрема (Checkin)", sub: "Поединечен или групен поврат", url: "/return", kind: "action", icon: "i-swap" },
    { title: "Регистрирај нов уред", sub: "Внеси ново средство во залиха", url: "/devices/new", kind: "action", icon: "i-plus" },
    { title: "Брз поврат (Quick Return)", sub: "Раздолжување со баркод/QR", url: "/quick-return", kind: "action", icon: "i-bolt" },
    { title: "Канбан табла", sub: "Преглед на задачи по статус (кратенка: g b)", url: "/my-board", kind: "action", icon: "i-clip" },
    { title: "Моја работа", sub: "Отворени тикети и рокови (кратенка: g w)", url: "/my-work", kind: "action", icon: "i-check" },
    { title: "Проекти и тимови", sub: "Спринтови и типови задачи (кратенка: g p)", url: "/projects", kind: "action", icon: "i-box" },
    { title: "База на знаење (KB)", sub: "Упатства и решенија (кратенка: g k)", url: "/kb", kind: "action", icon: "i-file" },
    { title: "Смени тема (Темна / Светла)", sub: "Префрли меѓу темна и светла тема", action: "toggleTheme", kind: "action", icon: "i-sun" },
    { title: "Кратенки на тастатура", sub: "Прикажи водич за брзи кратенки (?)", action: "showShortcuts", kind: "action", icon: "i-bolt" }
  ];

  const overlay = document.createElement("div");
  overlay.id = "palette";
  overlay.innerHTML =
    '<div class="palette-box">' +
    '<input id="paletteInput" placeholder="Барај акција, уред, вработен... (Esc за излез)">' +
    '<div id="paletteList"></div>' +
    '<div id="paletteMeta"></div>' +
    '</div>';
  document.body.appendChild(overlay);

  const input = overlay.querySelector("#paletteInput");
  const list = overlay.querySelector("#paletteList");
  const meta = overlay.querySelector("#paletteMeta");
  let currentItems = [];
  let activeIndex = -1;
  let debounceTimer = null;

  function render(items, metaText) {
    currentItems = items;
    list.innerHTML = "";
    activeIndex = items.length ? 0 : -1;

    items.forEach((it, i) => {
      const a = document.createElement("a");
      a.href = it.url || "#";
      a.className = "palette-item" + (i === 0 ? " active" : "");
      
      let iconName = "i-search";
      if (it.icon) iconName = it.icon;
      else if (it.kind === "device") iconName = "i-monitor";
      else if (it.kind === "employee") iconName = "i-user-plus";

      a.innerHTML =
        '<span class="pkind p-' + (it.kind || "default") + '">' +
        '<svg class="ic" aria-hidden="true"><use href="#' + iconName + '"/></svg>' +
        '</span><span><b>' +
        it.title +
        '</b><br><small class="text-muted">' +
        (it.sub || "") +
        '</small></span>';

      a.addEventListener("click", (e) => {
        e.preventDefault();
        execute(it);
      });
      list.appendChild(a);
    });

    meta.textContent = metaText || (items.length + " ставки");
  }

  function execute(item) {
    if (!item) return;
    if (item.action === "toggleTheme") {
      const btn = document.getElementById("themeToggle");
      if (btn) btn.click();
      close();
      return;
    }
    if (item.action === "showShortcuts") {
      close();
      const modalEl = document.getElementById("shortcutsModal");
      if (modalEl && typeof bootstrap !== "undefined") {
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
      }
      return;
    }
    if (item.url) {
      window.location = item.url;
    }
  }

  function open() {
    overlay.classList.add("open");
    input.value = "";
    render(ACTIONS, "Брзи дејства и навигација");
    setTimeout(() => input.focus(), 30);
  }

  function close() {
    overlay.classList.remove("open");
  }

  window.ServiceDeskPalette = { open, close };

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      overlay.classList.contains("open") ? close() : open();
    }
    if (e.key === "Escape" && overlay.classList.contains("open")) {
      close();
    }
  });

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close();
  });

  input.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(runQuery, 100);
  });

  input.addEventListener("keydown", (e) => {
    const kids = [...list.children];
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!kids.length) return;
      activeIndex =
        e.key === "ArrowDown"
          ? (activeIndex + 1) % kids.length
          : (activeIndex - 1 + kids.length) % kids.length;
      kids.forEach((k, i) => k.classList.toggle("active", i === activeIndex));
      kids[activeIndex]?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (activeIndex >= 0 && currentItems[activeIndex]) {
        execute(currentItems[activeIndex]);
      }
    }
  });

  function runQuery() {
    const q = input.value.trim().toLowerCase();
    if (!q) {
      render(ACTIONS, "Брзи дејства и навигација");
      return;
    }

    const matchedActions = ACTIONS.filter(
      (a) => a.title.toLowerCase().includes(q) || a.sub.toLowerCase().includes(q)
    );

    if (q.length < 2) {
      render(matchedActions, matchedActions.length + " акции");
      return;
    }

    fetch("/api/search?q=" + encodeURIComponent(q))
      .then((r) => r.json())
      .then((data) => {
        const results = data.results || [];
        const combined = [...matchedActions, ...results];
        render(combined, combined.length + " резултати (" + (data.ms || 0) + "ms)");
      })
      .catch(() => {
        render(matchedActions, matchedActions.length + " акции");
      });
  }
})();
