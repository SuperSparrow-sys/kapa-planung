(() => {
  const $ = (sel, ctx) => (ctx || document).querySelector(sel);
  const $$ = (sel, ctx) => [...(ctx || document).querySelectorAll(sel)];

  // -----------------------------------------------------------------------
  // Toast
  // -----------------------------------------------------------------------
  const toastContainer = document.getElementById("toast-container");
  let toastTimer = 0;

  function showToast(message, type = "success") {
    const el = document.createElement("div");
    el.className = "toast toast-" + type;
    el.textContent = message;
    toastContainer.appendChild(el);
    setTimeout(() => el.remove(), 3200);
  }

  // -----------------------------------------------------------------------
  // Scroll-Positionen
  // -----------------------------------------------------------------------
  function saveScrollPositions() {
    const gantt = document.getElementById("gantt-scroll");
    return {
      ganttLeft: gantt?.scrollLeft || 0,
      ganttTop: gantt?.scrollTop || 0,
    };
  }

  function restoreScrollPositions(pos) {
    const gantt = document.getElementById("gantt-scroll");
    if (gantt) { gantt.scrollLeft = pos.ganttLeft; gantt.scrollTop = pos.ganttTop; }
  }

  // -----------------------------------------------------------------------
  // App-daten aus JSON-Script-Tag lesen + aktualisieren
  // -----------------------------------------------------------------------
  function getAppData() {
    const el = document.getElementById("app-data");
    return el ? JSON.parse(el.textContent) : {};
  }

  function updateAppData(partial) {
    const el = document.getElementById("app-data");
    if (el) {
      const data = {
        quarter_options: partial.quarter_options,
        members: partial.members,
        member_defaults: partial.member_defaults,
      };
      el.textContent = JSON.stringify(data);
    }
  }

  // -----------------------------------------------------------------------
  // Seite partiell aktualisieren (kein location.reload)
  // -----------------------------------------------------------------------
  async function refreshPage(successMsg) {
    const positions = saveScrollPositions();
    try {
      const res = await fetch("/_partial");
      if (!res.ok) throw new Error("Partial fetch failed");
      const partial = await res.json();

      const sidebar = document.querySelector(".sidebar");
      const ganttWrap = document.getElementById("gantt-scroll");

      if (sidebar) sidebar.innerHTML = partial.sidebar;
      if (ganttWrap) ganttWrap.outerHTML = partial.gantt;

      updateAppData(partial);
      restoreScrollPositions(positions);
      attachAllEventListeners();
      refreshHistoryButtons();
      if (window.lucide) lucide.createIcons();

      if (successMsg) showToast(successMsg, "success");
    } catch (e) {
      console.error("refreshPage failed", e);
      showToast("Aktualisierung fehlgeschlagen", "error");
    }
  }

  // -----------------------------------------------------------------------
  // API-Helfer
  // -----------------------------------------------------------------------
  async function apiFetch(url, options, okMsg) {
    try {
      const res = await fetch(url, options);
      if (res.ok) {
        await refreshPage(okMsg);
        return { ok: true };
      }
      const data = await res.json().catch(() => ({}));
      showToast(data.error || "Fehler aufgetreten", "error");
      return { ok: false, error: data.error };
    } catch (e) {
      console.error(e);
      showToast("Netzwerkfehler", "error");
      return { ok: false };
    }
  }

  // -----------------------------------------------------------------------
  // Event-Listener (zentral, nach jedem Refresh neu gebunden)
  // -----------------------------------------------------------------------
  let currentContext = null;
  let editContext = null;

  function attachAllEventListeners() {
    attachNewProjectForm();
    attachExpandToggles();
    attachProjectDeleteButtons();
    attachStepDeleteButtons();
    attachBarSegments();
    attachEditButtons();
    attachAddStepButtons();
    attachTodayButton();
    attachAllocationModal();
    attachEditModal();
    attachSettingsModal();
  }

  // -- Neues Projekt --
  function attachNewProjectForm() {
    const btnNew = document.getElementById("btn-new-project");
    const formNew = document.getElementById("form-new-project");
    const btnCancel = document.getElementById("np-cancel");
    if (!btnNew || !formNew) return;

    const toggle = () => formNew.classList.toggle("hidden");

    btnNew.onclick = toggle;
    if (btnCancel) {
      btnCancel.onclick = () => { formNew.classList.add("hidden"); formNew.reset(); };
    }

    formNew.onsubmit = async (e) => {
      e.preventDefault();
      const name = document.getElementById("np-name").value.trim();
      const [year, q] = document.getElementById("np-start").value.split("-").map(Number);
      const duration = parseInt(document.getElementById("np-duration").value, 10);
      if (!name || !duration) return;
      await apiFetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, start_year: year, start_q: q, duration }),
      }, "Projekt angelegt");
    };
  }

  // -- Ein-/Ausklappen --
  function attachExpandToggles() {
    $$(".expand-toggle").forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const block = btn.closest(".project-block");
        if (!block) return;
        const list = block.querySelector(".steps-list");
        btn.classList.toggle("is-open");
        if (list) list.classList.toggle("is-open");
      };
    });
  }

  // -- Projekt löschen --
  function attachProjectDeleteButtons() {
    $$(".btn-delete-project").forEach((btn) => {
      btn.onclick = async (e) => {
        e.stopPropagation();
        const item = btn.closest(".project-list-item");
        const projectId = item?.dataset.projectId;
        if (!projectId) return;
        if (!confirm("Dieses Projekt inkl. aller Teilschritte und Stunden-Einträge wirklich löschen?")) return;
        await apiFetch("/api/projects/" + projectId, { method: "DELETE" }, "Projekt gelöscht");
      };
    });
  }

  // -- Teilschritt löschen --
  function attachStepDeleteButtons() {
    $$(".btn-delete-step").forEach((btn) => {
      btn.onclick = async (e) => {
        e.stopPropagation();
        const stepId = btn.dataset.stepId;
        if (!stepId) return;
        if (!confirm("Diesen Teilschritt wirklich löschen?")) return;
        await apiFetch("/api/steps/" + stepId, { method: "DELETE" }, "Teilschritt gelöscht");
      };
    });
  }

  // -- Balkensegmente (Stunden-Modal öffnen) --
  function attachBarSegments() {
    $$(".bar-segment:not(.bar-segment-static)").forEach((seg) => {
      seg.onclick = () => openAllocationModal(seg);
    });
  }

  // -- Bearbeiten-Buttons --
  function attachEditButtons() {
    $$(".btn-edit-project").forEach((btn) => {
      btn.onclick = (e) => {
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
      };
    });

    $$(".btn-edit-step").forEach((btn) => {
      btn.onclick = (e) => {
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
      };
    });
  }

  // -- Teilschritt hinzufügen --
  function attachAddStepButtons() {
    $$(".btn-add-step").forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const sel = document.getElementById("em-start");
        const firstOpt = sel?.options[0]?.value?.split("-").map(Number) || [new Date().getFullYear(), 1];
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
      };
    });
  }

  // -- "Heute"-Button --
  function attachTodayButton() {
    const btn = document.getElementById("btn-today");
    if (!btn) return;
    btn.onclick = () => {
      const current = document.querySelector(".head-cell.is-current");
      if (current) current.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
    };
  }

  // -----------------------------------------------------------------------
  // Modal: Stunden
  // -----------------------------------------------------------------------
  function openAllocationModal(seg) {
    const projectId = seg.dataset.projectId;
    const projectName = seg.dataset.projectName;
    const label = seg.dataset.label;
    const year = seg.dataset.year;
    const q = seg.dataset.q;
    let alloc = [];
    try { alloc = JSON.parse(seg.dataset.alloc); } catch (_) { alloc = []; }

    currentContext = { projectId, year, q };

    const title = document.getElementById("modal-project-name");
    const subtitle = document.getElementById("modal-subtitle");
    if (title) title.textContent = projectName;
    if (subtitle) subtitle.textContent = "Quartal " + label;

    const body = document.getElementById("modal-body");
    if (!body) return;
    body.innerHTML = "";
    alloc.forEach((a) => {
      const row = document.createElement("div");
      row.className = "modal-field";
      row.innerHTML = `
        <label><svg class="icon-sm"><use href="#icon-person"/></svg>${a.member}</label>
        <span style="display:flex;align-items:center;gap:6px">
          <input type="number" min="0" step="0.5" value="${a.stunden}" data-member-id="${a.member_id}">
          <span class="modal-field-unit">h</span>
        </span>`;
      body.appendChild(row);
    });

    document.getElementById("modal-overlay").classList.remove("hidden");
  }

  function closeAllocationModal() {
    document.getElementById("modal-overlay").classList.add("hidden");
    currentContext = null;
  }

  function attachAllocationModal() {
    const overlay = document.getElementById("modal-overlay");
    if (!overlay) return;
    document.getElementById("modal-close").onclick = closeAllocationModal;
    document.getElementById("modal-cancel").onclick = closeAllocationModal;
    overlay.onclick = (e) => { if (e.target === overlay) closeAllocationModal(); };

    document.getElementById("modal-save").onclick = async () => {
      if (!currentContext) return;
      const values = {};
      $$("input[data-member-id]", document.getElementById("modal-body")).forEach((input) => {
        values[input.dataset.memberId] = parseFloat(input.value || "0");
      });
      await apiFetch("/api/allocations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: currentContext.projectId,
          year: currentContext.year,
          quarter: currentContext.q,
          values,
        }),
      }, "Stunden gespeichert");
    };
  }

  // -----------------------------------------------------------------------
  // Modal: Projekt / Teilschritt bearbeiten
  // -----------------------------------------------------------------------
  function openEditModal(opts) {
    editContext = opts;
    document.getElementById("edit-modal-title").textContent = opts.title;
    document.getElementById("em-name").value = opts.name || "";
    document.getElementById("em-start").value = opts.startYear + "-" + opts.startQ;
    document.getElementById("em-duration").value = opts.duration || 1;
    document.getElementById("edit-modal-delete").style.display = opts.isCreate ? "none" : "";
    document.getElementById("edit-modal-overlay").classList.remove("hidden");
    document.getElementById("em-name").focus();
  }

  function closeEditModal() {
    document.getElementById("edit-modal-overlay").classList.add("hidden");
    editContext = null;
  }

  function attachEditModal() {
    const overlay = document.getElementById("edit-modal-overlay");
    if (!overlay) return;
    document.getElementById("edit-modal-close").onclick = closeEditModal;
    document.getElementById("edit-modal-cancel").onclick = closeEditModal;
    overlay.onclick = (e) => { if (e.target === overlay) closeEditModal(); };

    document.getElementById("edit-modal-save").onclick = async () => {
      if (!editContext) return;
      const name = document.getElementById("em-name").value.trim();
      const [year, q] = document.getElementById("em-start").value.split("-").map(Number);
      const duration = parseInt(document.getElementById("em-duration").value, 10);
      if (!name || !duration) return;

      const payload = { name, start_year: year, start_q: q, duration };
      let url, method;

      if (editContext.type === "project") {
        url = "/api/projects/" + editContext.id;
        method = "PATCH";
      } else if (editContext.isCreate) {
        url = "/api/projects/" + editContext.projectId + "/steps";
        method = "POST";
      } else {
        url = "/api/steps/" + editContext.id;
        method = "PATCH";
      }

      const result = await apiFetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }, editContext.isCreate ? "Teilschritt angelegt" : "Gespeichert");

      if (result.ok) closeEditModal();
    };

    document.getElementById("edit-modal-delete").onclick = async () => {
      if (!editContext) return;
      const isProject = editContext.type === "project";
      const msg = isProject
        ? "Dieses Projekt inkl. aller Teilschritte und Stunden-Einträge wirklich löschen?"
        : "Diesen Teilschritt wirklich löschen?";
      if (!confirm(msg)) return;
      const url = isProject
        ? "/api/projects/" + editContext.id
        : "/api/steps/" + editContext.id;
      const result = await apiFetch(url, { method: "DELETE" },
        isProject ? "Projekt gelöscht" : "Teilschritt gelöscht");
      if (result.ok) closeEditModal();
    };
  }

  // -----------------------------------------------------------------------
  // Modal: Einstellungen
  // -----------------------------------------------------------------------
  function openSettings() {
    document.getElementById("settings-modal-overlay").classList.remove("hidden");
  }
  function closeSettings() {
    document.getElementById("settings-modal-overlay").classList.add("hidden");
  }

  function attachSettingsModal() {
    const overlay = document.getElementById("settings-modal-overlay");
    if (!overlay) return;

    document.getElementById("btn-settings").onclick = openSettings;
    document.getElementById("settings-modal-close").onclick = closeSettings;
    document.getElementById("settings-modal-done").onclick = closeSettings;
    overlay.onclick = (e) => { if (e.target === overlay) closeSettings(); };

    document.getElementById("settings-add-member-btn").onclick = async () => {
      const name = document.getElementById("settings-new-member-name").value.trim();
      if (!name) return;
      const maxRaw = document.getElementById("settings-new-member-maxstunden").value;
      const max_stunden_quarter = maxRaw === "" ? null : parseFloat(maxRaw);
      const result = await apiFetch("/api/members", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, max_stunden_quarter }),
      }, "Mitarbeiter hinzugefügt");
      if (result.ok) {
        document.getElementById("settings-new-member-name").value = "";
        document.getElementById("settings-new-member-maxstunden").value = "";
      }
    };

    document.getElementById("settings-new-member-name").onkeydown = (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        document.getElementById("settings-add-member-btn").click();
      }
    };

    $$(".settings-max-stunden-input").forEach((input) => {
      input.onchange = async () => {
        const memberId = input.dataset.memberId;
        const raw = input.value;
        const max_stunden_quarter = raw === "" ? null : parseFloat(raw);
        const res = await fetch("/api/members/" + memberId, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ max_stunden_quarter }),
        });
        if (res.ok) {
          showToast("Max. Stunden gespeichert", "success");
        } else {
          showToast("Speichern fehlgeschlagen", "error");
        }
      };
    });

    $$(".btn-delete-member").forEach((btn) => {
      btn.onclick = async () => {
        const memberId = btn.dataset.memberId;
        if (!confirm("Diesen Mitarbeiter inkl. aller zugehörigen Stunden-Einträge wirklich entfernen?")) return;
        await apiFetch("/api/members/" + memberId, { method: "DELETE" }, "Mitarbeiter entfernt");
      };
    });

    const btnBackup = document.getElementById("btn-backup-now");
    const backupStatus = document.getElementById("backup-status");
    if (btnBackup && backupStatus) {
      btnBackup.onclick = async () => {
        btnBackup.disabled = true;
        backupStatus.textContent = "Läuft...";
        try {
          const res = await fetch("/api/backup/run", { method: "POST" });
          const data = await res.json();
          backupStatus.textContent = data.message;
          showToast(data.message, data.success ? "success" : "error");
        } catch (e) {
          backupStatus.textContent = "Fehlgeschlagen";
          showToast("Backup fehlgeschlagen", "error");
        } finally {
          btnBackup.disabled = false;
        }
      };
    }
  }

  // -----------------------------------------------------------------------
  // Undo / Redo
  // -----------------------------------------------------------------------
  async function refreshHistoryButtons() {
    try {
      const res = await fetch("/api/history/status");
      const s = await res.json();
      const btnUndo = document.getElementById("btn-undo");
      const btnRedo = document.getElementById("btn-redo");
      if (btnUndo) {
        btnUndo.disabled = !s.can_undo;
        btnUndo.title = s.undo_description || "Rückgängig";
      }
      if (btnRedo) {
        btnRedo.disabled = !s.can_redo;
        btnRedo.title = s.redo_description || "Wiederherstellen";
      }
    } catch (_) {}
  }

  async function doUndo() {
    const res = await fetch("/api/undo", { method: "POST" });
    const data = await res.json();
    showToast(data.message, data.success ? "success" : "error");
    if (data.success) {
      await refreshPage();
      refreshHistoryButtons();
    }
  }

  async function doRedo() {
    const res = await fetch("/api/redo", { method: "POST" });
    const data = await res.json();
    showToast(data.message, data.success ? "success" : "error");
    if (data.success) {
      await refreshPage();
      refreshHistoryButtons();
    }
  }

  function attachUndoRedo() {
    const btnUndo = document.getElementById("btn-undo");
    const btnRedo = document.getElementById("btn-redo");
    if (btnUndo) btnUndo.onclick = doUndo;
    if (btnRedo) btnRedo.onclick = doRedo;
    refreshHistoryButtons();
  }

  // -----------------------------------------------------------------------
  // Init
  // -----------------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", () => {
    attachAllEventListeners();
    attachUndoRedo();
    if (window.lucide) lucide.createIcons();
  });
})();
