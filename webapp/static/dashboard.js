// webapp/static/dashboard.js — Chart.js init, trigger polling, copy-to-clipboard.
// No build step / no framework — plain DOM + fetch, loaded as a classic script.

// Warm palette echoing the light theme; a parallel set for dark mode so
// charts repaint correctly when the toggle flips. Recomputed on every
// initHomeCharts() call rather than once at load, since the user can
// switch themes without a page reload.
const LIGHT_PALETTE = {
  coral: "#cc785c", olive: "#7a8754", amber: "#c68e3d",
  terracotta: "#a55c44", teal: "#5a8e8e", ink: "#9a9690",
  text: "#6e6a63", grid: "#f0ece0", doughnutBorder: "#faf9f5",
};
const DARK_PALETTE = {
  coral: "#d4a574", olive: "#8a9d6a", amber: "#e0b563",
  terracotta: "#c4795c", teal: "#6fb3b3", ink: "#999999",
  text: "#999999", grid: "#2e2c29", doughnutBorder: "#1a1a1a",
};

function currentPalette() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? DARK_PALETTE : LIGHT_PALETTE;
}

Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif';
Chart.defaults.font.size = 12;

let homeCharts = [];

function destroyHomeCharts() {
  homeCharts.forEach((c) => c.destroy());
  homeCharts = [];
}

function initHomeCharts(stats) {
  destroyHomeCharts();
  const PALETTE = currentPalette();
  const PALETTE_SEQ = [PALETTE.coral, PALETTE.olive, PALETTE.amber, PALETTE.terracotta, PALETTE.teal];
  Chart.defaults.color = PALETTE.text;
  Chart.defaults.borderColor = PALETTE.grid;

  const scoreCtx = document.getElementById("scoreChart");
  if (scoreCtx) {
    homeCharts.push(new Chart(scoreCtx, {
      type: "bar",
      data: {
        labels: Object.keys(stats.score_distribution),
        datasets: [{
          label: "Jobs",
          data: Object.values(stats.score_distribution),
          backgroundColor: PALETTE.coral,
          borderRadius: 4,
        }],
      },
      options: { plugins: { legend: { display: false } } },
    }));
  }

  const timeCtx = document.getElementById("timeChart");
  if (timeCtx) {
    homeCharts.push(new Chart(timeCtx, {
      type: "line",
      data: {
        labels: stats.runs_over_time.map((r) => r.run_id),
        datasets: [
          {
            label: "Scored",
            data: stats.runs_over_time.map((r) => r.total_scored),
            borderColor: PALETTE.ink,
            backgroundColor: PALETTE.ink,
            tension: 0.3,
            pointRadius: 3,
          },
          {
            label: "Qualifying",
            data: stats.runs_over_time.map((r) => r.total_qualifying),
            borderColor: PALETTE.coral,
            backgroundColor: PALETTE.coral,
            tension: 0.3,
            pointRadius: 3,
          },
        ],
      },
    }));
  }

  const sourceCtx = document.getElementById("sourceChart");
  if (sourceCtx) {
    homeCharts.push(new Chart(sourceCtx, {
      type: "doughnut",
      data: {
        labels: Object.keys(stats.source_breakdown),
        datasets: [{
          data: Object.values(stats.source_breakdown),
          backgroundColor: PALETTE_SEQ,
          borderWidth: 2,
          borderColor: PALETTE.doughnutBorder,
        }],
      },
      options: { cutout: "65%" },
    }));
  }

  const companyCtx = document.getElementById("companyChart");
  if (companyCtx) {
    homeCharts.push(new Chart(companyCtx, {
      type: "bar",
      data: {
        labels: stats.top_companies.map((c) => c.company),
        datasets: [{
          label: "Qualifying matches",
          data: stats.top_companies.map((c) => c.count),
          backgroundColor: PALETTE.olive,
          borderRadius: 4,
        }],
      },
      options: {
        indexAxis: "y",
        plugins: { legend: { display: false } },
      },
    }));
  }
}

function initThemeToggle() {
  const btn = document.getElementById("themeToggle");
  if (!btn) return;

  function syncIcon() {
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    btn.textContent = dark ? "☀️" : "🌙";
  }

  syncIcon();
  btn.addEventListener("click", function () {
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    if (dark) {
      document.documentElement.removeAttribute("data-theme");
      localStorage.setItem("theme", "light");
    } else {
      document.documentElement.setAttribute("data-theme", "dark");
      localStorage.setItem("theme", "dark");
    }
    syncIcon();
    // Charts read computed colors once at creation time, so a theme flip
    // needs a destroy + recreate, not just a CSS repaint.
    if (window.DASHBOARD_STATS && window.initHomeCharts) {
      window.initHomeCharts(window.DASHBOARD_STATS);
    }
  });
}

function initCopyButton(buttonId, textId) {
  const btn = document.getElementById(buttonId);
  const block = document.getElementById(textId);
  if (!btn || !block) return;
  btn.addEventListener("click", function () {
    navigator.clipboard.writeText(block.textContent).then(function () {
      const original = btn.textContent;
      btn.textContent = "Copied!";
      setTimeout(function () { btn.textContent = original; }, 1500);
    });
  });
}

function initTriggerPage() {
  const form = document.getElementById("triggerForm");
  const dryRunCheckbox = document.getElementById("dryRunCheckbox");
  const resumePathInput = document.getElementById("resumePathInput");
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

  // Reflect any already-in-progress run on page load.
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
        // A run started after this page loaded — let the server render the row.
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
        // Run errored with no snapshot — show the error in-place rather than
        // reloading to a blank table (no snapshot means no completed row would appear).
        const statusSpan = document.getElementById("inProgressStatus");
        if (statusSpan) statusSpan.textContent = "Error: " + status.error;
        if (pollHandle) { clearInterval(pollHandle); pollHandle = null; }
      } else {
        // Run finished successfully — reload to show the completed snapshot row.
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
          }
        })
        .catch(function () {
          if (previousNextSibling) {
            previousParent.insertBefore(card, previousNextSibling);
          } else {
            previousParent.appendChild(card);
          }
          if (message) {
            message.textContent = "Failed to save — check the server log.";
            message.className = "trigger-message error";
          }
        });
    });
  });
}

window.initHomeCharts = initHomeCharts;
window.initThemeToggle = initThemeToggle;
window.initCopyButton = initCopyButton;
window.initTriggerPage = initTriggerPage;
window.initRunsPage = initRunsPage;
window.initKanbanPage = initKanbanPage;
