// ReceiptDesk front end. All dynamic content is inserted with textContent, never innerHTML.
"use strict";

const $ = (s, r = document) => r.querySelector(s);

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null) el.append(kid);
  return el;
}

function toast(msg) {
  const t = h("div", { class: "toast" }, msg);
  $("#toasts").append(t);
  setTimeout(() => t.remove(), 4000);
}

// Money arrives as exact decimal strings. Format by string manipulation, never via floats.
function fmtMoney(s) {
  if (s == null || s === "") return "";
  const [i, f] = String(s).split(".");
  const sign = i.startsWith("-") ? "-" : "";
  const digits = i.replace("-", "").replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return sign + digits + (f ? "." + f : "");
}

async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw { message: "Could not reach the ReceiptDesk server.", details: [] };
  }
  if (res.status === 204) return null;
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    const e = (body && body.error) || {};
    throw { message: e.message || `Request failed (${res.status}).`, details: e.details || [], code: e.code };
  }
  return body;
}

function showError(el, err) {
  el.replaceChildren(h("strong", {}, err.message), err.details?.length ? h("ul", {}, err.details.map(d => h("li", {}, d))) : null);
  el.hidden = false;
}

function confirmDialog(title, body, okLabel = "Delete") {
  const d = $("#confirm-dialog");
  $("#confirm-title").textContent = title;
  $("#confirm-body").textContent = body;
  $("#confirm-ok").textContent = okLabel;
  return new Promise(resolve => {
    d.addEventListener("close", () => resolve(d.returnValue === "ok"), { once: true });
    d.returnValue = "cancel";
    d.showModal();
  });
}

function expenseRow(e, { select = false, actions = false, onChange } = {}) {
  const cells = [];
  if (select) cells.push(h("td", {}, h("input", { type: "checkbox", "data-id": e.id, "aria-label": `Select ${e.supplier}`, onchange: onChange })));
  cells.push(
    h("td", {}, e.invoice_date || "–"),
    h("td", { class: "wrap-cell" }, e.supplier),
    h("td", {}, e.invoice_number || "–"),
    h("td", {}, e.currency || "–"),
    h("td", { class: "num" }, fmtMoney(e.total)),
    h("td", {}, e.category || "–"),
  );
  if (actions) cells.push(h("td", {}, h("div", { class: "row" },
    h("a", { class: "btn sm", href: `/extract?edit=${encodeURIComponent(e.id)}` }, "Edit"),
    h("button", { class: "btn sm", type: "button", "data-delete": e.id, "aria-label": `Delete ${e.supplier}` }, "Delete"))));
  return h("tr", {}, cells);
}

function expenseTable(items, opts = {}) {
  const head = [opts.select ? h("th", { scope: "col" }, h("span", { class: "sr" }, "")) : null,
    ...["Date", "Supplier", "Invoice #", "Currency"].map(t => h("th", { scope: "col" }, t)),
    h("th", { scope: "col", class: "num" }, "Total"), h("th", { scope: "col" }, "Category"),
    opts.actions ? h("th", { scope: "col" }, "Actions") : null];
  return h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, head)), h("tbody", {}, items.map(e => expenseRow(e, opts)))));
}

function emptyState(filtered) {
  return h("div", { class: "empty" },
    h("h3", {}, filtered ? "No expenses match your filters" : "No expenses yet"),
    h("p", { class: "muted" }, filtered ? "Try a different search or clear the filters."
      : "Extract your first invoice to start building your expense list."),
    filtered ? null : h("a", { class: "btn primary", href: "/extract" }, "Extract invoice"));
}

// ---------------- Dashboard ----------------
async function initDashboard() {
  try {
    const [sum, list] = await Promise.all([api("/api/expenses/summary"), api("/api/expenses?page_size=5")]);
    $("#sum-count").textContent = sum.count;
    $("#sum-currency").textContent = sum.most_used_currency || "–";
    const totals = $("#sum-totals");
    const entries = Object.entries(sum.totals_by_currency);
    totals.replaceChildren(...(entries.length
      ? entries.map(([c, v]) => h("p", {}, h("span", {}, c === "UNSPECIFIED" ? "No currency" : c), fmtMoney(v)))
      : [h("p", { class: "muted" }, "–")]));
    $("#recent").replaceChildren(list.items.length ? expenseTable(list.items) : emptyState(false));
  } catch (err) {
    const box = h("div", { class: "alert error", role: "alert" });
    showError(box, err);
    $("#recent").replaceChildren(box);
  }
}

