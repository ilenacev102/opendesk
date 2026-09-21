/* Global command palette: Ctrl+K -> live /api/search -> jump. */
(function () {
  const overlay = document.createElement("div");
  overlay.id = "palette";
  overlay.innerHTML =
    '<div class="palette-box">' +
    '<input id="paletteInput" placeholder="Барај уред, сериски, вработен... (Esc за излез)">' +
    '<div id="paletteList"></div>' +
    '<div id="paletteMeta"></div>' +
    "</div>";
  document.body.appendChild(overlay);
  const input = overlay.querySelector("#paletteInput");
  const list = overlay.querySelector("#paletteList");
  const meta = overlay.querySelector("#paletteMeta");
  let results = [];
  let active = -1;
  let timer = null;

  function open() {
    overlay.classList.add("open");
    input.value = "";
    list.innerHTML = "";
    meta.textContent = "";
    active = -1;
    setTimeout(() => input.focus(), 30);
  }
  function close() {
    overlay.classList.remove("open");
  }
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      overlay.classList.contains("open") ? close() : open();
    }
    if (e.key === "Escape") close();
  });
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close();
  });
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(run, 120);
  });
  input.addEventListener("keydown", (e) => {
    const kids = [...list.children];
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!kids.length) return;
      active =
        e.key === "ArrowDown"
          ? (active + 1) % kids.length
          : (active - 1 + kids.length) % kids.length;
      kids.forEach((k, i) => k.classList.toggle("active", i === active));
    } else if (e.key === "Enter" && active >= 0 && results[active]) {
      window.location = results[active].url;
    }
  });
  function run() {
    const q = input.value.trim();
    if (q.length < 2) {
      list.innerHTML = "";
      meta.textContent = "";
      return;
    }
    fetch("/api/search?q=" + encodeURIComponent(q))
      .then((r) => r.json())
      .then((data) => {
        results = data.results || [];
        active = results.length ? 0 : -1;
        list.innerHTML = "";
        results.forEach((it, i) => {
          const a = document.createElement("a");
          a.href = it.url;
          a.className = "palette-item" + (i === 0 ? " active" : "");
          a.innerHTML =
            "<span class='pkind p-" +
            it.kind +
            "'>" +
            (it.kind === "device"
              ? "<svg class='ic' aria-hidden='true'><use href='#i-monitor'/></svg>"
              : "<svg class='ic' aria-hidden='true'><use href='#i-user-plus'/></svg>") +
            "</span><span><b>" +
            it.title +
            "</b><br><small>" +
            it.sub +
            "</small></span>";
          list.appendChild(a);
        });
        meta.textContent = results.length
          ? results.length + " резултати (" + data.ms + "ms)"
          : "Нема резултати";
      });
  }
})();
