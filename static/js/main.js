/* ==========================================================================
   CEMS — AGC Campus Event Management System
   Progressive-enhancement JavaScript. Every control below is wired to a real
   element rendered by a template - there are no decorative buttons.
   ========================================================================== */
(function () {
  "use strict";

  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));

  /* ---------------------------------------------------------- sidebar ---- */
  function initSidebar() {
    const overlay = $(".sidebar-overlay");
    const body = document.body;

    $$("[data-sidebar-toggle]").forEach((toggle) => {
      toggle.addEventListener("click", () => {
        const open = !body.classList.contains("sidebar-open");
        body.classList.toggle("sidebar-open", open);
        if (overlay) overlay.hidden = !open;
      });
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && body.classList.contains("sidebar-open")) {
        body.classList.remove("sidebar-open");
        if (overlay) overlay.hidden = true;
      }
    });

    window.addEventListener("resize", () => {
      if (window.innerWidth > 1024 && body.classList.contains("sidebar-open")) {
        body.classList.remove("sidebar-open");
        if (overlay) overlay.hidden = true;
      }
    });
  }

  /* ------------------------------------------------------- flash msgs ---- */
  function initFlash() {
    $$("[data-flash-close]").forEach((button) => {
      button.addEventListener("click", () => {
        const alert = button.closest("[data-flash]");
        if (alert) alert.remove();
      });
    });

    const stack = $("#flash-stack");
    if (!stack) return;
    const alerts = $$("[data-flash]", stack);
    if (alerts.length < 2) return;
    alerts.forEach((alert, index) => {
      if (index > 2) return;
      window.setTimeout(function () { alert.remove(); }, 8000 + index * 1500);
    });
  }

  /* ------------------------------------------------- confirm on submit --- */
  function initConfirmations() {
    document.addEventListener("submit", function (event) {
      const form = event.target;
      const message = form.getAttribute("data-confirm");
      if (!message) return;
      if (!window.confirm(message)) {
        event.preventDefault();
        event.stopPropagation();
      }
    });
  }

  /* ------------------------------------------------ password visibility --- */
  function initPasswordToggles() {
    $$("[data-toggle-password]").forEach((button) => {
      button.addEventListener("click", () => {
        const selector = button.getAttribute("data-toggle-password");
        const input = $(selector);
        if (!input) return;
        const showing = input.type === "text";
        input.type = showing ? "password" : "text";
        button.setAttribute("aria-label", showing ? "Show password" : "Hide password");
        button.setAttribute("title", showing ? "Show password" : "Hide password");
      });
    });
  }

  /* ----------------------------------------------------- layout toggle --- */
  function initViewToggles() {
    $$("[data-view-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const mode = button.getAttribute("data-view-toggle");
        const target = $(button.getAttribute("data-view-target"));
        if (!target) return;
        $$("[data-view-toggle]").forEach((other) => {
          other.setAttribute("aria-pressed", String(other === button));
        });
        target.setAttribute("data-view", mode);
      });
    });
  }

  /* ----------------------------------------------------------- modals ---- */
  function initModals() {
    function openModal(modal) {
      if (!modal) return;
      modal.hidden = false;
      document.body.style.overflow = "hidden";
      const focusable = modal.querySelector("input, button, select, textarea, a[href]");
      if (focusable) focusable.focus();
    }
    function closeModal(modal) {
      if (!modal) return;
      modal.hidden = true;
      document.body.style.overflow = "";
    }

    $$("[data-modal-open]").forEach((trigger) => {
      trigger.addEventListener("click", function () {
        openModal($("#" + trigger.getAttribute("data-modal-open")));
      });
    });
    $$("[data-modal-close]").forEach((trigger) => {
      trigger.addEventListener("click", function () {
        closeModal(trigger.closest(".modal"));
      });
    });
    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      $$(".modal").forEach(function (modal) {
        if (!modal.hidden) closeModal(modal);
      });
    });
  }

  /* ------------------------------------------------- attendance sheets --- */
  function initAttendanceSheets() {
    const form = $("#attendance-form");
    if (!form) return;

    $$("[data-check-all]", form).forEach((master) => {
      master.addEventListener("change", function () {
        const checked = master.checked;
        $$("[data-mark-toggle]", form).forEach((box) { box.checked = checked; });
      });
    });

    function syncMaster() {
      const rows = $$("[data-mark-toggle]", form);
      const checked = rows.filter((box) => box.checked).length;
      $$("[data-check-all]", form).forEach((master) => {
        master.checked = rows.length > 0 && checked === rows.length;
        master.indeterminate = checked > 0 && checked < rows.length;
      });
    }

    $$("[data-mark-toggle]", form).forEach((box) => {
      box.addEventListener("change", function () {
        syncMaster();
        const row = box.closest("tr");
        const badge = row ? row.querySelector(".badge") : null;
        if (!badge) return;
        badge.textContent = box.checked ? "Present" : "Absent";
        badge.classList.toggle("badge-success", box.checked);
        badge.classList.toggle("badge-danger", !box.checked);
      });
    });
    syncMaster();

    $$("[data-select-all]", form).forEach((button) => {
      button.addEventListener("click", function () {
        const mode = button.getAttribute("data-select-all");
        $$("[data-mark-toggle]", form).forEach((box) => {
          box.checked = mode === "present";
        });
        syncMaster();
      });
    });

    form.addEventListener("submit", function (event) {
      if (event.submitter && event.submitter.getAttribute("name") === "scope") return;
      const any = $$("[data-mark-toggle]", form).some((box) => box.checked);
      if (!any) {
        if (!window.confirm("No participant is ticked. Everyone will be marked Absent. Continue?")) {
          event.preventDefault();
        }
      }
    });
  }

  /* ------------------------------------------------------ star ratings --- */
  function initStarInputs() {
    $$("[data-star-form]").forEach((form) => {
      const inputs = $$("input[name='rating']", form);
      if (!inputs.length) return;
      const legend = form.querySelector("legend");
      inputs.forEach(function (input) {
        input.addEventListener("change", function () {
          const value = parseInt(input.value, 10);
          if (!legend) return;
          if (!legend.dataset.original) legend.dataset.original = legend.textContent.trim();
          legend.textContent = legend.dataset.original + " (" + value + "/5)";
        });
      });
    });
  }

  /* --------------------------------------------------- image preview ----- */
  function initImagePreview() {
    $$("[data-preview-input]").forEach((input) => {
      const target = $("[data-preview-target]");
      input.addEventListener("change", function () {
        if (!target) return;
        target.innerHTML = "";
        target.hidden = true;
        const file = input.files && input.files[0];
        if (!file) return;
        if (file.size > 4 * 1024 * 1024) {
          window.alert("The selected image is larger than 4 MB. Please choose a smaller file.");
          input.value = "";
          return;
        }
        const image = document.createElement("img");
        image.alt = "Selected event image preview";
        image.src = URL.createObjectURL(file);
        image.addEventListener("load", function () { URL.revokeObjectURL(image.src); }, { once: true });
        target.appendChild(image);
        target.hidden = false;
      });
    });
  }

  /* ------------------------------------------------------ dev mailbox ---- */
  function initDevMail() {
    const tray = $("[data-devmail]");
    if (!tray) return;
    const toggle = $("[data-devmail-toggle]", tray);
    const body = $(".devmail-tray__body", tray);
    if (!toggle || !body) return;
    toggle.addEventListener("click", function () {
      body.hidden = !body.hidden;
    });
  }

  /* ------------------------------------------------ date range guard ----- */
  function initDateRangeGuard() {
    $$("form").forEach((form) => {
      const from = $("input[name='date_from']", form);
      const to = $("input[name='date_to']", form);
      if (!from || !to) return;
      from.addEventListener("change", function () {
        if (from.value && to.value && from.value > to.value) to.value = from.value;
      });
      to.addEventListener("change", function () {
        if (from.value && to.value && to.value < from.value) from.value = to.value;
      });
    });
  }

  /* -------------------------------------------- end time auto-fix ------- */
  function initEventTimeGuard() {
    const form = $("#event-form");
    if (!form) return;
    const start = $("input[name='start_time']", form);
    const end = $("input[name='end_time']", form);
    if (!start || !end) return;
    start.addEventListener("change", function () {
      if (start.value && (!end.value || end.value <= start.value)) {
        const [h, m] = start.value.split(":").map(Number);
        const total = h * 60 + m + 90;
        end.value = String(Math.floor(total / 60) % 24).padStart(2, "0") + ":" +
                    String(total % 60).padStart(2, "0");
      }
    });
  }

  /* ------------------------------------------------------- boot ---------- */
  document.addEventListener("DOMContentLoaded", function () {
    initSidebar();
    initFlash();
    initConfirmations();
    initPasswordToggles();
    initViewToggles();
    initModals();
    initAttendanceSheets();
    initStarInputs();
    initImagePreview();
    initDevMail();
    initDateRangeGuard();
    initEventTimeGuard();
  });
})();