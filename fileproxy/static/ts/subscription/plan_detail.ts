import { getCsrfToken } from "../utils/cookies.js";
import { qs, setFlash } from "../utils/dom.js";

type Plan = {
  id: string;
  name: string;
  is_default: boolean;
  enumerate_limit: number | null;
  read_limit: number | null;
  write_limit: number | null;
  delete_limit: number | null;
  read_transfer_limit_bytes: number | null;
  write_transfer_limit_bytes: number | null;
  expires_at: string | null;
};

type Subscriber = {
  id: string;
  username: string;
  email: string;
  status: string;
  cycle_ends_at: string;
};

declare const PLAN_ID: string;

function esc(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function fmtLimit(val: number | null): string {
  return val === null ? "Unlimited" : String(val);
}

function fmtDate(val: string | null): string {
  if (!val) return "—";
  const d = new Date(val);
  return isNaN(d.getTime()) ? val : d.toLocaleString();
}

async function loadPlanDetail(): Promise<void> {
  const infoEl = qs<HTMLElement>("#plan-info");
  const tbody = qs<HTMLTableSectionElement>("#subscribers-rows");
  if (!infoEl || !tbody) return;

  try {
    const [planResp, subsResp] = await Promise.all([
      fetch(`/api/v1/subscription/plans/${PLAN_ID}/`, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      }),
      fetch(`/api/v1/subscription/plans/${PLAN_ID}/subscribers/`, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      }),
    ]);

    if (!planResp.ok) {
      setFlash(`Failed to load plan (${planResp.status}).`, "error");
      return;
    }

    const plan = (await planResp.json()) as Plan;

    // Render plan info
    infoEl.innerHTML = `
      <div class="d-flex align-items-center justify-content-between mb-3">
        <h6 class="mb-0 fw-semibold">${esc(plan.name)}</h6>
        <div class="d-flex gap-2">
          ${plan.is_default ? '<span class="badge bg-success">Default</span>' : ""}
          ${plan.expires_at ? '<span class="badge bg-warning text-dark">Expiring</span>' : ""}
        </div>
      </div>
      <div class="row g-2 small">
        <div class="col-sm-6"><span class="text-secondary">Enumerate limit:</span> ${fmtLimit(plan.enumerate_limit)}</div>
        <div class="col-sm-6"><span class="text-secondary">Read limit:</span> ${fmtLimit(plan.read_limit)}</div>
        <div class="col-sm-6"><span class="text-secondary">Write limit:</span> ${fmtLimit(plan.write_limit)}</div>
        <div class="col-sm-6"><span class="text-secondary">Delete limit:</span> ${fmtLimit(plan.delete_limit)}</div>
        <div class="col-sm-6"><span class="text-secondary">Read transfer limit:</span> ${fmtLimit(plan.read_transfer_limit_bytes)}</div>
        <div class="col-sm-6"><span class="text-secondary">Write transfer limit:</span> ${fmtLimit(plan.write_transfer_limit_bytes)}</div>
      </div>
      <div class="mt-3 d-flex gap-2">
        ${!plan.is_default ? `<button id="set-default-btn" class="btn btn-sm btn-outline-secondary">Set as Default</button>` : ""}
        <button id="delete-btn" class="btn btn-sm btn-outline-danger">Delete Plan</button>
      </div>
    `;

    const setDefaultBtn = qs<HTMLButtonElement>("#set-default-btn");
    setDefaultBtn?.addEventListener("click", async () => {
      try {
        setDefaultBtn.disabled = true;
        const csrf = getCsrfToken();
        const resp = await fetch(`/api/v1/subscription/plans/${PLAN_ID}/set-default/`, {
          method: "POST",
          headers: { Accept: "application/json", ...(csrf ? { "X-CSRFToken": csrf } : {}) },
          credentials: "same-origin",
        });
        if (!resp.ok) throw new Error(`Set default failed (${resp.status})`);
        setFlash("Default plan updated.", "info");
        await loadPlanDetail();
      } catch (err) {
        setFlash(String(err), "error");
        setDefaultBtn.disabled = false;
      }
    });

    const deleteBtn = qs<HTMLButtonElement>("#delete-btn");
    deleteBtn?.addEventListener("click", async () => {
      if (!confirm(`Delete plan "${plan.name}"?`)) return;
      try {
        deleteBtn.disabled = true;
        const csrf = getCsrfToken();
        const resp = await fetch(`/api/v1/subscription/plans/${PLAN_ID}/`, {
          method: "DELETE",
          headers: { Accept: "application/json", ...(csrf ? { "X-CSRFToken": csrf } : {}) },
          credentials: "same-origin",
        });
        if (!resp.ok) throw new Error(`Delete failed (${resp.status})`);
        setFlash("Plan deleted.", "info");
        setTimeout(() => { window.location.href = "/subscription/plans/"; }, 1000);
      } catch (err) {
        setFlash(String(err), "error");
        deleteBtn.disabled = false;
      }
    });

    // Render subscribers
    if (!subsResp.ok) {
      tbody.innerHTML = `<tr><td colspan="4" class="text-secondary">Failed to load subscribers.</td></tr>`;
      return;
    }

    const subs = (await subsResp.json()) as Subscriber[] | { results: Subscriber[] };
    const subList = Array.isArray(subs) ? subs : (subs as { results: Subscriber[] }).results ?? [];

    tbody.innerHTML = "";
    if (!subList.length) {
      tbody.innerHTML = `<tr><td colspan="4" class="text-secondary">No subscribers.</td></tr>`;
      return;
    }

    for (const sub of subList) {
      const tr = document.createElement("tr");

      const tdUsername = document.createElement("td");
      tdUsername.textContent = sub.username;
      tr.appendChild(tdUsername);

      const tdEmail = document.createElement("td");
      tdEmail.textContent = sub.email;
      tr.appendChild(tdEmail);

      const tdStatus = document.createElement("td");
      const statusSpan = document.createElement("span");
      statusSpan.className = "badge " + (sub.status === "active" ? "bg-success" : "bg-secondary");
      statusSpan.textContent = sub.status;
      tdStatus.appendChild(statusSpan);
      tr.appendChild(tdStatus);

      const tdCycleEndsAt = document.createElement("td");
      tdCycleEndsAt.textContent = fmtDate(sub.cycle_ends_at);
      tr.appendChild(tdCycleEndsAt);

      tbody.appendChild(tr);
    }
  } catch (err) {
    setFlash(`Error: ${String(err)}`, "error");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  void loadPlanDetail();
});
