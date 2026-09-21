/* Universal table sort: click <th data-sort> to cycle asc -> desc.
 * Engine: PowerSort (adaptive counting/radix/bucket/merge/introsort);
 * falls back to native sort if powersort.js failed to load. */
(function () {
  function cellValue(row, idx) {
    const cell = row.children[idx];
    if (!cell) return "";
    const raw = (cell.innerText || "").trim();
    const num = raw.replace(/\s/g, "").replace(",", ".");
    if (/^-?\d+(\.\d+)?$/.test(num)) return { k: 0, v: parseFloat(num) };
    const ts = Date.parse(raw);
    if (!isNaN(ts) && /\d{4}|\d{2}\.\d{2}\.\d{4}/.test(raw)) return { k: 1, v: ts };
    return { k: 2, v: raw.toLocaleLowerCase("mk-MK") };
  }
  function cmp(a, b, dir) {
    if (a.k !== b.k) return (a.k - b.k) * dir;
    if (typeof a.v === "number" && typeof b.v === "number") return (a.v - b.v) * dir;
    return String(a.v).localeCompare(String(b.v), "mk-MK") * dir;
  }
  function powerOrder(pairs, dir) {
    const numeric = pairs.length > 0 && pairs.every(([k]) => k.k === 0);
    if (numeric) {
      const arr = pairs.slice();
      window.PowerSort.sortBy(arr, (p) => p[0].v, (a, b) => a - b);
      return dir === 1 ? arr : arr.reverse();
    }
    const arr = pairs.slice();
    window.PowerSort.sortBy(
      arr,
      (p) => String(p[0].v),
      (a, b) => a.localeCompare(b, "mk-MK")
    );
    return dir === 1 ? arr : arr.reverse();
  }
  document.querySelectorAll("table.sortable").forEach((table) => {
    const heads = [...table.querySelectorAll("thead th[data-sort]")];
    if (!heads.length) return;
    const body = table.querySelector("tbody");
    if (!body) return;
    const original = [...body.rows];
    let state = { idx: -1, dir: 0 };
    heads.forEach((th) => {
      th.title = "Сортирај";
      th.setAttribute("tabindex", "0");
      const go = () => {
        const idx = [...th.parentElement.children].indexOf(th);
        state = state.idx === idx && state.dir === 1 ? { idx, dir: -1 } : { idx, dir: 1 };
        if (state.dir === 0) {
          original.forEach((r) => body.appendChild(r));
        } else if (window.PowerSort) {
          powerOrder(
            [...body.rows].map((r) => [cellValue(r, idx), r]),
            state.dir
          ).forEach(([, r]) => body.appendChild(r));
        } else {
          [...body.rows]
            .map((r) => [cellValue(r, idx), r])
            .sort((a, b) => cmp(a[0], b[0], state.dir))
            .forEach(([, r]) => body.appendChild(r));
        }
        heads.forEach((h) => h.classList.remove("sort-asc", "sort-desc"));
        th.classList.add(state.dir === 1 ? "sort-asc" : "sort-desc");
      };
      th.addEventListener("click", go);
      th.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); }
      });
    });
  });
})();
