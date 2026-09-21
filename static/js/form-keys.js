/* Form keys: Ctrl/Cmd+Enter submits the closest form from anywhere inside it.
 * In textareas Enter stays a newline; Ctrl+Enter submits. No dependencies. */
(function () {
  "use strict";
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      const t = e.target;
      if (!t || !t.form) return;
      e.preventDefault();
      if (typeof t.form.requestSubmit === "function") t.form.requestSubmit();
      else t.form.submit();
    }
  });
})();
