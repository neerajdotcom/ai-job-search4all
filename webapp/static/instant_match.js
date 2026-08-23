/**
 * instant_match.js — Client-side live stream listener, device file uploads (.pdf, .docx),
 * cloud link imports (Google Drive / Dropbox), drag-and-drop, and form handler.
 */

let pathwayDebounceTimer = null;
let pathwayAbortController = null;

function setupFileUploader(fileInputId, uploadBtnId, cloudBtnId, cloudRowId, cloudUrlId, cloudFetchBtnId, textAreaId, statusRowId, badgeId, isPrimary = true) {
  const fileInput = document.getElementById(fileInputId);
  const uploadBtn = document.getElementById(uploadBtnId);
  const cloudBtn = document.getElementById(cloudBtnId);
  const cloudRow = document.getElementById(cloudRowId);
  const cloudUrl = document.getElementById(cloudUrlId);
  const cloudFetchBtn = document.getElementById(cloudFetchBtnId);
  const textArea = document.getElementById(textAreaId);
  const statusRow = document.getElementById(statusRowId);
  const badge = document.getElementById(badgeId);

  // Trigger system file picker
  if (uploadBtn && fileInput) {
    uploadBtn.addEventListener("click", () => fileInput.click());
  }

  // Toggle Cloud Link input
  if (cloudBtn && cloudRow) {
    cloudBtn.addEventListener("click", () => {
      const isHidden = cloudRow.style.display === "none";
      cloudRow.style.display = isHidden ? "block" : "none";
      if (isHidden && cloudUrl) cloudUrl.focus();
    });
  }

  // Upload file handler
  async function handleFileUpload(file) {
    if (!file) return;
    if (uploadBtn) {
      uploadBtn.disabled = true;
      uploadBtn.textContent = "⏳ Parsing...";
    }
    if (window.showToast) {
      window.showToast(`Uploading and extracting '${file.name}'...`, "info");
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      const resp = await fetch("/api/resume/upload", {
        method: "POST",
        body: formData,
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        throw new Error(data.error || "Failed to extract text from resume");
      }

      if (textArea) {
        textArea.value = data.text;
        textArea.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (statusRow && badge) {
        statusRow.style.display = "flex";
        badge.textContent = `✓ ${data.filename} (${data.char_count.toLocaleString()} characters extracted)`;
      }
      if (window.showToast) {
        window.showToast(`Extracted ${data.filename} successfully!`, "success");
      }

      // Auto-detect name & title if empty
      if (isPrimary) {
        const nameInput = document.getElementById("targetName");
        const titleInput = document.getElementById("targetTitle");
        const lines = data.text.split("\n").map(l => l.trim()).filter(Boolean);

        if (nameInput && (!nameInput.value.trim() || nameInput.value.trim() === "Candidate")) {
          for (const l of lines.slice(0, 5)) {
            const clean = l.split(/[|•–—\t]/)[0].trim().replace(/\(.*?\)/g, "").replace(/[^a-zA-Z\s\.\-']/g, "").trim();
            const words = clean.split(/\s+/).filter(Boolean);
            if (words.length >= 1 && words.length <= 4 && clean.length >= 2 && clean.length <= 35 && !/resume|cv|curriculum|summary|experience|contact/i.test(clean)) {
              nameInput.value = clean;
              break;
            }
          }
        }

        if (titleInput && !titleInput.value.trim()) {
          for (const l of lines.slice(0, 8)) {
            if (/engineer|manager|developer|architect|designer|lead|analyst|producer|director/i.test(l) && l.length < 50 && !l.includes("@")) {
              titleInput.value = l;
              break;
            }
          }
        }
        if (data.text && data.text.trim().length >= 30) {
          analyzeCareerPathways(data.text.trim(), true);
        }
      }
    } catch (err) {
      if (window.showToast) {
        window.showToast(`Upload failed: ${err.message}`, "danger");
      } else {
        alert(err.message);
      }
    } finally {
      if (uploadBtn) {
        uploadBtn.disabled = false;
        uploadBtn.textContent = isPrimary ? "📂 Upload File (.pdf, .docx)" : "📂 Upload File";
      }
    }
  }

  if (fileInput) {
    fileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
      }
    });
  }

  // Fetch Cloud Link handler (Google Drive / Dropbox / Public URL)
  if (cloudFetchBtn && cloudUrl) {
    cloudFetchBtn.addEventListener("click", async () => {
      const url = cloudUrl.value.trim();
      if (!url) {
        if (window.showToast) window.showToast("Please enter a cloud resume link", "warning");
        return;
      }
      cloudFetchBtn.disabled = true;
      cloudFetchBtn.textContent = "⏳ Fetching...";
      if (window.showToast) window.showToast("Connecting to cloud storage and extracting...", "info");

      try {
        const resp = await fetch("/api/resume/fetch-url", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: url }),
        });
        const data = await resp.json();
        if (!resp.ok || !data.ok) {
          throw new Error(data.error || "Failed to fetch from cloud");
        }

        if (textArea) {
          textArea.value = data.text;
          textArea.dispatchEvent(new Event("input", { bubbles: true }));
        }
        if (statusRow && badge) {
          statusRow.style.display = "flex";
          badge.textContent = `✓ Cloud Import (${data.char_count.toLocaleString()} characters extracted)`;
        }
        if (cloudRow) cloudRow.style.display = "none";
        if (window.showToast) window.showToast("Cloud resume imported successfully!", "success");

        if (isPrimary && data.text && data.text.trim().length >= 30) {
          analyzeCareerPathways(data.text.trim(), true);
        }
      } catch (err) {
        if (window.showToast) {
          window.showToast(`Cloud fetch error: ${err.message}`, "danger");
        } else {
          alert(err.message);
        }
      } finally {
        cloudFetchBtn.disabled = false;
        cloudFetchBtn.textContent = "Fetch";
      }
    });
  }

  // Drag and drop directly on textarea
  if (textArea) {
    textArea.addEventListener("dragover", (e) => {
      e.preventDefault();
      textArea.style.borderColor = "var(--accent-cyan-fg)";
    });
    textArea.addEventListener("dragleave", (e) => {
      e.preventDefault();
      textArea.style.borderColor = "var(--border-default)";
    });
    textArea.addEventListener("drop", (e) => {
      e.preventDefault();
      textArea.style.borderColor = "var(--border-default)";
      if (e.dataTransfer && e.dataTransfer.files.length > 0) {
        handleFileUpload(e.dataTransfer.files[0]);
      }
    });
  }
}

