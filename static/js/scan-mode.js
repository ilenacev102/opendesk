/* Scan mode (?scan=1): keeps focus on the scan field, preserves the flag
 * across submits, and beeps on flash outcome. USB scanners act as keyboards.
 * No dependencies. AudioContext may stay suspended until user gesture. */
(function () {
  "use strict";
  var params = new URLSearchParams(window.location.search);
  if (params.get("scan") !== "1") return;
  document.body.classList.add("scan-on");
  document.querySelectorAll("form").forEach(function (f) {
    var action = f.getAttribute("action");
    if (action && action.charAt(0) === "/" && action.indexOf("scan=") < 0) {
      f.setAttribute(
        "action",
        action + (action.indexOf("?") < 0 ? "?" : "&") + "scan=1"
      );
    }
  });
  function beep(freq, dur, delay) {
    try {
      var Ctor = window.AudioContext || window.webkitAudioContext;
      if (!Ctor) return;
      var ctx = new Ctor();
      var o = ctx.createOscillator();
      var g = ctx.createGain();
      o.connect(g);
      g.connect(ctx.destination);
      o.frequency.value = freq;
      var t = ctx.currentTime + (delay || 0);
      g.gain.setValueAtTime(0.001, t);
      g.gain.exponentialRampToValueAtTime(0.4, t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.001, t + dur);
      o.start(t);
      o.stop(t + dur + 0.05);
    } catch (e) {
      /* silent: beep is best-effort */
    }
  }
  var ok = document.querySelector(".alert-success");
  var err = document.querySelector(".alert-danger");
  if (ok && !err) {
    beep(880, 0.12, 0);
  } else if (err) {
    beep(220, 0.15, 0);
    beep(160, 0.2, 0.18);
  }
  var target = document.querySelector("[data-scan]");
  if (target) target.focus();
})();
