/* Instant table filtering on the client for sub-5ms search */
(function () {
  document.addEventListener("DOMContentLoaded", () => {
    const filterInput = document.querySelector("#tableFilter, input[name='q'], input[name='filter']");
    const table = document.querySelector(".table-responsive table tbody");
    if (!filterInput || !table) return;

    let debounceTimer = null;
    filterInput.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        const query = filterInput.value.toLowerCase().trim();
        const rows = table.querySelectorAll("tr");
        let visibleCount = 0;

        rows.forEach((row) => {
          if (!query) {
            row.style.display = "";
            visibleCount++;
            return;
          }

          const text = row.textContent.toLowerCase();
          const match = query.split(/\s+/).every((word) => text.includes(word));
          if (match) {
            row.style.display = "";
            visibleCount++;
          } else {
            row.style.display = "none";
          }
        });

        const counterEl = document.querySelector("#filterCount, .table-count");
        if (counterEl) {
          counterEl.textContent = `Прикажани ${visibleCount} од ${rows.length}`;
        }
      }, 50);
    });
  });
})();