function initInstantMatcher() {
  const form = document.getElementById("instantMatchForm");
  if (!form) return;

  const submitBtn = document.getElementById("startMatchBtn");
  const progressContainer = document.getElementById("progressContainer");
  const progressStage = document.getElementById("progressStage");
  const progressPct = document.getElementById("progressPct");
  const progressBar = document.getElementById("progressBar");
  const progressMessage = document.getElementById("progressMessage");
  const resumeTextArea = document.getElementById("resumeText");
  const resumeSecondaryTextArea = document.getElementById("resumeSecondaryText");
  const toggleSecBtn = document.getElementById("toggleSecondaryResumeBtn");
  const secGroup = document.getElementById("secondaryResumeGroup");

  // Secondary resume toggle
  if (toggleSecBtn && secGroup) {
    toggleSecBtn.addEventListener("click", function () {
      const isHidden = secGroup.style.display === "none";
      secGroup.style.display = isHidden ? "block" : "none";
      toggleSecBtn.textContent = isHidden ? "− Remove Secondary Resume" : "+ Add Secondary Resume (Track 2)";
    });
  }

  // Initialize Primary Uploader
  setupFileUploader(
    "primaryFileInput", "uploadPrimaryBtn", "cloudPrimaryBtn", "primaryCloudRow",
    "primaryCloudUrl", "primaryCloudFetchBtn", "resumeText", "primaryFileStatus", "primaryFileBadge", true
  );

  // Initialize Secondary Uploader
  setupFileUploader(
    "secondaryFileInput", "uploadSecondaryBtn", "cloudSecondaryBtn", "secondaryCloudRow",
    "secondaryCloudUrl", "secondaryCloudFetchBtn", "resumeSecondaryText", "secondaryFileStatus", "secondaryFileBadge", false
  );

  // Keyboard shortcut: Cmd+Enter or Ctrl+Enter to submit
  if (resumeTextArea) {
    resumeTextArea.addEventListener("keydown", function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        form.requestSubmit();
      }
    });

    // Auto-analyze pathways with debounce on typing / pasting
    resumeTextArea.addEventListener("input", function () {
      clearTimeout(pathwayDebounceTimer);
      const text = resumeTextArea.value.trim();
      if (text.length >= 50) {
        pathwayDebounceTimer = setTimeout(() => {
          analyzeCareerPathways(text, false);
        }, 800);
      }
    });
  }

  // Refresh Paths Button Listener
  const reanalyzeBtn = document.getElementById("reanalyzePathwaysBtn");
  if (reanalyzeBtn) {
    reanalyzeBtn.addEventListener("click", (e) => {
      e.preventDefault();
      clearTimeout(pathwayDebounceTimer);
      const text = resumeTextArea ? resumeTextArea.value.trim() : "";
      if (text.length >= 30) {
        analyzeCareerPathways(text, true);
      } else {
        if (window.showToast) {
          window.showToast("Please upload or paste a resume (at least 30 characters) to analyze pathways.", "warning");
        } else {
          alert("Please upload or paste a resume (at least 30 characters) to analyze pathways.");
        }
      }
    });
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();

    const resumeText = resumeTextArea.value;
    const resumeSecText = resumeSecondaryTextArea ? resumeSecondaryTextArea.value : "";
    const name = document.getElementById("targetName") ? document.getElementById("targetName").value : "";
    const title = document.getElementById("targetTitle").value;
    const location = document.getElementById("targetLocation").value;
    const remoteOnly = document.getElementById("remoteOnly").checked;

    // Collect selected tracks
    const selectedTrackCheckboxes = document.querySelectorAll(".pathway-card-checkbox:checked");
    const selectedTracks = Array.from(selectedTrackCheckboxes).map(cb => cb.value);

    if (!resumeText || resumeText.trim().length < 50) {
      if (window.showToast) {
        window.showToast("Please upload a resume or paste at least 50 characters of text.", "warning");
      } else {
        alert("Please upload a resume or paste at least 50 characters of text.");
      }
      return;
    }

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span>⚡</span> Scouting & Matching Across Pathways...';
    progressContainer.style.display = "block";
    progressBar.style.width = "10%";
    if (progressPct) progressPct.innerText = "10%";
    progressStage.innerText = "Initializing Multi-Track Scout...";
    progressMessage.innerText = "Deconstructing career tracks and connecting to live search...";

    try {
      const resp = await fetch("/api/match/instant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_text: resumeText,
          resume_secondary_text: resumeSecText ? resumeSecText.trim() : null,
          name: name ? name.trim() : "",
          title: title,
          location: location,
          remote_only: remoteOnly,
          selected_tracks: selectedTracks.length > 0 ? selectedTracks : null,
          pathways: window._currentPathways || null,
        }),
      });

      const data = await resp.json();
      if (!resp.ok || !data.session_id) {
        throw new Error(data.error || "Failed to start match session");
      }

      const sessionId = data.session_id;

      // Connect to SSE stream
      const evtSource = new EventSource(`/api/match/stream/${sessionId}`);

      function getStageTitle(stage) {
        switch (stage) {
          case "extracting": return "Analyzing Pathways & Profile";
          case "scouting": return "Scouting Job Boards";
          case "scoring": return "Scoring Multi-Track Fit";
          case "tailoring": return "Tailoring Fast-Apply Packs";
          case "done": return "✓ Recommendations Ready";
          default: return "Processing";
        }
      }

      evtSource.onmessage = function (event) {
        try {
          const payload = JSON.parse(event.data);
          if (payload.stage) {
            progressStage.innerText = getStageTitle(payload.stage);
          }
          if (payload.message) {
            progressMessage.innerText = payload.message;
          }
          if (payload.percent) {
            progressBar.style.width = `${payload.percent}%`;
            if (progressPct) progressPct.innerText = `${payload.percent}%`;
          }

          if (payload.stage === "done") {
            evtSource.close();
            progressBar.style.width = "100%";
            if (progressPct) progressPct.innerText = "100%";
            progressStage.innerText = "✓ Recommendations Ready!";
            progressMessage.innerText = "Redirecting to your multi-track match recommendations...";
            setTimeout(() => {
              window.location.href = `/match/${sessionId}`;
            }, 600);
          } else if (payload.stage === "error") {
            evtSource.close();
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<span>⚡</span> Try Again';
            progressStage.innerText = "Error during matching";
            progressMessage.innerText = payload.message || "An unexpected error occurred.";
          }
        } catch (err) {
          console.error("SSE parse error", err);
        }
      };

      evtSource.onerror = function (err) {
        console.error("SSE connection error", err);
        setTimeout(async () => {
          try {
            const check = await fetch(`/api/match/results/${sessionId}`);
            const statusData = await check.json();
            if (statusData.status === "completed") {
              evtSource.close();
              window.location.href = `/match/${sessionId}`;
            }
          } catch (e) {}
        }, 3000);
      };

    } catch (err) {
      if (window.showToast) {
        window.showToast("Error: " + err.message, "danger");
      } else {
        alert("Error: " + err.message);
      }
      submitBtn.disabled = false;
      submitBtn.innerHTML = '<span>⚡</span> Find Matches & Generate Fast-Apply Packs';
      progressContainer.style.display = "none";
    }
  });
}

