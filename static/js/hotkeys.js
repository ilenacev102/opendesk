/* Global keyboard shortcuts for ServiceDesk (Linear-style speed) */
(function () {
  let pendingKey = null;
  let pendingTimer = null;

  function isInputActive() {
    const el = document.activeElement;
    if (!el) return false;
    const tag = el.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
  }

  function showShortcutsModal() {
    const modalEl = document.getElementById("shortcutsModal");
    if (!modalEl || typeof bootstrap === "undefined") return;
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
  }

  document.addEventListener("keydown", (e) => {
    // If inside an input field, only allow Escape
    if (isInputActive()) {
      if (e.key === "Escape") {
        document.activeElement.blur();
      }
      return;
    }

    // Ignore if Ctrl, Alt or Meta is pressed
    if (e.ctrlKey || e.altKey || e.metaKey) return;

    const key = e.key.toLowerCase();

    // Show Shortcuts Sheet
    if (e.key === "?") {
      e.preventDefault();
      showShortcutsModal();
      return;
    }

    // Focus table filter / search
    if (key === "/") {
      e.preventDefault();
      const filterInput = document.querySelector("#tableFilter, input[type=search], input[name=q]");
      if (filterInput) {
        filterInput.focus();
        if (filterInput.select) filterInput.select();
      }
      return;
    }

    // Quick Action: Create New Ticket / Incident
    if (key === "c") {
      e.preventDefault();
      window.location = "/incidents";
      return;
    }

    // Two-key chord navigation: 'g' then X
    if (pendingKey === "g") {
      clearTimeout(pendingTimer);
      pendingKey = null;
      if (key === "i") {
        e.preventDefault();
        window.location = "/incidents";
      } else if (key === "d") {
        e.preventDefault();
        window.location = "/devices";
      } else if (key === "b") {
        e.preventDefault();
        window.location = "/my-board";
      } else if (key === "w") {
        e.preventDefault();
        window.location = "/my-work";
      } else if (key === "p") {
        e.preventDefault();
        window.location = "/projects";
      } else if (key === "h") {
        e.preventDefault();
        window.location = "/history";
      } else if (key === "k") {
        e.preventDefault();
        window.location = "/kb";
      }
      return;
    }

    if (key === "g") {
      pendingKey = "g";
      pendingTimer = setTimeout(() => {
        pendingKey = null;
      }, 1000);
    }
  });
})();