// ---------------- Extract / review ----------------
function initExtract() {
  const FIELDS = ["supplier", "invoice_number", "invoice_date", "currency", "subtotal", "tax", "total", "category", "notes"];
  const tabs = { text: [$("#tab-text"), $("#pane-text")], file: [$("#tab-file"), $("#pane-file")] };
  let mode = "text", file = null, sourceType = "text", editingId = null;

  function setMode(m) {
    mode = m;
    for (const [k, [tab, pane]] of Object.entries(tabs)) {
      tab.setAttribute("aria-selected", k === m); tab.tabIndex = k === m ? 0 : -1; pane.hidden = k !== m;
    }
  }
  for (const [k, [tab]] of Object.entries(tabs)) {
    tab.addEventListener("click", () => setMode(k));
    tab.addEventListener("keydown", e => {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") { const o = k === "text" ? "file" : "text"; setMode(o); tabs[o][0].focus(); }
    });
  }

  const drop = $("#drop"), input = $("#file-input");
  function setFile(f) { file = f; $("#file-name").textContent = f ? `Selected: ${f.name}` : ""; }
  input.addEventListener("change", () => setFile(input.files[0] || null));
  drop.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  ["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", e => { if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); });

  function fillForm(fields) {
    for (const f of FIELDS) $(`#f-${f}`).value = fields[f] ?? "";
  }
  function showReview(title) {
    $("#review-title").textContent = title;
    $("#review-panel").hidden = false;
    $("#form-error").hidden = true;
    $("#review-panel").scrollIntoView({ behavior: "smooth", block: "start" });
    $("#f-supplier").focus({ preventScroll: true });
  }
  function reset() {
    $("#review-panel").hidden = true; $("#input-panel").hidden = false;
    $("#expense-form").reset(); setFile(null); input.value = ""; $("#input-error").hidden = true; $("#status").textContent = "";
    editingId = null;
    if (location.search) history.replaceState(null, "", "/extract");
    $("#page-title").textContent = "Extract invoice";
  }

  $("#extract-btn").addEventListener("click", async () => {
    const err = $("#input-error"); err.hidden = true;
    let req;
    if (mode === "text") {
      const text = $("#invoice-text").value.trim();
      if (!text) return showError(err, { message: "Paste some invoice text first.", details: [] });
      req = ["/api/extract/text", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) }];
    } else {
      if (!file) return showError(err, { message: "Choose a PDF, PNG or JPG file first.", details: [] });
      const fd = new FormData(); fd.append("file", file);
      req = ["/api/extract/file", { method: "POST", body: fd }];
    }
    const btn = $("#extract-btn"); btn.disabled = true;
    $("#status").replaceChildren(h("span", { class: "spinner" }), "Reading the document with Gemma. This can take a minute on a laptop…");
    try {
      const r = await api(...req);
      sourceType = r.source_type;
      fillForm(r.fields);
      $("#source-badge").textContent = { text: "Pasted text", pdf: "PDF", image: "Image" }[r.source_type] + " · " + r.model;
      const wl = $("#warning-list"); wl.replaceChildren(...r.warnings.map(w => h("li", {}, w)));
      $("#warnings").hidden = r.warnings.length === 0;
      const det = $("#ocr-details");
      det.hidden = !r.text_preview; $("#ocr-text").textContent = r.text_preview || "";
      showReview("Review and confirm");
    } catch (e) {
      showError(err, e);
    } finally {
      btn.disabled = false; $("#status").textContent = "";
    }
  });

  $("#cancel-btn").addEventListener("click", () => {
    if (editingId) location.href = "/expenses"; else reset();
  });

  $("#expense-form").addEventListener("submit", async ev => {
    ev.preventDefault();
    const body = Object.fromEntries(FIELDS.map(f => [f, $(`#f-${f}`).value.trim()]));
    body.source_type = sourceType;
    const btn = $("#save-btn"); btn.disabled = true;
    try {
      await api(editingId ? `/api/expenses/${editingId}` : "/api/expenses", {
        method: editingId ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      sessionStorage.setItem("flash", editingId ? "Expense updated." : "Expense saved.");
      location.href = "/expenses";
    } catch (e) {
      showError($("#form-error"), e);
      btn.disabled = false;
    }
  });

  const editId = new URLSearchParams(location.search).get("edit");
  if (editId) {
    editingId = editId;
    $("#page-title").textContent = "Edit expense";
    $("#input-panel").hidden = true;
    api(`/api/expenses/${encodeURIComponent(editId)}`).then(e => {
      sourceType = e.source_type; fillForm(e);
      $("#source-badge").textContent = "Saved record";
      showReview("Edit expense");
      $("#save-btn").textContent = "Save changes";
    }).catch(e => { $("#input-panel").hidden = false; showError($("#input-error"), e); });
  }
}

// ---------------- Expenses list ----------------
function initExpenses() {
  const state = { page: 1, pageSize: 20 };
  const selected = new Set();
  const flash = sessionStorage.getItem("flash");
  if (flash) { toast(flash); sessionStorage.removeItem("flash"); }

  function params(extra = {}) {
    const p = new URLSearchParams();
    const q = $("#q").value.trim(), cur = $("#currency").value, f = $("#date_from").value, t = $("#date_to").value;
    if (q) p.set("q", q); if (cur) p.set("currency", cur); if (f) p.set("date_from", f); if (t) p.set("date_to", t);
    for (const [k, v] of Object.entries(extra)) p.set(k, v);
    return p;
  }
  const filtersActive = () => params().size > 0;

  async function load() {
    const [sort, order] = $("#sort").value.split(":");
    try {
      const r = await api("/api/expenses?" + params({ sort, order, page: state.page, page_size: state.pageSize }));
      $("#export-all").href = "/api/expenses/export.csv" + (params().size ? "?" + params() : "");
      const totals = Object.entries(r.totals_by_currency).map(([c, v]) => `${c === "UNSPECIFIED" ? "no currency" : c} ${fmtMoney(v)}`).join(" · ");
      $("#result-count").textContent = r.total_count ? `${r.total_count} record${r.total_count === 1 ? "" : "s"} · ${totals}` : "";
      $("#table-area").replaceChildren(r.items.length ? expenseTable(r.items, { select: true, actions: true, onChange: onSelect }) : emptyState(filtersActive()));
      for (const cb of document.querySelectorAll("[data-id]")) cb.checked = selected.has(cb.dataset.id);
      const pages = Math.max(1, Math.ceil(r.total_count / r.page_size));
      $("#pager").hidden = pages <= 1;
      $("#page-info").textContent = `Page ${r.page} of ${pages}`;
      $("#prev").disabled = r.page <= 1; $("#next").disabled = r.page >= pages;
    } catch (e) {
      const box = h("div", { class: "alert error", role: "alert" }); showError(box, e);
      $("#table-area").replaceChildren(box);
    }
  }

  function onSelect(ev) {
    ev.target.checked ? selected.add(ev.target.dataset.id) : selected.delete(ev.target.dataset.id);
    $("#export-selected").disabled = selected.size === 0;
    $("#export-selected").textContent = selected.size ? `Export selected (${selected.size})` : "Export selected";
  }
  $("#export-selected").addEventListener("click", () => {
    location.href = "/api/expenses/export.csv?ids=" + encodeURIComponent([...selected].join(","));
  });

  // Populate currency filter from existing data.
  api("/api/expenses/summary").then(s => {
    for (const c of Object.keys(s.counts_by_currency).filter(c => c !== "UNSPECIFIED").sort())
      $("#currency").append(h("option", { value: c }, c));
  }).catch(() => {});

  let timer;
  $("#filters").addEventListener("submit", e => e.preventDefault());
  $("#filters").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { state.page = 1; load(); }, 250); });
  $("#prev").addEventListener("click", () => { state.page--; load(); });
  $("#next").addEventListener("click", () => { state.page++; load(); });

  $("#table-area").addEventListener("click", async ev => {
    const btn = ev.target.closest("[data-delete]");
    if (!btn) return;
    if (!await confirmDialog("Delete this expense?", "This permanently removes the record from your local database.")) return;
    try { await api(`/api/expenses/${encodeURIComponent(btn.dataset.delete)}`, { method: "DELETE" }); selected.delete(btn.dataset.delete); toast("Expense deleted."); load(); }
    catch (e) { toast(e.message); }
  });
  load();
}

const page = document.body.dataset.page;
({ dashboard: initDashboard, extract: initExtract, expenses: initExpenses })[page]?.();