// Asynchronous Career Divergence Pathway Analysis
async function analyzeCareerPathways(resumeText, force = false) {
  const container = document.getElementById("pathwaysContainer");
  const grid = document.getElementById("pathwaysGrid");
  const reanalyzeBtn = document.getElementById("reanalyzePathwaysBtn");
  if (!container || !grid) return;

  if (window._analyzingPathways && !force) return;

  if (pathwayAbortController) {
    pathwayAbortController.abort();
  }
  pathwayAbortController = new AbortController();
  window._analyzingPathways = true;

  if (reanalyzeBtn) {
    reanalyzeBtn.disabled = true;
    reanalyzeBtn.innerHTML = '<span>⏳</span> Refreshing...';
  }
  container.style.display = "block";

  if (force || !grid.children.length) {
    grid.innerHTML = `
      <div style="grid-column: 1 / -1; padding: 24px; text-align: center; color: var(--ink-muted);">
        <span style="display: inline-block; animation: pulse 1s infinite; margin-right: 6px;">⚡</span>
        Deconstructing candidate background into 3 strategic career pathways...
      </div>
    `;
  }

  try {
    const titleInput = document.getElementById("targetTitle");
    const resp = await fetch("/api/career/pathways", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: pathwayAbortController.signal,
      body: JSON.stringify({
        resume_text: resumeText,
        title: titleInput ? titleInput.value.trim() : "",
      }),
    });

    const data = await resp.json();
    if (resp.ok && data.ok && data.pathways && data.pathways.length > 0) {
      window._currentPathways = data.pathways;

      // Populate candidate name if available
      const nameInput = document.getElementById("targetName");
      if (nameInput && (!nameInput.value.trim() || nameInput.value.trim() === "Candidate") && data.candidate_name && data.candidate_name !== "Candidate") {
        nameInput.value = data.candidate_name;
      }

      renderPathways(data.pathways, grid);
      container.style.display = "block";
      if (force && window.showToast) {
        window.showToast("Career pathways refreshed successfully!", "success");
      }
    } else {
      window._currentPathways = [];
      container.style.display = "none";
      if (force && window.showToast) {
        window.showToast(data.error || "No recognized career pathways for this resume text.", "warning");
      }
    }
  } catch (err) {
    if (err.name !== "AbortError") {
      console.warn("Could not analyze career pathways:", err);
      if (force && window.showToast) {
        window.showToast("Failed to refresh career pathways: " + err.message, "danger");
      }
    }
  } finally {
    window._analyzingPathways = false;
    if (reanalyzeBtn) {
      reanalyzeBtn.disabled = false;
      reanalyzeBtn.innerHTML = '🔄 Refresh Paths';
    }
  }
}

