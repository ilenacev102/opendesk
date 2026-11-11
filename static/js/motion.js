/**
 * ServiceDesk Motion & Interactive System
 * GPU-accelerated micro-interactions, spotlight card illumination,
 * click ripples, kinetic drag feedback, and canvas celebration.
 * Respects prefers-reduced-motion and CSP nonce standards.
 */

(function () {
  "use strict";

  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ==========================================================================
     1. Spotlight Card Illumination (Cursor tracking on cards)
     ========================================================================== */
  if (!prefersReduced) {
    let activeCard = null;
    let cardRect = null;

    document.addEventListener("pointermove", (e) => {
      const card = e.target.closest(
        ".sd-card, .stat-card, .panel-card, .qa-card, .kanban-card, .card-spotlight"
      );

      if (!card) {
        if (activeCard) {
          activeCard = null;
          cardRect = null;
        }
        return;
      }

      if (card !== activeCard) {
        activeCard = card;
        cardRect = card.getBoundingClientRect();
        if (!card.classList.contains("card-spotlight")) {
          card.classList.add("card-spotlight");
        }
      }

      if (cardRect) {
        const x = e.clientX - cardRect.left;
        const y = e.clientY - cardRect.top;
        card.style.setProperty("--mouse-x", `${x}px`);
        card.style.setProperty("--mouse-y", `${y}px`);
      }
    }, { passive: true });
  }

  /* ==========================================================================
     2. Tactile Click Ripple on Buttons and Commands
     ========================================================================== */
  if (!prefersReduced) {
    document.addEventListener("click", (e) => {
      const target = e.target.closest(".btn, .command-action, .qa-card, .filter-tabs a");
      if (!target || target.disabled || target.classList.contains("disabled")) return;

      const rect = target.getBoundingClientRect();
      const diameter = Math.max(rect.width, rect.height);
      const radius = diameter / 2;

      const ripple = document.createElement("span");
      ripple.className = "sd-ripple";
      ripple.style.width = ripple.style.height = `${diameter}px`;
      ripple.style.left = `${e.clientX - rect.left - radius}px`;
      ripple.style.top = `${e.clientY - rect.top - radius}px`;

      target.appendChild(ripple);
      setTimeout(() => ripple.remove(), 600);
    });
  }

  /* ==========================================================================
     3. Animated Alert Timer Progress Bar & Smooth Dismiss
     ========================================================================== */
  document.querySelectorAll(".alert-dismissible").forEach((alert) => {
    if (!alert.querySelector(".alert-progress")) {
      const progress = document.createElement("div");
      progress.className = "alert-progress";
      alert.appendChild(progress);
    }
  });

  /* ==========================================================================
     4. Canvas Confetti Celebration (Zero dependencies, pure Canvas)
     ========================================================================== */
  function sdConfetti(opts = {}) {
    if (prefersReduced) return;

    let canvas = document.getElementById("sdConfettiCanvas");
    if (!canvas) {
      canvas = document.createElement("canvas");
      canvas.id = "sdConfettiCanvas";
      document.body.appendChild(canvas);
    }

    const ctx = canvas.getContext("2d");
    const width = (canvas.width = window.innerWidth);
    const height = (canvas.height = window.innerHeight);

    const colors = [
      "#2563eb", "#3b82f6", "#10b981", "#34d399",
      "#f59e0b", "#fbbf24", "#8b5cf6", "#ec4899"
    ];

    const particleCount = opts.count || 75;
    const particles = [];

    const originX = opts.x !== undefined ? opts.x : width / 2;
    const originY = opts.y !== undefined ? opts.y : height * 0.35;

    for (let i = 0; i < particleCount; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = Math.random() * 9 + 4;
      particles.push({
        x: originX,
        y: originY,
        vx: Math.cos(angle) * speed * (0.8 + Math.random() * 0.6),
        vy: (Math.sin(angle) * speed - 4) * (0.8 + Math.random() * 0.6),
        w: Math.random() * 8 + 5,
        h: Math.random() * 5 + 3,
        color: colors[Math.floor(Math.random() * colors.length)],
        rotation: Math.random() * 360,
        vr: (Math.random() - 0.5) * 12,
        opacity: 1,
        gravity: 0.22,
        drag: 0.985
      });
    }

    let start = null;
    const duration = opts.duration || 2400;

    function frame(timestamp) {
      if (!start) start = timestamp;
      const elapsed = timestamp - start;
      const progress = elapsed / duration;

      ctx.clearRect(0, 0, width, height);

      let alive = false;
      for (let p of particles) {
        p.vx *= p.drag;
        p.vy = p.vy * p.drag + p.gravity;
        p.x += p.vx;
        p.y += p.vy;
        p.rotation += p.vr;
        p.opacity = Math.max(0, 1 - progress);

        if (p.opacity > 0 && p.y < height + 20) {
          alive = true;
          ctx.save();
          ctx.translate(p.x, p.y);
          ctx.rotate((p.rotation * Math.PI) / 180);
          ctx.globalAlpha = p.opacity;
          ctx.fillStyle = p.color;
          ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
          ctx.restore();
        }
      }

      if (alive && progress < 1) {
        requestAnimationFrame(frame);
      } else {
        ctx.clearRect(0, 0, width, height);
        canvas.remove();
      }
    }

    requestAnimationFrame(frame);
  }

  window.sdConfetti = sdConfetti;

  /* Trigger celebratory confetti automatically if a success alert is shown */
  const successAlert = document.querySelector(".alert-success");
  if (successAlert) {
    setTimeout(() => {
      const rect = successAlert.getBoundingClientRect();
      sdConfetti({
        x: rect.left + rect.width / 2,
        y: rect.bottom,
        count: 55
      });
    }, 180);
  }

  /* ==========================================================================
     5. Kanban Drag-and-Drop Kinetic Interactions
     ========================================================================== */
  document.addEventListener("dragstart", (e) => {
    const card = e.target.closest(".kanban-card");
    if (card) {
      card.classList.add("is-dragging");
    }
  });

  document.addEventListener("dragend", (e) => {
    const card = e.target.closest(".kanban-card");
    if (card) {
      card.classList.remove("is-dragging");
    }
    document.querySelectorAll(".kanban-dropzone").forEach((z) => {
      z.classList.remove("drag-active");
    });
  });

  document.addEventListener("dragover", (e) => {
    const zone = e.target.closest(".kanban-dropzone");
    if (zone) {
      zone.classList.add("drag-active");
    }
  });

  document.addEventListener("dragleave", (e) => {
    const zone = e.target.closest(".kanban-dropzone");
    if (zone && !zone.contains(e.relatedTarget)) {
      zone.classList.remove("drag-active");
    }
  });

  /* ==========================================================================
     6. Smooth Stat Number Count-up for any [data-count] element
     ========================================================================== */
  if (!prefersReduced) {
    document.querySelectorAll("[data-count]").forEach((el) => {
      const target = parseInt(el.dataset.count, 10);
      if (isNaN(target)) return;

      const duration = 750;
      const startTime = performance.now();

      function update(now) {
        const elapsed = now - startTime;
        const p = Math.min(elapsed / duration, 1);
        // easeOutCubic
        const current = Math.round(target * (1 - Math.pow(1 - p, 3)));
        el.textContent = current;

        if (p < 1) {
          requestAnimationFrame(update);
        } else {
          el.textContent = target;
        }
      }

      requestAnimationFrame(update);
    });
  }

})();
