const fs = require("fs");
const path = require("path");

const store = {};
global.window = {
  localStorage: {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => {
      store[k] = String(v);
    },
  },
};
function fakeEl() {
  return {
    value: "",
    style: {},
    dataset: {},
    classList: { toggle() {} },
    setAttribute() {},
    addEventListener() {},
    appendChild() {},
    parentElement: { style: {}, appendChild() {} },
  };
}
global.document = {
  createElement: () => fakeEl(),
  addEventListener: () => {},
  querySelectorAll: () => [],
};

const src = fs.readFileSync(
  path.join(__dirname, "..", "static", "js", "autocomplete.js"),
  "utf8"
);
eval(src + "\nglobalThis.__AC = AutoComplete;");
const AutoComplete = globalThis.__AC;

function makeInstance() {
  const input = fakeEl();
  input.parentElement = { style: {}, appendChild() {} };
  const items = [
    { value: "E1", search: "ana petrovska" },
    { value: "E2", search: "ana trajkovska" },
  ];
  return new AutoComplete(input, items, { freqKey: "emp" });
}
let base = makeInstance();
base.input.value = "ana";
base.search();
const baseFirst = base.filtered[0].value;

for (let k = 0; k < 2; k++) {
  const m = makeInstance();
  m.input.value = "ana";
  m.search();
  const idx = m.filtered.findIndex((it) => it.value === "E2");
  if (idx < 0) {
    console.error("E2 not found in results");
    process.exit(2);
  }
  m.pick(idx);
}

const after = makeInstance();
after.input.value = "ana";
after.search();
const top = after.filtered[0].value;

if (baseFirst !== "E1") {
  console.error("baseline order broken, first=" + baseFirst);
  process.exit(2);
}
if (top !== "E2") {
  console.error("frequency did not promote, top=" + top);
  process.exit(1);
}
console.log("OK top=" + top);
