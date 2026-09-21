/* Instant autocomplete: substring match, keyboard nav, detail preview.
 * Usage: new AutoComplete(inputEl, items, {label: fn, onPick: fn}) */
class AutoComplete {
  constructor(input, items, opts = {}) {
    this.input = input;
    this.items = items;
    this.label = opts.label || ((x) => x.value);
    this.onPick = opts.onPick || (() => {});
    this.freqKey = opts.freqKey || "";
    this.freqPrefix = "sdFreq_";
    this.box = document.createElement("div");
    this.box.className = "ac-list list-group position-absolute w-100";
    this.box.style.zIndex = "1000";
    this.box.style.display = "none";
    input.parentElement.style.position = "relative";
    input.parentElement.appendChild(this.box);
    this.active = -1;
    this.filtered = [];
    input.setAttribute("autocomplete", "off");
    input.addEventListener("input", () => this.search());
    input.addEventListener("keydown", (e) => this.keys(e));
    document.addEventListener("click", (e) => {
      if (!this.box.contains(e.target) && e.target !== input) this.hide();
    });
  }
  norm(s) {
    return (s || "").toLowerCase();
  }
  freqOf(value) {
    if (!this.freqKey) return 0;
    try {
      const raw = window.localStorage.getItem(this.freqPrefix + this.freqKey);
      if (!raw) return 0;
      const all = JSON.parse(raw);
      return all[value] || 0;
    } catch (e) {
      return 0;
    }
  }
  freqBump(value) {
    if (!this.freqKey) return;
    try {
      const k = this.freqPrefix + this.freqKey;
      const all = JSON.parse(window.localStorage.getItem(k) || "{}");
      all[value] = (all[value] || 0) + 1;
      window.localStorage.setItem(k, JSON.stringify(all));
    } catch (e) {
      /* best-effort */
    }
  }
  score(it, words) {
    const hay = this.norm(it.search);
    const tokens = hay.split(/\s+/);
    let total = 0;
    for (const w of words) {
      if (tokens.includes(w)) total += 100;
      else if (tokens.some((t) => t.startsWith(w))) total += 80;
      else if (hay.includes(w)) total += 60;
      else {
        let pi = 0, gaps = 0;
        for (const ch of hay) {
          if (ch === w[pi]) pi++;
          else if (pi > 0) gaps++;
          if (pi === w.length) break;
        }
        if (pi === w.length) total += Math.max(10, 40 - gaps);
        else return -1;
      }
    }
    return total;
  }
  search() {
    const q = this.norm(this.input.value.trim());
    this.box.innerHTML = "";
    this.active = -1;
    if (q.length < 1) {
      this.hide();
      return;
    }
    const words = q.split(/\s+/);
    const self = this;
    this.filtered = this.items
      .map((it) => {
        const base = self.score(it, words);
        if (base < 0) return [-1, it];
        return [base + Math.min(self.freqOf(it.value) * 10, 50), it];
      })
      .filter(([s]) => s >= 0)
      .sort((a, b) => b[0] - a[0])
      .slice(0, 8)
      .map(([, it]) => it);
    if (!this.filtered.length) {
      this.hide();
      return;
    }
    this.filtered.forEach((it, i) => {
      const a = document.createElement("button");
      a.type = "button";
      a.className = "list-group-item list-group-item-action";
      a.innerHTML = this.label(it);
      a.addEventListener("click", () => this.pick(i));
      this.box.appendChild(a);
    });
    this.box.style.display = "block";
  }
  keys(e) {
    const kids = [...this.box.children];
    if (!kids.length) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      this.active =
        e.key === "ArrowDown"
          ? (this.active + 1) % kids.length
          : (this.active - 1 + kids.length) % kids.length;
      kids.forEach((k, i) =>
        k.classList.toggle("active", i === this.active)
      );
    } else if (e.key === "Enter" && this.active >= 0) {
      e.preventDefault();
      this.pick(this.active);
    } else if (e.key === "Escape") {
      this.hide();
    }
  }
  pick(i) {
    const it = this.filtered[i];
    this.input.value = it.value;
    this.freqBump(it.value);
    this.hide();
    this.onPick(it);
  }
  hide() {
    this.box.style.display = "none";
    this.active = -1;
  }
}
