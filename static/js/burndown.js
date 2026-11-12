/* Sprint analytics: vanilla-canvas burndown + velocity renderer.
 * Reads window.sdBurndown / window.sdVelocity set by the sprint_analytics template.
 * No external chart libraries (CSP-safe, offline-friendly). */
(function () {
  "use strict";

  function cssVar(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  function themeColors() {
    var dark = document.documentElement.getAttribute("data-bs-theme") === "dark";
    return {
      text: dark ? "#e6edf5" : "#1c2733",
      grid: dark ? "rgba(230,237,245,0.12)" : "rgba(28,39,51,0.08)",
      accent: cssVar("--sd-accent", dark ? "#60a5fa" : "#2563eb"),
      good: dark ? "#4ade80" : "#16a34a",
      muted: dark ? "rgba(230,237,245,0.55)" : "rgba(28,39,51,0.55)",
    };
  }

  function setupCanvas(canvas) {
    var dpr = window.devicePixelRatio || 1;
    var width = canvas.clientWidth || canvas.parentElement.clientWidth || 600;
    var height = 260;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.height = height + "px";
    var ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx: ctx, width: width, height: height };
  }

  function axes(ctx, box, colors) {
    ctx.strokeStyle = colors.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(box.left, box.top);
    ctx.lineTo(box.left, box.bottom);
    ctx.lineTo(box.right, box.bottom);
    ctx.stroke();
  }

  function drawBurndown(canvas, data) {
    if (!canvas || !data || !Array.isArray(data.days) || data.days.length === 0) return;
    var colors = themeColors();
    var c = setupCanvas(canvas);
    var ctx = c.ctx;
    var pad = { l: 44, r: 16, t: 16, b: 28 };
    var box = {
      left: pad.l,
      top: pad.t,
      right: c.width - pad.r,
      bottom: c.height - pad.b,
    };
    var n = data.days.length;
    var max = Math.max(data.total, 1);
    var xs = data.days.map(function (_, i) {
      return box.left + (box.right - box.left) * (n === 1 ? 0 : i / (n - 1));
    });
    var ys = function (v) {
      return box.bottom - (box.bottom - box.top) * (v / max);
    };

    axes(ctx, box, colors);
    ctx.font = "11px system-ui, sans-serif";
    ctx.fillStyle = colors.muted;
    ctx.textAlign = "center";
    var every = Math.ceil(n / 8);
    data.days.forEach(function (d, i) {
      if (i % every === 0) {
        ctx.fillText(d.slice(5), xs[i], c.height - 8);
      }
    });
    ctx.textAlign = "right";
    var steps = 4;
    for (var s = 0; s <= steps; s++) {
      var v = Math.round((max * s) / steps);
      ctx.fillText(String(v), box.left - 6, ys(v) + 4);
    }

    // ideal line (dashed)
    ctx.strokeStyle = colors.muted;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    data.ideal.forEach(function (v, i) {
      if (i === 0) ctx.moveTo(xs[i], ys(v));
      else ctx.lineTo(xs[i], ys(v));
    });
    ctx.stroke();
    ctx.setLineDash([]);

    // remaining line
    ctx.strokeStyle = colors.accent;
    ctx.lineWidth = 2;
    ctx.beginPath();
    data.remaining.forEach(function (v, i) {
      if (i === 0) ctx.moveTo(xs[i], ys(v));
      else ctx.lineTo(xs[i], ys(v));
    });
    ctx.stroke();
    ctx.lineWidth = 1;
  }

  function drawVelocity(canvas, rows, currentId) {
    if (!canvas || !Array.isArray(rows) || rows.length === 0) return;
    var colors = themeColors();
    var c = setupCanvas(canvas);
    var ctx = c.ctx;
    var pad = { l: 44, r: 16, t: 16, b: 28 };
    var box = {
      left: pad.l,
      top: pad.t,
      right: c.width - pad.r,
      bottom: c.height - pad.b,
    };
    var n = rows.length;
    var max = Math.max(1, Math.max.apply(null, rows.map(function (r) {
      return Math.max(r.Committed, r.Completed);
    })));
    var slot = (box.right - box.left) / n;
    var bw = Math.min(28, slot / 3);

    axes(ctx, box, colors);
    ctx.font = "11px system-ui, sans-serif";
    ctx.fillStyle = colors.muted;
    ctx.textAlign = "right";
    var steps = 4;
    for (var s = 0; s <= steps; s++) {
      var v = Math.round((max * s) / steps);
      ctx.fillText(String(v), box.left - 6, box.bottom - (box.bottom - box.top) * (s / steps) + 4);
    }

    rows.forEach(function (r, i) {
      var cx = box.left + slot * i + slot / 2;
      var hC = (box.bottom - box.top) * (r.Committed / max);
      var hD = (box.bottom - box.top) * (r.Completed / max);
      ctx.fillStyle = r.SprintID === currentId ? colors.good : colors.grid;
      ctx.fillRect(cx - bw - 2, box.bottom - hC, bw, hC);
      ctx.fillStyle = colors.accent;
      ctx.fillRect(cx + 2, box.bottom - hD, bw, hD);
      ctx.fillStyle = colors.muted;
      ctx.textAlign = "center";
      ctx.fillText(String(r.Name).slice(0, 10), cx, c.height - 8);
    });
  }

  function render() {
    drawBurndown(document.getElementById("cvBurndown"), window.sdBurndown);
    drawVelocity(
      document.getElementById("cvVelocity"),
      window.sdVelocity,
      window.sdVelocityCurrent
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", render);
  } else {
    render();
  }
  if (window.matchMedia) {
    window
      .matchMedia("(prefers-color-scheme: dark)")
      .addEventListener("change", render);
  }
  document.addEventListener("sd-theme", render);
})();