function renderPathways(pathways, containerEl) {
  containerEl.innerHTML = "";
  pathways.forEach((pw, idx) => {
    const card = document.createElement("div");
    card.className = "pathway-card active";
    card.dataset.trackId = pw.id;

    const cos = (pw.target_companies || []).slice(0, 3).map(c => `<span class="co-chip">${c}</span>`).join("");
    const skills = (pw.key_transferable_skills || []).slice(0, 3).map(s => `<span class="skill-chip">${s}</span>`).join("");

    card.innerHTML = `
      <div class="pathway-card-top">
        <div>
          <label class="pathway-select-label" style="display: flex; align-items: center; gap: 6px; cursor: pointer;">
            <input type="checkbox" class="pathway-card-checkbox" value="${pw.id}" checked>
            <span class="pathway-badge-pill role-${pw.role_type}">${pw.track_label}</span>
          </label>
          <h4 class="pathway-title">${pw.title}</h4>
        </div>
        <div class="pathway-potential-meter">
          <div class="potential-val">${pw.potential_score}%</div>
          <div class="potential-sub">Potential</div>
        </div>
      </div>
      <p class="pathway-tagline">${pw.tagline || ""}</p>
      <div class="pathway-cos">
        ${cos}
      </div>
      <div class="pathway-skills" style="display: flex; gap: 4px; flex-wrap: wrap; margin-top: 8px;">
        ${skills}
      </div>
    `;

    // Click anywhere on card to toggle
    const checkbox = card.querySelector(".pathway-card-checkbox");
    card.addEventListener("click", (e) => {
      if (e.target !== checkbox) {
        checkbox.checked = !checkbox.checked;
      }
      card.classList.toggle("active", checkbox.checked);
    });

    checkbox.addEventListener("change", () => {
      card.classList.toggle("active", checkbox.checked);
    });

    containerEl.appendChild(card);
  });
}

