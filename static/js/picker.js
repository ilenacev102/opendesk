/* DevicePicker: type serial/inventory/brand/model -> full-data results -> chips.
 * Usage: new DevicePicker(inputId, listId, hiddenName, items[, formEl])
 * formEl is required when the input lives outside the target form. */
class DevicePicker {
  constructor(inputId, listId, hiddenName, items, formEl) {
    this.input = document.getElementById(inputId);
    this.list = document.getElementById(listId);
    if (!this.input || !this.list) return;
    this.hiddenName = hiddenName;
    this.items = items;
    this.picked = new Map();
    this.form = formEl || this.input.closest("form");
    this.input.setAttribute("autocomplete", "off");
    this.input.addEventListener("input", () => this.search());
    this.input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const first = this.list.querySelector("button");
        if (first) first.click();
      }
      if (e.key === "Escape") this.list.innerHTML = "";
    });
    document.addEventListener("click", (e) => {
      if (!this.list.contains(e.target) && e.target !== this.input) {
        this.list.innerHTML = "";
      }
    });
    if (this.form) this.form.addEventListener("submit", () => this.sync());
  }
  search() {
    const words = this.input.value.trim().toLowerCase().split(/\s+/);
    this.list.innerHTML = "";
    if (!words[0]) return;
    const hits = this.items
      .filter(
        (d) =>
          !this.picked.has(d.AssetID) &&
          words.every((w) =>
            (
              d.AssetID +
              " " +
              d.SerialNumber +
              " " +
              d.Manufacturer +
              " " +
              d.Model +
              " " +
              d.Type +
              " " +
              d.Status
            )
              .toLowerCase()
              .includes(w)
          )
      )
      .slice(0, 8);
    hits.forEach((d) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "list-group-item list-group-item-action";
      b.innerHTML =
        "<b>" +
        d.AssetID +
        "</b> " +
        d.Manufacturer +
        " " +
        d.Model +
        "<br><small>SN: " +
        d.SerialNumber +
        " | " +
        d.Type +
        " | " +
        d.Status +
        " | " +
        d.Location +
        "</small>";
      b.addEventListener("click", () => this.add(d));
      this.list.appendChild(b);
    });
  }
  add(d) {
    this.picked.set(d.AssetID, d);
    this.input.value = "";
    this.list.innerHTML = "";
    this.render();
    this.input.focus();
  }
  remove(id) {
    this.picked.delete(id);
    this.render();
  }
  render() {
    let chips = document.getElementById(this.list.id + "-chips");
    if (!chips) {
      chips = document.createElement("div");
      chips.id = this.list.id + "-chips";
      chips.className = "mt-2";
      this.list.after(chips);
    }
    chips.innerHTML = "";
    this.picked.forEach((d) => {
      const s = document.createElement("span");
      s.className = "badge bg-primary me-2 mb-2 p-2";
      s.style.fontSize = "0.9rem";
      s.innerHTML =
        d.AssetID +
        " " +
        d.Model +
        ' <a href="#" style="color:#fff;text-decoration:none;">✕</a>';
      s.querySelector("a").addEventListener("click", (e) => {
        e.preventDefault();
        this.remove(d.AssetID);
      });
      chips.appendChild(s);
    });
    const n = this.picked.size;
    let counter = document.getElementById(this.list.id + "-count");
    if (!counter) {
      counter = document.createElement("div");
      counter.id = this.list.id + "-count";
      counter.className = "form-text";
      chips.after(counter);
    }
    counter.textContent = n ? "Избрани: " + n : "";
  }
  sync() {
    if (!this.form) return;
    this.form
      .querySelectorAll("input[data-picker='" + this.list.id + "']")
      .forEach((el) => el.remove());
    this.picked.forEach((d) => {
      const h = document.createElement("input");
      h.type = "hidden";
      h.name = this.hiddenName;
      h.value = d.AssetID;
      h.setAttribute("data-picker", this.list.id);
      this.form.appendChild(h);
    });
  }
}
