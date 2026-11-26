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

  /* ==========================================================================
     7. Slide-Over Peek Drawer Controller (Linear Style)
     ========================================================================== */
  // Escape server-provided strings before any innerHTML interpolation (XSS guard).
  function escSd(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  const drawerEl = document.getElementById("sdDrawer");
  const drawerBackdrop = document.getElementById("sdDrawerBackdrop");
  const drawerCloseBtn = document.getElementById("sdDrawerClose");
  const drawerTitle = document.getElementById("sdDrawerTitle");
  const drawerBadge = document.getElementById("sdDrawerBadge");
  const drawerLoading = document.querySelector(".sd-drawer-loading");
  const drawerContent = document.getElementById("sdDrawerContent");
  const drawerFullLink = document.getElementById("sdDrawerFullLink");
  const drawerActionBtn = document.getElementById("sdDrawerActionBtn");

  function sdOpenDrawer(opts = {}) {
    if (!drawerEl || !drawerBackdrop) return;
    if (opts.title && drawerTitle) drawerTitle.textContent = opts.title;
    if (opts.badge && drawerBadge) {
      drawerBadge.textContent = opts.badge;
      drawerBadge.className = `badge badge-st ${opts.badgeClass || "st-Assigned"}`;
    }
    if (drawerFullLink) {
      if (opts.fullLink) {
        drawerFullLink.href = opts.fullLink;
        drawerFullLink.classList.remove("d-none");
      } else {
        drawerFullLink.classList.add("d-none");
      }
    }

    if (opts.loading) {
      if (drawerLoading) drawerLoading.classList.remove("d-none");
      if (drawerContent) drawerContent.innerHTML = "";
    } else if (opts.content) {
      if (drawerLoading) drawerLoading.classList.add("d-none");
      if (drawerContent) drawerContent.innerHTML = opts.content;
    }

    drawerBackdrop.classList.add("show");
    drawerEl.classList.add("open");
    drawerEl.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function sdCloseDrawer() {
    if (!drawerEl || !drawerBackdrop) return;
    drawerEl.classList.remove("open");
    drawerBackdrop.classList.remove("show");
    drawerEl.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  if (drawerCloseBtn) drawerCloseBtn.addEventListener("click", sdCloseDrawer);
  if (drawerBackdrop) drawerBackdrop.addEventListener("click", sdCloseDrawer);
  if (drawerActionBtn) drawerActionBtn.addEventListener("click", sdCloseDrawer);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drawerEl && drawerEl.classList.contains("open")) {
      sdCloseDrawer();
    }
  });

  window.sdOpenDrawer = sdOpenDrawer;
  window.sdCloseDrawer = sdCloseDrawer;

  /* ==========================================================================
     8. Kanban Card Peek Integration
     ========================================================================== */
  document.addEventListener("click", (e) => {
    const card = e.target.closest(".kanban-card");
    if (!card) return;
    if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey) return;
    e.preventDefault();

    const incidentId = card.dataset.incidentId;
    const currentStatus = card.dataset.status || "open";
    if (!incidentId) return;

    sdOpenDrawer({
      title: `${incidentId} — Вчитување...`,
      badge: currentStatus,
      fullLink: `/incidents/${incidentId}`,
      loading: true
    });

    fetch(`/incidents/${incidentId}?format=json`, {
      headers: { "Accept": "application/json", "X-Requested-With": "XMLHttpRequest" }
    })
      .then((res) => res.json())
      .then((data) => {
        if (!data || !data.IncidentID) {
          throw new Error("Невалидни податоци");
        }
        let priorityBadge = "";
        if (data.Priority === "urgent") {
          priorityBadge = '<span class="badge badge-st st-Broken">urgent</span>';
        } else if (data.Priority === "high") {
          priorityBadge = '<span class="badge badge-st st-Repair">high</span>';
        } else if (data.Priority === "medium") {
          priorityBadge = '<span class="badge badge-st st-Assigned">medium</span>';
        } else {
          priorityBadge = '<span class="badge badge-st st-Repaired">low</span>';
        }

        let threadHtml = "";
        if (data.thread && data.thread.length > 0) {
          threadHtml = '<div class="mt-4"><h6 class="fw-bold mb-2">Последна активност</h6><ul class="list-group list-group-flush border-top border-bottom">';
          data.thread.forEach((c) => {
            threadHtml += `<li class="list-group-item px-0 py-2">
              <div class="d-flex justify-content-between small text-muted"><strong>${escSd(c.Author)}</strong><span>${escSd(c.Created)}</span></div>
              <div class="small mt-1">${escSd(c.Body)}</div>
            </li>`;
          });
          threadHtml += "</ul></div>";
        }

        const html = `
          <div class="mb-3">
            <h5 class="fw-bold mb-2">${escSd(data.Title)}</h5>
            <div class="d-flex align-items-center gap-2 flex-wrap mb-3">
              ${priorityBadge}
              <span class="badge badge-st st-Assigned">${escSd(data.Status) || "open"}</span>
              ${data.StoryPoints ? `<span class="badge badge-st st-Assigned">${escSd(data.StoryPoints)}п</span>` : ""}
            </div>
            <dl class="row small g-2 mb-0">
              <dt class="col-sm-4 text-muted">Носител</dt>
              <dd class="col-sm-8 mb-1">${escSd(data.Assignee) || "—"}</dd>
              <dt class="col-sm-4 text-muted">Уред</dt>
              <dd class="col-sm-8 mb-1">${data.AssetID ? `<a href="/device/${escSd(data.AssetID)}">${escSd(data.AssetID)}</a>` : "—"}</dd>
              <dt class="col-sm-4 text-muted">Вработен</dt>
              <dd class="col-sm-8 mb-1">${escSd(data.EmployeeID) || "—"}</dd>
              <dt class="col-sm-4 text-muted">Креиран</dt>
              <dd class="col-sm-8 mb-1">${escSd(data.Created) || "—"}</dd>
              <dt class="col-sm-4 text-muted">Рок</dt>
              <dd class="col-sm-8 mb-1">${escSd(data.DueDate) || "—"}</dd>
              <dt class="col-sm-4 text-muted">Забелешка</dt>
              <dd class="col-sm-8 mb-1">${escSd(data.Notes) || "—"}</dd>
            </dl>
            ${threadHtml}
          </div>
        `;

        sdOpenDrawer({
          title: `${escSd(data.IncidentID)}`,
          badge: data.Status,
          fullLink: `/incidents/${data.IncidentID}`,
          content: html
        });
      })
      .catch((err) => {
        sdOpenDrawer({
          title: escSd(incidentId),
          content: `<div class="alert alert-warning mb-0">Не може да се вчитаат деталите за инцидентот: ${escSd(err.message)}. <br><a href="/incidents/${escSd(incidentId)}">Отвори ја целата страна</a></div>`,
          fullLink: `/incidents/${incidentId}`
        });
      });
  });

  /* ==========================================================================
     9. Interactive CSAT Rating Controller
     ========================================================================== */
  document.addEventListener("click", (e) => {
    const starBtn = e.target.closest(".csat-star-btn");
    if (!starBtn) return;
    const group = starBtn.closest(".csat-rating-group");
    const form = starBtn.closest(".csat-form");
    if (!group || !form) return;

    e.preventDefault();
    const score = parseInt(starBtn.dataset.score, 10);
    const incidentId = form.dataset.incidentId;
    const csrfToken = form.querySelector('input[name="_csrf_token"]')?.value || "";

    // Highlight stars
    group.querySelectorAll(".csat-star-btn").forEach((btn) => {
      const s = parseInt(btn.dataset.score, 10);
      if (s <= score) {
        btn.classList.add("is-active");
      } else {
        btn.classList.remove("is-active");
      }
    });

    const hiddenInput = form.querySelector('input[name="score"]');
    if (hiddenInput) hiddenInput.value = score;

    // Send async rating
    fetch(`/incidents/${incidentId}/rate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest"
      },
      body: new URLSearchParams({
        _csrf_token: csrfToken,
        score: score
      })
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.ok) {
          const feedback = form.querySelector(".csat-feedback");
          if (feedback) {
            feedback.classList.remove("d-none");
            setTimeout(() => feedback.classList.add("d-none"), 3500);
          }
          if (score >= 5) {
            const rect = starBtn.getBoundingClientRect();
            sdConfetti({
              x: rect.left + rect.width / 2,
              y: rect.top,
              count: 45
            });
          }
        }
      })
      .catch(() => {});
  });

})();