// Set of tracks explicitly ignored/excluded by the user for this run
const ignoredTracks = new Set();

function toggleTrackStatus(trackId, sourceBtn) {
  const pathwayCard = document.getElementById(`pathway_card_${trackId}`);
  const filterPill = document.querySelector(`.track-filter-pill[data-track-filter="${trackId}"]`);
  
  if (ignoredTracks.has(trackId)) {
    // Restore / Re-enable Track
    ignoredTracks.delete(trackId);
    if (pathwayCard) {
      pathwayCard.classList.remove("ignored-track");
      pathwayCard.classList.add("active");
    }
    if (filterPill) {
      filterPill.classList.remove("track-pill-ignored");
    }
    updateTrackToggleButtons(trackId, true);
    if (window.showToast) {
      window.showToast("Restored career track and revealed matching positions.", "success");
    }
  } else {
    // Ignore / Exclude Track
    ignoredTracks.add(trackId);
    if (pathwayCard) {
      pathwayCard.classList.add("ignored-track");
      pathwayCard.classList.remove("active");
    }
    if (filterPill) {
      filterPill.classList.add("track-pill-ignored");
      // If currently active on this ignored filter pill, switch to "all"
      if (filterPill.classList.contains("active")) {
        const allBtn = document.querySelector('.track-filter-pill[data-track-filter="all"]');
        if (allBtn) {
          document.querySelectorAll(".track-filter-pill").forEach(b => b.classList.remove("active"));
          allBtn.classList.add("active");
        }
      }
    }
    updateTrackToggleButtons(trackId, false);
    if (window.showToast) {
      window.showToast("Ignored career track: removed all its jobs from this run.", "warning");
    }
  }

  updateJobVisibility();
}

function updateTrackToggleButtons(trackId, isActive) {
  const btns = document.querySelectorAll(`.btn-track-toggle[data-track-id="${trackId}"]`);
  btns.forEach(btn => {
    if (isActive) {
      btn.classList.remove("btn-track-ignored");
      btn.classList.add("btn-track-active");
      btn.innerHTML = '<span class="track-toggle-icon">✓</span> <span class="track-toggle-label">Active</span>';
      btn.title = "Click to ignore this track and remove its jobs from this run";
    } else {
      btn.classList.add("btn-track-ignored");
      btn.classList.remove("btn-track-active");
      btn.innerHTML = '<span class="track-toggle-icon">⊘</span> <span class="track-toggle-label">Ignored</span>';
      btn.title = "Click to restore this track";
    }
  });
}

