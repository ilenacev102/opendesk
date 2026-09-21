/* Smart defaults: remember last-used values per field group (localStorage).
 * Opt-in: <input data-remember="Location"> — on submit the value is stored;
 * on load, empty fields are prefilled. No dependencies. */
(function () {
  "use strict";
  var PREFIX = "sdDefault_";
  function store() {
    try {
      return window.localStorage;
    } catch (e) {
      return null;
    }
  }
  function fill() {
    var ls = store();
    if (!ls) return;
    document.querySelectorAll("[data-remember]").forEach(function (el) {
      if (el.value) return;
      var saved = ls.getItem(PREFIX + el.getAttribute("data-remember"));
      if (saved !== null && saved !== "") el.value = saved;
    });
  }
  function learn(form) {
    var ls = store();
    if (!ls) return;
    form.querySelectorAll("[data-remember]").forEach(function (el) {
      if (el.value) ls.setItem(PREFIX + el.getAttribute("data-remember"), el.value);
    });
  }
  document.addEventListener("submit", function (e) {
    if (e.target && e.target.tagName === "FORM") learn(e.target);
  });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", fill);
  } else {
    fill();
  }
})();
