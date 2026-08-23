// webapp/static/dashboard.js — Tier-1 UI Controls, Chart.js, Polling, Toasts & Micro-Interactions

const LIGHT_PALETTE = {
  primary: "#0d9488",
  success: "#10b981",
  cyan: "#06b6d4",
  warning: "#f59e0b",
  danger: "#f43f5e",
  indigo: "#6366f1",
  text: "#334155",
  grid: "rgba(0, 0, 0, 0.05)",
  doughnutBorder: "#ffffff",
};

const DARK_PALETTE = {
  primary: "#2dd4bf",
  success: "#10b981",
  cyan: "#38bdf8",
  warning: "#f59e0b",
  danger: "#f43f5e",
  indigo: "#818cf8",
  text: "#94a3b8",
  grid: "rgba(255, 255, 255, 0.06)",
  doughnutBorder: "#12151f",
};

function currentPalette() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? DARK_PALETTE : LIGHT_PALETTE;
}

Chart.defaults.font.family = '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
Chart.defaults.font.size = 12;

let homeCharts = [];

function destroyHomeCharts() {
  homeCharts.forEach((c) => c.destroy());
  homeCharts = [];
}

function initHomeCharts(stats) {
  destroyHomeCharts();
  const PALETTE = currentPalette();
  Chart.defaults.color = PALETTE.text;
  Chart.defaults.borderColor = PALETTE.grid;

  const scoreCtx = document.getElementById("scoreChart");
  if (scoreCtx && stats && stats.score_distribution) {
    homeCharts.push(new Chart(scoreCtx, {
      type: "bar",
      data: {
        labels: Object.keys(stats.score_distribution),
        datasets: [{
          label: "Jobs",
          data: Object.values(stats.score_distribution),
          backgroundColor: PALETTE.primary,
          borderRadius: 6,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false } },
          y: { grid: { color: PALETTE.grid } }
        }
      },
    }));
  }

  const timeCtx = document.getElementById("timeChart");
  if (timeCtx && stats && stats.runs_over_time) {
    homeCharts.push(new Chart(timeCtx, {
      type: "line",
      data: {
        labels: stats.runs_over_time.map((r) => r.run_id),
        datasets: [
          {
            label: "Scored",
            data: stats.runs_over_time.map((r) => r.total_scored),
            borderColor: PALETTE.text,
            backgroundColor: PALETTE.text,
            tension: 0.35,
            pointRadius: 4,
          },
          {
            label: "Qualifying",
            data: stats.runs_over_time.map((r) => r.total_qualifying),
            borderColor: PALETTE.success,
            backgroundColor: PALETTE.success,
            tension: 0.35,
            pointRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        scales: {
          x: { grid: { display: false } },
          y: { grid: { color: PALETTE.grid } }
        }
      }
    }));
  }
}

// -------------------- Global Toast System --------------------
function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  
  let icon = "⚡";
  if (type === "success") icon = "✓";
  if (type === "error") icon = "✕";

  toast.innerHTML = `
    <span style="color: var(--accent-primary); font-weight: 700;">${icon}</span>
    <span>${message}</span>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(8px) scale(0.95)";
    setTimeout(() => toast.remove(), 250);
  }, 2500);
}

// -------------------- Theme Toggle & Mobile Triggers --------------------
function initThemeToggle() {
  const btns = [document.getElementById("themeToggle"), document.getElementById("themeToggleMobile")].filter(Boolean);
  if (btns.length === 0) return;

  function syncThemeUI() {
    const isDark = document.documentElement.getAttribute("data-theme") !== "light";
    btns.forEach((btn) => {
      btn.innerHTML = isDark ? `☀️` : `🌙`;
      btn.setAttribute("title", isDark ? "Switch to Light Mode" : "Switch to Dark Mode");
      btn.setAttribute("aria-label", isDark ? "Switch to Light Mode" : "Switch to Dark Mode");
    });
  }

  syncThemeUI();
  btns.forEach((btn) => {
    btn.addEventListener("click", function () {
      const isCurrentlyLight = document.documentElement.getAttribute("data-theme") === "light";
      const nextTheme = isCurrentlyLight ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", nextTheme);
      document.body.setAttribute("data-theme", nextTheme);
      localStorage.setItem("theme", nextTheme);
      syncThemeUI();
      if (window.DASHBOARD_STATS && window.initHomeCharts) {
        window.initHomeCharts(window.DASHBOARD_STATS);
      }
      showToast(`Switched to ${nextTheme === "light" ? "Light" : "Dark"} Mode`, "info");
    });
  });

  const mobileCmdkBtn = document.getElementById("mobileCmdkBtn");
  if (mobileCmdkBtn) {
    mobileCmdkBtn.addEventListener("click", function () {
      const backdrop = document.getElementById("cmdPaletteBackdrop");
      const input = document.getElementById("cmdPaletteInput");
      if (backdrop && input) {
        backdrop.classList.remove("hidden");
        setTimeout(() => input.focus(), 50);
      }
    });
  }
}

function initCopyButton(buttonId, textId) {
  const btn = document.getElementById(buttonId);
  const block = document.getElementById(textId);
  if (!btn || !block) return;
  btn.addEventListener("click", function () {
    navigator.clipboard.writeText(block.textContent).then(function () {
      showToast("Copied to clipboard!", "success");
      const original = btn.textContent;
      btn.textContent = "Copied! ✓";
      setTimeout(function () { btn.textContent = original; }, 1500);
    });
  });
}

function initTriggerPage() {
  const form = document.getElementById("triggerForm");
  const dryRunCheckbox = document.getElementById("dryRunCheckbox");
  const resumePathInput = document.getElementById("resumePathInput");
  const resumeSecondaryPathInput = document.getElementById("resumeSecondaryPathInput");
  const enableCrawl4aiCheckbox = document.getElementById("enableCrawl4aiCheckbox");
  const triggerBtn = document.getElementById("triggerBtn");
  const message = document.getElementById("triggerMessage");
  const statusPanel = document.getElementById("statusPanel");
  const statusStage = document.getElementById("statusStage");
  const progressFill = document.getElementById("progressFill");
  const statusDetail = document.getElementById("statusDetail");

  let pollHandle = null;

  function renderStatus(status) {
    statusPanel.hidden = false;
    statusStage.textContent = status.stage || "idle";

    const pct = status.total > 0 ? Math.round((status.current / status.total) * 100) : 0;
    progressFill.style.width = pct + "%";

    const parts = [];
    if (status.title) parts.push(status.title + (status.company ? " @ " + status.company : ""));
    if (status.total) parts.push(status.current + " / " + status.total);
    if (status.error) parts.push("Error: " + status.error);
    if (status.finished && status.result_run_id) {
      parts.push("Done — view results: " + status.result_run_id);
    }
    statusDetail.innerHTML = "";
    if (status.finished && status.result_run_id) {
      const link = document.createElement("a");
      link.href = "/runs/" + status.result_run_id;
      link.textContent = "View run " + status.result_run_id;
      statusDetail.appendChild(link);
    } else {
      statusDetail.textContent = parts.join(" · ");
    }

    if (!status.active) {
      triggerBtn.disabled = false;
      if (pollHandle) {
        clearInterval(pollHandle);
        pollHandle = null;
      }
    }
  }

  function poll() {
    fetch("/api/runs/status")
      .then((r) => r.json())
      .then(renderStatus)
      .catch(() => {});
  }

  // Primary & Secondary File Upload Handlers
  const uploadPrimaryBtn = document.getElementById("uploadPrimaryBtn");
  const primaryFileInput = document.getElementById("primaryFileInput");
  const primaryUploadBadge = document.getElementById("primaryUploadBadge");
  const primaryUploadedName = document.getElementById("primaryUploadedName");

  const uploadSecondaryBtn = document.getElementById("uploadSecondaryBtn");
  const secondaryFileInput = document.getElementById("secondaryFileInput");
  const secondaryUploadBadge = document.getElementById("secondaryUploadBadge");
  const secondaryUploadedName = document.getElementById("secondaryUploadedName");

  function uploadResumeFile(file, isPrimary) {
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);

    const btn = isPrimary ? uploadPrimaryBtn : uploadSecondaryBtn;
    const originalText = btn.innerHTML;
    btn.innerHTML = `<span>⏳</span> Uploading...`;
    btn.style.pointerEvents = "none";

    fetch("/api/resume/upload-batch-file", {
      method: "POST",
      body: formData,
    })
      .then((r) => r.json())
      .then((res) => {
        btn.innerHTML = originalText;
        btn.style.pointerEvents = "auto";

        if (!res.ok) {
          showToast(res.error || "Upload failed", "error");
          return;
        }

        const sizeKb = Math.round(res.size_bytes / 1024);
        if (isPrimary) {
          if (resumePathInput) resumePathInput.value = res.saved_path;
          if (primaryUploadBadge && primaryUploadedName) {
            primaryUploadedName.textContent = `${res.filename} (${sizeKb} KB)`;
            primaryUploadBadge.style.display = "block";
          }
          showToast(`Primary resume uploaded: ${res.filename}`, "success");
        } else {
          if (resumeSecondaryPathInput) resumeSecondaryPathInput.value = res.saved_path;
          if (secondaryUploadBadge && secondaryUploadedName) {
            secondaryUploadedName.textContent = `${res.filename} (${sizeKb} KB)`;
            secondaryUploadBadge.style.display = "block";
          }
          showToast(`Secondary resume uploaded: ${res.filename}`, "success");
        }
      })
      .catch((err) => {
        btn.innerHTML = originalText;
        btn.style.pointerEvents = "auto";
        showToast("Network error uploading resume.", "error");
      });
  }

  if (uploadPrimaryBtn && primaryFileInput) {
    uploadPrimaryBtn.addEventListener("click", () => primaryFileInput.click());
    primaryFileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        uploadResumeFile(e.target.files[0], true);
      }
    });
  }

  if (uploadSecondaryBtn && secondaryFileInput) {
    uploadSecondaryBtn.addEventListener("click", () => secondaryFileInput.click());
    secondaryFileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        uploadResumeFile(e.target.files[0], false);
      }
    });
  }

  if (form) {
    form.addEventListener("submit", function (evt) {
      evt.preventDefault();
      triggerBtn.disabled = true;
      message.textContent = "";
      message.className = "trigger-message";

      fetch("/api/runs/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dry_run: dryRunCheckbox.checked,
          resume_path: resumePathInput.value,
          resume_secondary_path: resumeSecondaryPathInput ? (resumeSecondaryPathInput.value || null) : null,
          enable_crawl4ai: enableCrawl4aiCheckbox.checked,
        }),
      })
        .then((r) => r.json().then((data) => ({ status: r.status, data })))
        .then(({ status, data }) => {
          if (status === 409) {
            message.textContent = data.message || "A run is already in progress";
            message.classList.add("error");
            triggerBtn.disabled = false;
            return;
          }
          message.textContent = "Run started.";
          message.classList.add("success");
          showToast("Scout pipeline started in background", "info");
          if (!pollHandle) {
            pollHandle = setInterval(poll, 1500);
          }
          poll();
        })
        .catch(() => {
          message.textContent = "Failed to start run — check the server log.";
          message.classList.add("error");
          triggerBtn.disabled = false;
        });
    });
  }

  poll();
  fetch("/api/runs/status")
    .then((r) => r.json())
    .then((status) => {
      if (status.active) {
        triggerBtn.disabled = true;
        if (!pollHandle) pollHandle = setInterval(poll, 1500);
      }
    })
    .catch(() => {});
}

function initRunsPage() {
  const table = document.querySelector("[data-runs-table]");
  if (!table) return;

  let pollHandle = null;
  let reloading = false;

  function reloadOnce() {
    if (reloading) return;
    reloading = true;
    if (pollHandle) {
      clearInterval(pollHandle);
      pollHandle = null;
    }
    window.location.reload();
  }

  function apply(status) {
    const row = document.getElementById("inProgressRow");
    if (status.active) {
      if (!row) {
        reloadOnce();
        return;
      }
      const statusSpan = document.getElementById("inProgressStatus");
      if (statusSpan) {
        const parts = [];
        if (status.title) parts.push(status.title + (status.company ? " @ " + status.company : ""));
        parts.push(status.stage || "running");
        if (status.total) parts.push(status.current + "/" + status.total);
        statusSpan.textContent = parts.join(" · ");
      }
    } else if (row) {
      if (status.error && !status.result_run_id) {
        const statusSpan = document.getElementById("inProgressStatus");
        if (statusSpan) statusSpan.textContent = "Error: " + status.error;
        if (pollHandle) { clearInterval(pollHandle); pollHandle = null; }
      } else {
        reloadOnce();
      }
    }
  }

  function poll() {
    fetch("/api/runs/status")
      .then((r) => r.json())
      .then(apply)
      .catch(() => {});
  }

  poll();
  pollHandle = setInterval(poll, 1500);
}

function initKanbanPage() {
  const board = document.getElementById("kanbanBoard");
  if (!board) return;

  // Handle status URL highlighting (e.g. /kanban?status=applied)
  const urlParams = new URLSearchParams(window.location.search);
  const targetStatus = urlParams.get("status");
  if (targetStatus) {
    const targetBody = board.querySelector(`[data-status="${targetStatus}"]`);
    if (targetBody) {
      const col = targetBody.closest(".kanban-column");
      if (col) {
        col.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
        col.style.transition = "all 0.4s ease";
        col.style.boxShadow = "0 0 0 2px var(--accent-cyan-fg), 0 8px 24px -4px rgba(6, 182, 212, 0.4)";
        setTimeout(() => {
          col.style.boxShadow = "";
        }, 3000);
      }
    }
  }

  const message = document.getElementById("kanbanMessage");
  let dragCard = null;
  let dragOrigin = null;

  board.addEventListener("dragstart", function (evt) {
    const card = evt.target.closest(".kanban-card");
    if (!card) return;
    dragCard = card;
    dragOrigin = card.parentElement;
    card.classList.add("kanban-dragging");
    evt.dataTransfer.effectAllowed = "move";
  });

  board.addEventListener("dragend", function () {
    if (dragCard) dragCard.classList.remove("kanban-dragging");
    dragCard = null;
    dragOrigin = null;
  });

  board.querySelectorAll(".kanban-column-body").forEach(function (body) {
    body.addEventListener("dragover", function (evt) {
      evt.preventDefault();
      body.classList.add("kanban-dragover");
    });
    body.addEventListener("dragleave", function () {
      body.classList.remove("kanban-dragover");
    });
    body.addEventListener("drop", function (evt) {
      evt.preventDefault();
      body.classList.remove("kanban-dragover");
      if (!dragCard) return;

      const card = dragCard;
      const previousParent = dragOrigin;
      const previousNextSibling = card.nextSibling;
      const newStatus = body.dataset.status;
      const key = card.dataset.key;

      body.appendChild(card);
      if (message) message.textContent = "";

      fetch("/api/tracker/status_by_key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: key, status: newStatus }),
      })
        .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
        .then(({ ok, data }) => {
          if (!ok || !data.ok) {
            if (previousNextSibling) {
              previousParent.insertBefore(card, previousNextSibling);
            } else {
              previousParent.appendChild(card);
            }
            if (message) {
              message.textContent = (data && data.reason) || "Move rejected.";
              message.className = "trigger-message error";
            }
          } else {
            showToast(`Moved to ${newStatus.replace('_', ' ').toUpperCase()}`, "success");
          }
        })
        .catch(function () {
          if (previousNextSibling) {
            previousParent.insertBefore(card, previousNextSibling);
          } else {
            previousParent.appendChild(card);
          }
          if (message) {
            message.textContent = "Failed to save — check server log.";
            message.className = "trigger-message error";
          }
        });
    });
  });
}

// -------------------- Spotlight Card Cursor Tracking (Aceternity / Linear Style) --------------------

function initSpotlightEffect() {
  const cards = document.querySelectorAll(".spotlight-card");
  if (!cards.length) return;

  cards.forEach((card) => {
    card.addEventListener("mousemove", (e) => {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      card.style.setProperty("--mouse-x", `${x}px`);
      card.style.setProperty("--mouse-y", `${y}px`);
    });
  });
}

// -------------------- Smooth Number Rolling / Counter Animation --------------------

function initAnimatedCounters() {
  const counterEls = document.querySelectorAll("[data-counter]");
  if (!counterEls.length) return;

  counterEls.forEach((el) => {
    const rawVal = el.getAttribute("data-counter");
    const target = parseInt(rawVal, 10);
    if (isNaN(target) || target === 0) return;

    const duration = 1200; // ms
    const startTime = performance.now();

    function updateCounter(now) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out expo
      const easeProgress = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
      const current = Math.floor(easeProgress * target);

      el.textContent = current.toLocaleString();

      if (progress < 1) {
        requestAnimationFrame(updateCounter);
      } else {
        el.textContent = target.toLocaleString();
      }
    }

    requestAnimationFrame(updateCounter);
  });
}

// -------------------- Particle Burst / Sparkle Micro-Interaction (MoJS / Framer Motion Inspired) --------------------

function triggerSparkBurst(event, count = 10, colors = ['#2dd4bf', '#38bdf8', '#818cf8', '#34d399', '#f59e0b']) {
  const target = event.currentTarget || event.target;
  if (!target) return;
  const rect = target.getBoundingClientRect();
  const originX = event.clientX ? event.clientX - rect.left : rect.width / 2;
  const originY = event.clientY ? event.clientY - rect.top : rect.height / 2;

  for (let i = 0; i < count; i++) {
    const spark = document.createElement('span');
    spark.className = 'spark-particle';

    const angle = (i / count) * 2 * Math.PI + (Math.random() - 0.5) * 0.6;
    const distance = 24 + Math.random() * 32;
    const destX = Math.cos(angle) * distance;
    const destY = Math.sin(angle) * distance;
    const size = 3.5 + Math.random() * 3.5;
    const color = colors[Math.floor(Math.random() * colors.length)];

    spark.style.cssText = `
      position: absolute;
      left: ${originX}px;
      top: ${originY}px;
      width: ${size}px;
      height: ${size}px;
      border-radius: 50%;
      background-color: ${color};
      box-shadow: 0 0 6px ${color};
      pointer-events: none;
      transform: translate(-50%, -50%) scale(1);
      transition: transform 500ms cubic-bezier(0.16, 1, 0.3, 1), opacity 500ms ease-out;
      z-index: 99;
    `;

    target.appendChild(spark);

    requestAnimationFrame(() => {
      spark.style.transform = `translate(calc(-50% + ${destX}px), calc(-50% + ${destY}px)) scale(0)`;
      spark.style.opacity = '0';
    });

    setTimeout(() => spark.remove(), 550);
  }
}

document.addEventListener("DOMContentLoaded", function () {
  initSpotlightEffect();
  initAnimatedCounters();

  // Attach spark burst to primary interactive buttons
  document.querySelectorAll(".btn-primary, .btn-shimmer, #startMatchBtn, .home-open-drawer-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      triggerSparkBurst(e, 8);
    });
  });
});

// -------------------- Command Palette (Cmd+K / Ctrl+K) (Linear / CMDK Standard) --------------------

function initCommandPalette() {
  const backdrop = document.getElementById("cmdPaletteBackdrop");
  const input = document.getElementById("cmdPaletteInput");
  const list = document.getElementById("cmdPaletteList");
  if (!backdrop || !input || !list) return;

  const commands = [
    { label: "Find Matches (Instant Scanner)", icon: "⚡", url: "/", meta: "Home" },
    { label: "Candidate Profile Hub", icon: "👤", url: "/candidate", meta: "Profile" },
    { label: "Pipeline Runs & Historical Batches", icon: "📊", url: "/runs", meta: "Telemetry" },
    { label: "Application CRM Kanban Board", icon: "📋", url: "/kanban", meta: "Tracker" },
    { label: "Scout Batch Run", icon: "🚀", url: "/trigger", meta: "Batch" },
    { label: "OpenTelemetry JSON Traces", icon: "🔍", url: "/api/traces", external: true, meta: "Observability" },
    {
      label: "Toggle Dark / Light Theme",
      icon: "🌓",
      action: () => {
        const toggleBtn = document.getElementById("themeToggle");
        if (toggleBtn) toggleBtn.click();
      },
      meta: "Theme"
    }
  ];

  let selectedIndex = 0;
  let filteredCommands = [...commands];

  function renderList() {
    if (!filteredCommands.length) {
      list.innerHTML = `<div style="padding: 16px; text-align: center; color: #64748b; font-size: 13px;">No commands or destinations found.</div>`;
      return;
    }

    list.innerHTML = filteredCommands.map((cmd, idx) => `
      <div class="cmdk-item ${idx === selectedIndex ? 'active' : ''}" data-idx="${idx}">
        <div class="cmdk-item-left">
          <span class="cmdk-item-icon">${cmd.icon}</span>
          <span>${cmd.label}</span>
        </div>
        <span class="cmdk-item-meta">${cmd.meta}</span>
      </div>
    `).join('');

    list.querySelectorAll(".cmdk-item").forEach((el) => {
      el.addEventListener("click", () => {
        const idx = parseInt(el.getAttribute("data-idx"), 10);
        executeCommand(filteredCommands[idx]);
      });
      el.addEventListener("mouseenter", () => {
        selectedIndex = parseInt(el.getAttribute("data-idx"), 10);
        updateActiveState();
      });
    });
  }

  function updateActiveState() {
    list.querySelectorAll(".cmdk-item").forEach((el, idx) => {
      el.classList.toggle("active", idx === selectedIndex);
      if (idx === selectedIndex) {
        el.scrollIntoView({ block: "nearest" });
      }
    });
  }

  function executeCommand(cmd) {
    if (!cmd) return;
    closePalette();
    if (cmd.action) {
      cmd.action();
    } else if (cmd.url) {
      if (cmd.external) {
        window.open(cmd.url, "_blank");
      } else {
        window.location.href = cmd.url;
      }
    }
  }

  function openPalette() {
    backdrop.classList.remove("hidden");
    input.value = "";
    filteredCommands = [...commands];
    selectedIndex = 0;
    renderList();
    setTimeout(() => input.focus(), 50);
  }

  function closePalette() {
    backdrop.classList.add("hidden");
  }

  // Keyboard shortcut listener (Cmd+K or Ctrl+K)
  window.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if (backdrop.classList.contains("hidden")) {
        openPalette();
      } else {
        closePalette();
      }
    } else if (!backdrop.classList.contains("hidden")) {
      if (e.key === "Escape") {
        e.preventDefault();
        closePalette();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        if (filteredCommands.length > 0) {
          selectedIndex = (selectedIndex + 1) % filteredCommands.length;
          updateActiveState();
        }
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (filteredCommands.length > 0) {
          selectedIndex = (selectedIndex - 1 + filteredCommands.length) % filteredCommands.length;
          updateActiveState();
        }
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (filteredCommands[selectedIndex]) {
          executeCommand(filteredCommands[selectedIndex]);
        }
      }
    }
  });

  input.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase().trim();
    filteredCommands = commands.filter((c) =>
      c.label.toLowerCase().includes(q) || c.meta.toLowerCase().includes(q)
    );
    selectedIndex = 0;
    renderList();
  });

  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) closePalette();
  });
}

// -------------------- 3D Card Tilt Physics (Aceternity / Atropos Inspired) --------------------

function initTiltCards() {
  const cards = document.querySelectorAll(".tilt-card");
  if (!cards.length) return;

  cards.forEach((card) => {
    let rafId = null;
    const maxAngle = 10; // degrees

    card.addEventListener("mousemove", (e) => {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const normX = (x / rect.width) * 2 - 1;
      const normY = (y / rect.height) * 2 - 1;

      if (rafId) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        card.style.transform = `perspective(1000px) rotateX(${-normY * maxAngle}deg) rotateY(${normX * maxAngle}deg) scale(1.01)`;
      });
    });

    card.addEventListener("mouseleave", () => {
      if (rafId) cancelAnimationFrame(rafId);
      card.style.transform = `perspective(1000px) rotateX(0deg) rotateY(0deg) scale(1)`;
    });
  });
}

// -------------------- Candidate Location Preferences Editor --------------------

function initCandidateLocationEditor() {
  const toggleBtn = document.getElementById("toggleLocationEditorBtn");
  const cancelBtn = document.getElementById("cancelLocationEditBtn");
  const form = document.getElementById("locationEditorForm");
  const displayView = document.getElementById("locationDisplayView");

  const editLocation = document.getElementById("editCandidateLocation");
  const editCountry = document.getElementById("editTargetCountry");
  const editSearchLocs = document.getElementById("editSearchLocations");
  const editBlockedLocs = document.getElementById("editBlockedLocations");

  const displayBaseLoc = document.getElementById("displayBaseLoc");
  const displayTargetCountry = document.getElementById("displayTargetCountry");
  const displaySearchLocs = document.getElementById("displaySearchLocs");
  const displayBlockedLocs = document.getElementById("displayBlockedLocs");

  if (!toggleBtn || !form) return;

  toggleBtn.addEventListener("click", () => {
    form.style.display = form.style.display === "none" ? "block" : "none";
  });

  if (cancelBtn) {
    cancelBtn.addEventListener("click", () => {
      form.style.display = "none";
    });
  }

  // Quick Location tag click helpers inside editor
  document.querySelectorAll(".quick-loc-tag").forEach((btn) => {
    btn.addEventListener("click", () => {
      const loc = btn.getAttribute("data-loc");
      if (!loc || !editSearchLocs) return;
      const current = editSearchLocs.value.trim();
      const existing = current ? current.split(",").map((s) => s.trim()) : [];
      if (!existing.includes(loc)) {
        existing.push(loc);
        editSearchLocs.value = existing.join(", ");
        showToast(`Added ${loc}`, "info");
      }
    });
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const saveBtn = document.getElementById("saveLocationBtn");
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.innerHTML = `<span>⏳</span> Saving...`;
    }

    const payload = {
      location: editLocation ? editLocation.value.trim() : null,
      target_location_country: editCountry ? editCountry.value.trim() : null,
      search_locations: editSearchLocs ? editSearchLocs.value.split(",").map((s) => s.trim()).filter(Boolean) : null,
      blocked_locations: editBlockedLocs ? editBlockedLocs.value.split(",").map((s) => s.trim()).filter(Boolean) : null,
    };

    fetch("/api/candidate/locations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((r) => r.json())
      .then((data) => {
        if (saveBtn) {
          saveBtn.disabled = false;
          saveBtn.innerHTML = `💾 Save Location Preferences`;
        }

        if (!data.ok) {
          showToast(data.error || "Failed to save location preferences.", "error");
          return;
        }

        // Update display view
        if (displayBaseLoc && data.location) displayBaseLoc.textContent = data.location;
        if (displayTargetCountry && data.target_location_country) displayTargetCountry.textContent = data.target_location_country;
        if (displaySearchLocs) displaySearchLocs.textContent = data.search_locations.length ? data.search_locations.join(", ") : "All Metros in Target Country";
        if (displayBlockedLocs && data.blocked_locations) displayBlockedLocs.textContent = data.blocked_locations.join(", ");

        form.style.display = "none";
        showToast("Location preferences updated successfully!", "success");
      })
      .catch(() => {
        if (saveBtn) {
          saveBtn.disabled = false;
          saveBtn.innerHTML = `💾 Save Location Preferences`;
        }
        showToast("Network error saving location preferences.", "error");
      });
  });
}

// -------------------- Home Page Location Quick Tags --------------------

function initHomeLocationTags() {
  const targetLocationInput = document.getElementById("targetLocation");
  if (!targetLocationInput) return;

  document.querySelectorAll(".home-loc-tag").forEach((btn) => {
    btn.addEventListener("click", () => {
      const loc = btn.getAttribute("data-loc");
      if (loc) {
        targetLocationInput.value = loc;
        showToast(`Target location set to: ${loc}`, "info");
      }
    });
  });
}

// -------------------- Candidate Profile Switcher --------------------

function initCandidateSwitcher() {
  document.querySelectorAll(".candidate-switch-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const candidateId = btn.getAttribute("data-candidate-id");
      if (!candidateId) return;

      btn.disabled = true;
      showToast(`Activating candidate profile: ${candidateId}...`, "info");

      fetch("/api/candidate/switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate_id: candidateId }),
      })
        .then((r) => r.json())
        .then((data) => {
          if (data.ok) {
            showToast("Candidate profile activated successfully!", "success");
            setTimeout(() => {
              window.location.reload();
            }, 400);
          } else {
            btn.disabled = false;
            showToast(data.error || "Failed to switch candidate.", "error");
          }
        })
        .catch(() => {
          btn.disabled = false;
          showToast("Network error switching candidate.", "error");
        });
    });
  });
}

document.addEventListener("DOMContentLoaded", function () {
  initCandidateLocationEditor();
  initHomeLocationTags();
  initCandidateSwitcher();
});

window.showToast = showToast;
window.initHomeCharts = initHomeCharts;
window.initThemeToggle = initThemeToggle;
window.initCopyButton = initCopyButton;
window.initTriggerPage = initTriggerPage;
window.initRunsPage = initRunsPage;
window.initKanbanPage = initKanbanPage;
window.initSpotlightEffect = initSpotlightEffect;
window.initAnimatedCounters = initAnimatedCounters;
window.triggerSparkBurst = triggerSparkBurst;
window.initCommandPalette = initCommandPalette;
window.initTiltCards = initTiltCards;
window.initCandidateLocationEditor = initCandidateLocationEditor;
window.initHomeLocationTags = initHomeLocationTags;
window.initCandidateSwitcher = initCandidateSwitcher;