function restoreAllTracks() {
  ignoredTracks.clear();
  document.querySelectorAll(".pathway-card").forEach(c => {
    c.classList.remove("ignored-track");
    c.classList.add("active");
  });
  document.querySelectorAll(".btn-track-toggle").forEach(btn => {
    btn.classList.remove("btn-track-ignored");
    btn.classList.add("btn-track-active");
    btn.innerHTML = '<span class="track-toggle-icon">✓</span> <span class="track-toggle-label">Active</span>';
    btn.title = "Click to ignore this track and remove its jobs from this run";
  });
  document.querySelectorAll(".track-filter-pill").forEach(p => p.classList.remove("track-pill-ignored"));
  updateJobVisibility();
  if (window.showToast) {
    window.showToast("All career tracks restored.", "success");
  }
}

function updateJobVisibility() {
  const activeFilterBtn = document.querySelector(".track-filter-pill.active");
  const currentFilter = activeFilterBtn ? activeFilterBtn.dataset.trackFilter : "all";
  const jobCards = document.querySelectorAll(".match-card");
  
  let visibleCount = 0;
  let totalScoreSum = 0;

  jobCards.forEach(card => {
    const cardTrackId = card.dataset.trackId || "track_a";
    const isTrackIgnored = ignoredTracks.has(cardTrackId);
    
    if (isTrackIgnored) {
      card.style.display = "none";
    } else if (currentFilter === "all" || cardTrackId === currentFilter) {
      card.style.display = "block";
      visibleCount++;
      const scoreNum = parseInt(card.querySelector(".score-number")?.textContent || "0", 10);
      totalScoreSum += scoreNum;
    } else {
      card.style.display = "none";
    }
  });

  // Update dynamic KPI values
  const kpiCount = document.getElementById("kpiQualifyingMatches");
  if (kpiCount) kpiCount.textContent = visibleCount;

  const kpiAvg = document.getElementById("kpiAvgScore");
  if (kpiAvg) {
    kpiAvg.textContent = visibleCount > 0 ? `${Math.round(totalScoreSum / visibleCount)}%` : "0%";
  }

  // Update "All Active Tracks (N)" pill
  const allPill = document.querySelector('.track-filter-pill[data-track-filter="all"]');
  if (allPill) {
    allPill.textContent = `All Active Tracks (${visibleCount})`;
  }

  // Toggle empty state if zero matches remain
  const emptyState = document.getElementById("emptyFilteredState");
  if (emptyState) {
    emptyState.style.display = (visibleCount === 0 && jobCards.length > 0) ? "block" : "none";
  }
}

// Track Filter Toolbar on Results Page
function initTrackFilter() {
  const filterToolbar = document.getElementById("trackFilterToolbar");
  if (!filterToolbar) return;

  const buttons = filterToolbar.querySelectorAll(".track-filter-pill");

  buttons.forEach(btn => {
    btn.addEventListener("click", () => {
      if (btn.classList.contains("track-pill-ignored")) return;
      buttons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      updateJobVisibility();
    });
  });
}

function copyText(elementId, btn) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const text = el.innerText || el.textContent || "";
  navigator.clipboard.writeText(text).then(() => {
    if (window.showToast) {
      window.showToast("Copied to clipboard!", "success");
    }
    if (btn) {
      const orig = btn.innerHTML;
      btn.innerHTML = "✓ Copied";
      setTimeout(() => { btn.innerHTML = orig; }, 1500);
    }
  });
}

document.addEventListener("DOMContentLoaded", function () {
  initTrackFilter();

  // Toggle fast-apply drawer accordions
  document.querySelectorAll(".toggle-pack-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.dataset.jobId;
      const drawer = document.getElementById(targetId);
      if (drawer) {
        const isHidden = drawer.style.display === "none";
        drawer.style.display = isHidden ? "block" : "none";
        btn.innerHTML = isHidden ? "⚡ Fast-Apply Pack ▴" : "⚡ Fast-Apply Pack ▾";
      }
    });
  });
});

window.copyText = copyText;
window.initInstantMatcher = initInstantMatcher;
window.toggleTrackStatus = toggleTrackStatus;
window.restoreAllTracks = restoreAllTracks;
window.updateJobVisibility = updateJobVisibility;
