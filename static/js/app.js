document.addEventListener("DOMContentLoaded", () => {

  // ---------------- Neues Projekt ----------------
  const btnNew = document.getElementById("btn-new-project");
  const formNew = document.getElementById("form-new-project");
  const btnCancelNew = document.getElementById("np-cancel");

  btnNew.addEventListener("click", () => {
    formNew.classList.toggle("hidden");
  });
  btnCancelNew.addEventListener("click", () => {
    formNew.classList.add("hidden");
    formNew.reset();
  });

  formNew.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("np-name").value.trim();
    const [year, q] = document.getElementById("np-start").value.split("-").map(Number);
    const duration = parseInt(document.getElementById("np-duration").value, 10);
    if (!name || !duration) return;

    const res = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, start_year: year, start_q: q, duration }),
    });
    if (res.ok) {
      location.reload();
    } else {
      alert("Projekt konnte nicht gespeichert werden.");
    }
  });

  // Projekt löschen (Papierkorb in der Liste)
  document.querySelectorAll(".btn-delete-project").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const item = btn.closest(".project-list-item");
      const projectId = item.dataset.projectId;
      if (!confirm("Dieses Projekt inkl. aller Teilschritte und Manntage-Einträge wirklich löschen?")) return;
      const res = await fetch(`/api/projects/${projectId}`, { method: "DELETE" });
      if (res.ok) location.reload();
    });
  });

  // ---------------- Teilschritte ein-/ausklappen ----------------
  document.querySelectorAll(".expand-toggle").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const block = btn.closest(".project-block");
      const list = block.querySelector(".steps-list");
      btn.classList.toggle("is-open");
      list.classList.toggle("is-open");
    });
  });

  // Teilschritt löschen
  document.querySelectorAll(".btn-delete-step").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const stepId = btn.dataset.stepId;
      if (!confirm("Diesen Teilschritt wirklich löschen?")) return;
      const res = await fetch(`/api/steps/${stepId}`, { method: "DELETE" });
      if (res.ok) location.reload();
    });
  });

  // "Heute" Button: zum aktuellen Quartal scrollen
  const btnToday = document.getElementById("btn-today");
  if (btnToday) {
    btnToday.addEventListener("click", () => {
      const current = document.querySelector(".head-cell.is-current");
      if (current) {
        current.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
      }
    });
  }

  // ---------------- Modal: Manntage eintragen (ein Quartal) ----------------
  const overlay = document.getElementById("modal-overlay");
  const modalBody = document.getElementById("modal-body");
  const modalProjectName = document.getElementById("modal-project-name");
  const modalSubtitle = document.getElementById("modal-subtitle");
  const btnClose = document.getElementById("modal-close");
  const btnCancel = document.getElementById("modal-cancel");
  const btnSave = document.getElementById("modal-save");

  let currentContext = null; // { projectId, year, q }

  document.querySelectorAll(".bar-segment:not(.bar-segment-static)").forEach((seg) => {
    seg.addEventListener("click", () => openModal(seg));
  });

  function openModal(seg) {
    const projectId = seg.dataset.projectId;
    const projectName = seg.dataset.projectName;
    const label = seg.dataset.label;
    const year = seg.dataset.year;
    const q = seg.dataset.q;
    let alloc = [];
    try { alloc = JSON.parse(seg.dataset.alloc); } catch (e) { alloc = []; }

    currentContext = { projectId, year, q };
    modalProjectName.textContent = projectName;
    if (modalSubtitle) modalSubtitle.textContent = `Quartal ${label}`;

    modalBody.innerHTML = "";
    alloc.forEach((a) => {
      const row = document.createElement("div");
      row.className = "modal-field";
      row.innerHTML = `
        <label>
          <svg class="icon-sm"><use href="#icon-person"/></svg>
          ${a.member}
        </label>
        <span style="display:flex; align-items:center; gap:6px;">
          <input type="number" min="0" step="0.5" value="${a.manntage}" data-member-id="${a.member_id}">
          <span class="modal-field-unit">Tage</span>
        </span>
      `;
      modalBody.appendChild(row);
    });

    overlay.classList.remove("hidden");
  }

  function closeModal() {
    overlay.classList.add("hidden");
    currentContext = null;
  }

  btnClose.addEventListener("click", closeModal);
  btnCancel.addEventListener("click", closeModal);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeModal();
  });

  btnSave.addEventListener("click", async () => {
    if (!currentContext) return;
    const values = {};
    modalBody.querySelectorAll("input[data-member-id]").forEach((input) => {
      values[input.dataset.memberId] = parseFloat(input.value || "0");
    });

    const res = await fetch("/api/allocations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: currentContext.projectId,
        year: currentContext.year,
        quarter: currentContext.q,
        values,
      }),
    });
    if (res.ok) {
      location.reload();
    } else {
      alert("Speichern fehlgeschlagen.");
    }
  });

  // ---------------- Modal: Projekt / Teilschritt bearbeiten ----------------
  const editOverlay = document.getElementById("edit-modal-overlay");
  const editTitle = document.getElementById("edit-modal-title");
  const emName = document.getElementById("em-name");
  const emStart = document.getElementById("em-start");
  const emDuration = document.getElementById("em-duration");
  const editClose = document.getElementById("edit-modal-close");
  const editCancel = document.getElementById("edit-modal-cancel");
  const editSave = document.getElementById("edit-modal-save");
  const editDelete = document.getElementById("edit-modal-delete");

  let editContext = null; // { type: 'project'|'step', id, projectId(optional, create-mode) }

  function openEditModal(opts) {
    editContext = opts;
    editTitle.textContent = opts.title;
    emName.value = opts.name || "";
    emStart.value = `${opts.startYear}-${opts.startQ}`;
    emDuration.value = opts.duration || 1;
    editDelete.style.display = opts.isCreate ? "none" : "";
    editOverlay.classList.remove("hidden");
    emName.focus();
  }

  function closeEditModal() {
    editOverlay.classList.add("hidden");
    editContext = null;
  }

  editClose.addEventListener("click", closeEditModal);
  editCancel.addEventListener("click", closeEditModal);
  editOverlay.addEventListener("click", (e) => {
    if (e.target === editOverlay) closeEditModal();
  });

  // Projekt bearbeiten öffnen
  document.querySelectorAll(".btn-edit-project").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const d = btn.dataset;
      openEditModal({
        type: "project",
        id: d.projectId,
        title: "Projekt bearbeiten",
        name: d.name,
        startYear: d.startYear,
        startQ: d.startQ,
        duration: d.duration,
        isCreate: false,
      });
    });
  });

  // Teilschritt bearbeiten öffnen
  document.querySelectorAll(".btn-edit-step").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const d = btn.dataset;
      openEditModal({
        type: "step",
        id: d.stepId,
        projectId: d.projectId,
        title: "Teilschritt bearbeiten",
        name: d.name,
        startYear: d.startYear,
        startQ: d.startQ,
        duration: d.duration,
        isCreate: false,
      });
    });
  });

  // Neuen Teilschritt anlegen
  document.querySelectorAll(".btn-add-step").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const firstOpt = emStart.options[0] ? emStart.options[0].value.split("-").map(Number) : [new Date().getFullYear(), 1];
      openEditModal({
        type: "step",
        id: null,
        projectId: btn.dataset.projectId,
        title: "Teilschritt hinzufügen",
        name: "",
        startYear: firstOpt[0],
        startQ: firstOpt[1],
        duration: 1,
        isCreate: true,
      });
    });
  });

  editSave.addEventListener("click", async () => {
    if (!editContext) return;
    const name = emName.value.trim();
    const [year, q] = emStart.value.split("-").map(Number);
    const duration = parseInt(emDuration.value, 10);
    if (!name || !duration) return;

    const payload = { name, start_year: year, start_q: q, duration };
    let url, method;

    if (editContext.type === "project") {
      url = `/api/projects/${editContext.id}`;
      method = "PATCH";
    } else if (editContext.isCreate) {
      url = `/api/projects/${editContext.projectId}/steps`;
      method = "POST";
    } else {
      url = `/api/steps/${editContext.id}`;
      method = "PATCH";
    }

    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      location.reload();
    } else {
      alert("Speichern fehlgeschlagen.");
    }
  });

  editDelete.addEventListener("click", async () => {
    if (!editContext) return;
    const isProject = editContext.type === "project";
    const msg = isProject
      ? "Dieses Projekt inkl. aller Teilschritte und Manntage-Einträge wirklich löschen?"
      : "Diesen Teilschritt wirklich löschen?";
    if (!confirm(msg)) return;
    const url = isProject ? `/api/projects/${editContext.id}` : `/api/steps/${editContext.id}`;
    const res = await fetch(url, { method: "DELETE" });
    if (res.ok) {
      location.reload();
    } else {
      alert("Löschen fehlgeschlagen.");
    }
  });

  // ---------------- Modal: Einstellungen (Mitarbeiter + max. Tage/Quartal) ----------------
  const btnSettings = document.getElementById("btn-settings");
  const settingsOverlay = document.getElementById("settings-modal-overlay");
  const settingsClose = document.getElementById("settings-modal-close");
  const settingsDone = document.getElementById("settings-modal-done");
  const settingsList = document.getElementById("settings-member-list");
  const settingsNewName = document.getElementById("settings-new-member-name");
  const settingsNewMaxTage = document.getElementById("settings-new-member-maxtage");
  const settingsAddBtn = document.getElementById("settings-add-member-btn");

  function openSettings() {
    settingsOverlay.classList.remove("hidden");
  }
  function closeSettings() {
    settingsOverlay.classList.add("hidden");
  }

  btnSettings.addEventListener("click", openSettings);
  settingsClose.addEventListener("click", closeSettings);
  settingsDone.addEventListener("click", closeSettings);
  settingsOverlay.addEventListener("click", (e) => {
    if (e.target === settingsOverlay) closeSettings();
  });

  settingsAddBtn.addEventListener("click", async () => {
    const name = settingsNewName.value.trim();
    if (!name) return;
    const maxRaw = settingsNewMaxTage.value;
    const max_tage_quarter = maxRaw === "" ? null : parseFloat(maxRaw);
    const res = await fetch("/api/members", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, max_tage_quarter }),
    });
    if (res.ok) {
      location.reload();
    } else {
      const data = await res.json().catch(() => ({}));
      alert(data.error || "Mitarbeiter konnte nicht hinzugefügt werden.");
    }
  });
  settingsNewName.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      settingsAddBtn.click();
    }
  });

  // Max. Tage/Quartal je Mitarbeiter speichern, sobald das Feld verlassen wird
  settingsList.querySelectorAll(".settings-max-tage-input").forEach((input) => {
    input.addEventListener("change", async () => {
      const memberId = input.dataset.memberId;
      const raw = input.value;
      const max_tage_quarter = raw === "" ? null : parseFloat(raw);
      const res = await fetch(`/api/members/${memberId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_tage_quarter }),
      });
      if (!res.ok) {
        alert("Speichern fehlgeschlagen.");
      }
    });
  });

  settingsList.querySelectorAll(".btn-delete-member").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const memberId = btn.dataset.memberId;
      if (!confirm("Diesen Mitarbeiter inkl. aller zugehörigen Manntage-Einträge wirklich entfernen?")) return;
      const res = await fetch(`/api/members/${memberId}`, { method: "DELETE" });
      if (res.ok) {
        location.reload();
      } else {
        alert("Entfernen fehlgeschlagen.");
      }
    });
  });
});
