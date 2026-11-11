/**
 * CMDB Topology Graph & Impact Analysis Engine (Vanilla Canvas)
 * Zero external libraries or CDNs. Fully CSP-compliant.
 */

(function () {
  "use strict";

  const canvas = document.getElementById("cmdbCanvas");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  let width = canvas.clientWidth;
  let height = canvas.clientHeight;

  // Viewport transform
  let scale = 1.0;
  let panX = width / 2;
  let panY = height / 2;
  let isDragging = false;
  let dragNode = null;
  let dragStartX = 0;
  let dragStartY = 0;
  let hoveredNode = null;
  let selectedNode = null;

  // Data
  let nodes = [];
  let edges = [];
  let nodeMap = new Map();
  let impactedIds = new Set();
  let currentRootId = canvas.dataset.root || "";

  // Styling palette
  const typeColors = {
    server: { fill: "#4f46e5", stroke: "#6366f1", text: "#ffffff", label: "Сервер" },
    network: { fill: "#0d9488", stroke: "#14b8a6", text: "#ffffff", label: "Мрежа" },
    endpoint: { fill: "#2563eb", stroke: "#3b82f6", text: "#ffffff", label: "Клиент" },
    employee: { fill: "#16a34a", stroke: "#22c55e", text: "#ffffff", label: "Корисник" },
    service: { fill: "#ea580c", stroke: "#f97316", text: "#ffffff", label: "Сервис" },
    rack: { fill: "#475569", stroke: "#64748b", text: "#ffffff", label: "Рек" },
    power: { fill: "#ca8a04", stroke: "#eab308", text: "#ffffff", label: "Напојување" },
    other: { fill: "#64748b", stroke: "#94a3b8", text: "#ffffff", label: "Средство" },
  };

  function isDarkTheme() {
    return document.documentElement.getAttribute("data-bs-theme") === "dark";
  }

  function resizeCanvas() {
    const rect = canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    width = rect.width;
    height = Math.max(rect.height, 560);
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";
    ctx.scale(dpr, dpr);
    render();
  }

  window.addEventListener("resize", resizeCanvas);
  document.addEventListener("sd-theme", () => render());

  // Layout simulation
  function initLayout() {
    const n = nodes.length;
    if (n === 0) return;

    // Distribute initially in a circle or concentric circles
    const radius = Math.min(width, height) * 0.35;
    nodes.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / n;
      node.x = Math.cos(angle) * (radius + (i % 2) * 50);
      node.y = Math.sin(angle) * (radius + (i % 2) * 50);
      node.vx = 0;
      node.vy = 0;
      node.radius = 24;
      if (node.is_root) {
        node.x = 0;
        node.y = 0;
      }
    });

    // Run force iterations
    simulate(80);
  }

  function simulate(steps) {
    const kRepulse = 3800;
    const kAttract = 0.05;
    const centerPull = 0.015;

    for (let step = 0; step < steps; step++) {
      // Repulsion between all nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const u = nodes[i];
          const v = nodes[j];
          let dx = v.x - u.x;
          let dy = v.y - u.y;
          let dist = Math.sqrt(dx * dx + dy * dy) || 1;
          if (dist < 400) {
            const force = kRepulse / (dist * dist);
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            u.vx -= fx;
            u.vy -= fy;
            v.vx += fx;
            v.vy += fy;
          }
        }
      }

      // Attraction along edges
      edges.forEach((edge) => {
        const u = nodeMap.get(edge.source);
        const v = nodeMap.get(edge.target);
        if (!u || !v) return;
        const dx = v.x - u.x;
        const dy = v.y - u.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const desired = 120;
        const force = (dist - desired) * kAttract;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        u.vx += fx;
        u.vy += fy;
        v.vx += fx;
        v.vy += fy;
      });

      // Update positions
      nodes.forEach((u) => {
        if (u === dragNode) return;
        u.vx -= u.x * centerPull;
        u.vy -= u.y * centerPull;
        u.vx *= 0.82;
        u.vy *= 0.82;
        u.x += u.vx;
        u.y += u.vy;
      });
    }
  }

  // Coordinate transformations
  function toScreenX(x) {
    return panX + x * scale;
  }
  function toScreenY(y) {
    return panY + y * scale;
  }
  function toWorldX(sx) {
    return (sx - panX) / scale;
  }
  function toWorldY(sy) {
    return (sy - panY) / scale;
  }

  // Main Render Loop
  function render() {
    ctx.save();
    ctx.clearRect(0, 0, width, height);

    const dark = isDarkTheme();

    // Background Grid Dots
    const dotColor = dark ? "#1e293b" : "#f1f5f9";
    const bgFill = dark ? "#090d16" : "#f8fafc";
    ctx.fillStyle = bgFill;
    ctx.fillRect(0, 0, width, height);

    const gridSize = 32 * scale;
    if (gridSize > 12) {
      ctx.fillStyle = dotColor;
      const startX = panX % gridSize;
      const startY = panY % gridSize;
      for (let x = startX; x < width; x += gridSize) {
        for (let y = startY; y < height; y += gridSize) {
          ctx.beginPath();
          ctx.arc(x, y, 1.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }

    // 1. Draw Edges
    edges.forEach((edge) => {
      const u = nodeMap.get(edge.source);
      const v = nodeMap.get(edge.target);
      if (!u || !v) return;

      const sx = toScreenX(u.x);
      const sy = toScreenY(u.y);
      const tx = toScreenX(v.x);
      const ty = toScreenY(v.y);

      const isImpactedEdge = impactedIds.has(u.id) && impactedIds.has(v.id);

      ctx.beginPath();
      ctx.moveTo(sx, sy);
      ctx.lineTo(tx, ty);

      if (isImpactedEdge) {
        ctx.strokeStyle = "#ef4444";
        ctx.lineWidth = Math.max(2.5, 2.5 * scale);
        ctx.setLineDash([6, 4]);
      } else {
        ctx.strokeStyle = dark ? "#334155" : "#cbd5e1";
        ctx.lineWidth = Math.max(1.5, 1.5 * scale);
        ctx.setLineDash([]);
      }
      ctx.stroke();
      ctx.setLineDash([]);

      // Draw Arrow Head
      const angle = Math.atan2(ty - sy, tx - sx);
      const nodeR = (v.radius + 6) * scale;
      const arrowX = tx - Math.cos(angle) * nodeR;
      const arrowY = ty - Math.sin(angle) * nodeR;

      ctx.beginPath();
      ctx.moveTo(arrowX, arrowY);
      ctx.lineTo(
        arrowX - 10 * Math.cos(angle - Math.PI / 7) * scale,
        arrowY - 10 * Math.sin(angle - Math.PI / 7) * scale
      );
      ctx.lineTo(
        arrowX - 10 * Math.cos(angle + Math.PI / 7) * scale,
        arrowY - 10 * Math.sin(angle + Math.PI / 7) * scale
      );
      ctx.closePath();
      ctx.fillStyle = isImpactedEdge ? "#ef4444" : (dark ? "#64748b" : "#94a3b8");
      ctx.fill();

      // Draw Edge Label Badge if zoomed in enough
      if (scale > 0.65 && edge.label) {
        const midX = (sx + tx) / 2;
        const midY = (sy + ty) / 2;
        ctx.font = `${Math.max(9, Math.round(10 * scale))}px system-ui, sans-serif`;
        const textWidth = ctx.measureText(edge.label).width;
        const pad = 4;

        ctx.fillStyle = dark ? "rgba(15, 23, 42, 0.85)" : "rgba(255, 255, 255, 0.9)";
        ctx.strokeStyle = isImpactedEdge ? "#ef4444" : (dark ? "#475569" : "#e2e8f0");
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(
          midX - textWidth / 2 - pad,
          midY - 7 * scale - pad,
          textWidth + pad * 2,
          14 * scale + pad,
          4
        );
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = isImpactedEdge ? "#ef4444" : (dark ? "#94a3b8" : "#64748b");
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(edge.label, midX, midY);
      }
    });

    // 2. Draw Nodes
    nodes.forEach((node) => {
      const sx = toScreenX(node.x);
      const sy = toScreenY(node.y);
      const r = node.radius * scale;
      const isSelected = selectedNode && selectedNode.id === node.id;
      const isImpacted = impactedIds.has(node.id);
      const isHovered = hoveredNode && hoveredNode.id === node.id;
      const cfg = typeColors[node.category] || typeColors.other;

      // Glow or halo for Impacted / Selected / Root
      if (isImpacted) {
        ctx.beginPath();
        ctx.arc(sx, sy, r + 10 * scale, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(239, 68, 68, 0.25)";
        ctx.fill();
      } else if (node.is_root) {
        ctx.beginPath();
        ctx.arc(sx, sy, r + 8 * scale, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(14, 165, 233, 0.25)";
        ctx.fill();
      }

      // Node Body Circle
      ctx.beginPath();
      ctx.arc(sx, sy, r, 0, Math.PI * 2);
      ctx.fillStyle = isImpacted ? "#ef4444" : cfg.fill;
      ctx.fill();

      // Border
      ctx.lineWidth = isSelected ? 3.5 * scale : (isHovered ? 2.5 * scale : 2 * scale);
      ctx.strokeStyle = isImpacted
        ? "#b91c1c"
        : (isSelected ? "#38bdf8" : (isHovered ? "#ffffff" : cfg.stroke));
      ctx.stroke();

      // Node Icon / Type Badge inside
      ctx.fillStyle = "#ffffff";
      ctx.font = `bold ${Math.max(10, Math.round(11 * scale))}px system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      const shortBadge = node.type === "employee" ? "USER" : (node.category === "server" ? "SRV" : (node.category === "network" ? "NET" : "DEV"));
      ctx.fillText(shortBadge, sx, sy);

      // Node Label Text below
      ctx.font = `${node.is_root || isSelected ? "bold " : ""}${Math.max(10, Math.round(11 * scale))}px system-ui, sans-serif`;
      ctx.fillStyle = dark ? "#f8fafc" : "#0f172a";
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      const displayId = node.id;
      ctx.fillText(displayId, sx, sy + r + 5 * scale);

      // Optional Subtitle
      if (scale > 0.75 && node.label && node.label !== displayId) {
        ctx.font = `normal ${Math.max(9, Math.round(9.5 * scale))}px system-ui, sans-serif`;
        ctx.fillStyle = dark ? "#94a3b8" : "#64748b";
        let sub = node.label.replace(displayId, "").replace(/^[\s\-:]+/, "");
        if (sub.length > 22) sub = sub.substring(0, 20) + "...";
        ctx.fillText(sub, sx, sy + r + 18 * scale);
      }
    });

    ctx.restore();
  }

  // Hit testing
  function getNodeAt(screenX, screenY) {
    const wx = toWorldX(screenX);
    const wy = toWorldY(screenY);
    for (let i = nodes.length - 1; i >= 0; i--) {
      const node = nodes[i];
      const dx = wx - node.x;
      const dy = wy - node.y;
      if (dx * dx + dy * dy <= node.radius * node.radius) {
        return node;
      }
    }
    return null;
  }

  // Mouse Interactions
  canvas.addEventListener("mousedown", (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const clickedNode = getNodeAt(mx, my);
    if (clickedNode) {
      dragNode = clickedNode;
      isDragging = false;
      selectNode(clickedNode);
    } else {
      isDragging = true;
      dragStartX = mx - panX;
      dragStartY = my - panY;
    }
  });

  window.addEventListener("mousemove", (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    if (dragNode) {
      dragNode.x = toWorldX(mx);
      dragNode.y = toWorldY(my);
      dragNode.vx = 0;
      dragNode.vy = 0;
      render();
      return;
    }

    if (isDragging) {
      panX = mx - dragStartX;
      panY = my - dragStartY;
      render();
      return;
    }

    // Hover state
    if (mx >= 0 && mx <= width && my >= 0 && my <= height) {
      const prev = hoveredNode;
      hoveredNode = getNodeAt(mx, my);
      if (prev !== hoveredNode) {
        canvas.style.cursor = hoveredNode ? "pointer" : "grab";
        render();
      }
    }
  });

  window.addEventListener("mouseup", () => {
    if (dragNode) {
      dragNode = null;
      render();
    }
    isDragging = false;
  });

  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
    const newScale = Math.min(Math.max(scale * zoomFactor, 0.25), 3.0);

    panX = mx - (mx - panX) * (newScale / scale);
    panY = my - (my - panY) * (newScale / scale);
    scale = newScale;

    render();
  }, { passive: false });

  // Node Selection & Sidebar Updates
  function selectNode(node) {
    selectedNode = node;
    render();

    const infoCard = document.getElementById("selectedCiCard");
    const emptyCard = document.getElementById("emptyCiCard");
    const titleEl = document.getElementById("ciTitle");
    const idEl = document.getElementById("ciId");
    const typeEl = document.getElementById("ciType");
    const statusEl = document.getElementById("ciStatus");
    const locEl = document.getElementById("ciLocation");
    const linksEl = document.getElementById("ciDetailLink");
    const impactBtn = document.getElementById("btnCalcImpact");

    if (!infoCard || !emptyCard) return;

    emptyCard.classList.add("d-none");
    infoCard.classList.remove("d-none");

    if (titleEl) titleEl.textContent = node.label;
    if (idEl) idEl.textContent = node.id;
    if (typeEl) typeEl.textContent = node.raw_type || node.type;
    if (statusEl) statusEl.textContent = node.status || "Active";
    if (locEl) locEl.textContent = node.location || node.dept || "—";

    if (linksEl) {
      if (node.type === "device") {
        linksEl.href = `/device/${node.id}`;
        linksEl.classList.remove("d-none");
      } else if (node.type === "employee") {
        linksEl.href = `/employee/${node.id}`;
        linksEl.classList.remove("d-none");
      } else {
        linksEl.classList.add("d-none");
      }
    }

    if (impactBtn) {
      impactBtn.dataset.assetId = node.id;
      impactBtn.disabled = false;
    }
  }

  // Blast Radius Impact Engine
  async function runImpactAnalysis(assetId) {
    if (!assetId) return;

    const btn = document.getElementById("btnCalcImpact");
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Пресметувам...`;
    }

    try {
      const res = await fetch(`/api/v1/cmdb/impact/${encodeURIComponent(assetId)}`);
      if (!res.ok) throw new Error("Неуспешно читање на податоци за влијание");
      const data = await res.json();

      impactedIds = new Set(data.affected_ids || []);
      render();

      displayBlastRadiusResults(data);
    } catch (err) {
      console.error("Impact calculation failed:", err);
      alert("Грешка при пресметка на влијанието: " + err.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<svg class="ic me-1" aria-hidden="true"><use href="#i-bolt"/></svg> Пресметај Blast Radius`;
      }
    }
  }

  function displayBlastRadiusResults(data) {
    const resPanel = document.getElementById("blastRadiusResults");
    if (!resPanel) return;

    resPanel.classList.remove("d-none");

    const badgeEl = document.getElementById("blastScoreBadge");
    const totalEl = document.getElementById("blastTotalCount");
    const devListEl = document.getElementById("impactedDevicesList");
    const empListEl = document.getElementById("impactedEmployeesList");
    const srvListEl = document.getElementById("impactedServicesList");
    const changeBtn = document.getElementById("btnCreateChange");

    const scoreClass = {
      critical: "bg-danger",
      high: "bg-warning text-dark",
      medium: "bg-primary",
      low: "bg-secondary",
    }[data.blast_radius_score] || "bg-secondary";

    if (badgeEl) {
      badgeEl.className = `badge ${scoreClass} fs-6 px-3 py-2`;
      badgeEl.textContent = `Ризик: ${data.blast_radius_label || data.blast_radius_score}`;
    }

    if (totalEl) {
      totalEl.textContent = `${data.total_impacted} засегнати CI единици / корисници`;
    }

    // Devices List
    if (devListEl) {
      if (data.impacted_devices && data.impacted_devices.length > 0) {
        devListEl.innerHTML = data.impacted_devices.map(d =>
          `<li class="list-group-item d-flex justify-content-between align-items-center py-1">
             <span><b>${d.id}</b> — ${d.name} <small class="text-muted">(${d.type})</small></span>
             <a href="/device/${d.id}" class="btn btn-sm btn-outline-secondary py-0">Детали</a>
           </li>`
        ).join("");
      } else {
        devListEl.innerHTML = `<li class="list-group-item text-muted py-1">Нема директно засегнати уреди.</li>`;
      }
    }

    // Employees List
    if (empListEl) {
      if (data.impacted_employees && data.impacted_employees.length > 0) {
        empListEl.innerHTML = data.impacted_employees.map(e =>
          `<li class="list-group-item py-1">
             <b>${e.name}</b> <small class="text-muted">(${e.dept || e.id})</small>
           </li>`
        ).join("");
      } else {
        empListEl.innerHTML = `<li class="list-group-item text-muted py-1">Нема директно засегнати корисници.</li>`;
      }
    }

    // Services List
    if (srvListEl) {
      if (data.impacted_services && data.impacted_services.length > 0) {
        srvListEl.innerHTML = data.impacted_services.map(s =>
          `<li class="list-group-item py-1">
             <span class="badge bg-warning text-dark me-1">Сервис</span> <b>${s.name}</b>
           </li>`
        ).join("");
      } else {
        srvListEl.innerHTML = `<li class="list-group-item text-muted py-1">Нема поврзани сервиси.</li>`;
      }
    }

    // Prefilled Change Request Button
    if (changeBtn) {
      const impactSummary = `${data.target.id} (${data.target.name}) - ${data.total_impacted} засегнати единици (${data.impacted_devices.length} уреди, ${data.impacted_employees.length} корисници)`;
      const changeTitle = `Интервенција / Одржување на ${data.target.id} (${data.target.name})`;
      const riskLevel = data.blast_radius_score === "critical" ? "critical" : (data.blast_radius_score === "high" ? "high" : "medium");

      changeBtn.href = `/changes?title=${encodeURIComponent(changeTitle)}&impact_scope=${encodeURIComponent(impactSummary)}&risk_level=${encodeURIComponent(riskLevel)}`;
      changeBtn.classList.remove("d-none");
    }
  }

  // Load Graph Data
  async function loadGraphData(rootId, category) {
    let url = "/api/v1/cmdb/graph";
    const params = new URLSearchParams();
    if (rootId) params.append("root", rootId);
    if (category) params.append("type", category);
    if ([...params].length > 0) url += "?" + params.toString();

    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error("Неуспешно читање на CMDB топологија");
      const data = await res.json();

      nodes = data.nodes || [];
      edges = data.edges || [];
      nodeMap = new Map();
      nodes.forEach(n => nodeMap.set(n.id, n));

      initLayout();
      resizeCanvas();

      // If root specified, select it automatically and calculate impact!
      if (rootId && nodeMap.has(rootId)) {
        selectNode(nodeMap.get(rootId));
        runImpactAnalysis(rootId);
      }
    } catch (err) {
      console.error("Failed to load CMDB graph:", err);
    }
  }

  // Controls & UI Wiring
  document.getElementById("btnZoomIn")?.addEventListener("click", () => {
    scale = Math.min(scale * 1.25, 3.0);
    render();
  });

  document.getElementById("btnZoomOut")?.addEventListener("click", () => {
    scale = Math.max(scale * 0.8, 0.25);
    render();
  });

  document.getElementById("btnResetView")?.addEventListener("click", () => {
    scale = 1.0;
    panX = width / 2;
    panY = height / 2;
    render();
  });

  document.getElementById("btnCalcImpact")?.addEventListener("click", function () {
    const aid = this.dataset.assetId || (selectedNode ? selectedNode.id : null);
    if (aid) runImpactAnalysis(aid);
  });

  document.getElementById("categoryFilter")?.addEventListener("change", function () {
    loadGraphData(currentRootId, this.value);
  });

  document.getElementById("searchCiInput")?.addEventListener("change", function () {
    const val = this.value.trim();
    if (nodeMap.has(val)) {
      currentRootId = val;
      selectNode(nodeMap.get(val));
      runImpactAnalysis(val);
    }
  });

  // Initial load
  loadGraphData(currentRootId, "");
})();
