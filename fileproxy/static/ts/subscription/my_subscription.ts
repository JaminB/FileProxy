import { getCsrfToken } from '../utils/cookies.js';
import { qs, setFlash } from '../utils/dom.js';

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
};

type Sub = {
  id: string;
  status: string;
  plan: Plan | null;
  effective_plan: Plan | null;
  cycle_started_at: string;
  cycle_ends_at: string;
  cancels_at: string | null;
};

type Usage = {
  enumerate: number;
  read: number;
  write: number;
  delete: number;
  read_bytes: number;
  write_bytes: number;
  plan: Plan | null;
};

function esc(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function fmtDate(val: string | null): string {
  if (!val) return '—';
  const d = new Date(val);
  return isNaN(d.getTime()) ? val : d.toLocaleDateString();
}

function progressBar(label: string, used: number, limit: number | null): string {
  if (limit === null) {
    return `
      <div class="mb-3">
        <div class="d-flex justify-content-between small mb-1">
          <span>${label}</span>
          <span>${used} / <em>unlimited</em></span>
        </div>
        <div class="progress" style="height:6px">
          <div class="progress-bar bg-success" style="width:0%"></div>
        </div>
      </div>`;
  }

  const pct = limit === 0 ? 100 : Math.min(100, Math.round((used / limit) * 100));
  const color = pct >= 100 ? 'bg-danger' : pct >= 80 ? 'bg-warning' : 'bg-success';
  return `
    <div class="mb-3">
      <div class="d-flex justify-content-between small mb-1">
        <span>${label}</span>
        <span>${used} / ${limit}</span>
      </div>
      <div class="progress" style="height:6px">
        <div class="progress-bar ${color}" style="width:${pct}%"></div>
      </div>
    </div>`;
}

function renderSubInfo(sub: Sub, subInfoEl: HTMLElement): void {
  const plan = sub.effective_plan;
  const planName = plan ? plan.name : 'Unlimited (no plan)';
  const statusBadge =
    sub.status === 'active'
      ? `<span class="badge bg-success">Active</span>`
      : `<span class="badge bg-secondary">Canceled</span>`;

  subInfoEl.innerHTML = `
    <div class="d-flex justify-content-between align-items-start mb-3">
      <div>
        <div class="fw-semibold">${esc(planName)}</div>
        <div class="small text-secondary mt-1">
          Cycle: ${fmtDate(sub.cycle_started_at)} – ${fmtDate(sub.cycle_ends_at)}
          ${sub.cancels_at ? `<br><span class="text-warning">Cancels: ${fmtDate(sub.cancels_at)}</span>` : ''}
        </div>
      </div>
      <div>${statusBadge}</div>
    </div>
    <div class="d-flex gap-2">
      <button id="switch-plan-btn" class="btn btn-sm btn-outline-primary" data-bs-toggle="modal" data-bs-target="#switchPlanModal">
        Switch Plan
      </button>
      ${sub.status === 'active' ? `<button id="cancel-btn" class="btn btn-sm btn-outline-danger">Cancel Subscription</button>` : ''}
    </div>
  `;

  const cancelBtn = qs<HTMLButtonElement>('#cancel-btn');
  cancelBtn?.addEventListener('click', async () => {
    if (
      !confirm(
        'Cancel your subscription? You will remain on your current plan until the end of the billing cycle.',
      )
    )
      return;
    try {
      cancelBtn.disabled = true;
      const csrf = getCsrfToken();
      const resp = await fetch('/api/v1/subscription/my/cancel/', {
        method: 'POST',
        headers: { Accept: 'application/json', ...(csrf ? { 'X-CSRFToken': csrf } : {}) },
        credentials: 'same-origin',
      });
      if (!resp.ok) throw new Error(`Cancel failed (${resp.status})`);
      setFlash(
        'Subscription canceled. You will remain on your plan until the end of the cycle.',
        'info',
      );
      await loadAll();
    } catch (err) {
      setFlash(String(err), 'error');
      cancelBtn.disabled = false;
    }
  });
}

function renderUsageBars(usage: Usage, usageBarsEl: HTMLElement): void {
  const plan = usage.plan;
  usageBarsEl.innerHTML =
    progressBar('Enumerate requests', usage.enumerate, plan?.enumerate_limit ?? null) +
    progressBar('Read requests', usage.read, plan?.read_limit ?? null) +
    progressBar('Write requests', usage.write, plan?.write_limit ?? null) +
    progressBar('Delete requests', usage.delete, plan?.delete_limit ?? null) +
    progressBar('Read data (bytes)', usage.read_bytes, plan?.read_transfer_limit_bytes ?? null) +
    progressBar('Write data (bytes)', usage.write_bytes, plan?.write_transfer_limit_bytes ?? null);
}

async function loadAvailablePlans(plansListEl: HTMLElement): Promise<void> {
  try {
    const resp = await fetch('/api/v1/subscription/plans/', {
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
    });
    if (!resp.ok) {
      plansListEl.innerHTML = `<div class="text-secondary small">Failed to load plans (${resp.status}).</div>`;
      return;
    }
    const data = (await resp.json()) as Plan[] | { results: Plan[] };
    const plans = Array.isArray(data) ? data : ((data as { results: Plan[] }).results ?? []);

    if (!plans.length) {
      plansListEl.innerHTML = `<div class="text-secondary small">No plans available.</div>`;
      return;
    }

    const ul = document.createElement('ul');
    ul.className = 'list-group list-group-flush';
    for (const plan of plans) {
      const li = document.createElement('li');
      li.className = 'list-group-item d-flex justify-content-between align-items-center';

      const leftDiv = document.createElement('div');
      const nameSpan = document.createElement('span');
      nameSpan.className = 'fw-semibold small';
      nameSpan.textContent = plan.name;
      leftDiv.appendChild(nameSpan);

      if (plan.is_default) {
        const defaultBadge = document.createElement('span');
        defaultBadge.className = 'badge bg-success ms-1';
        defaultBadge.textContent = 'Default';
        leftDiv.appendChild(defaultBadge);
      }

      const button = document.createElement('button');
      button.className = 'btn btn-sm btn-outline-primary switch-btn';
      button.textContent = 'Select';
      button.dataset.planId = plan.id;

      li.appendChild(leftDiv);
      li.appendChild(button);
      ul.appendChild(li);
    }
    plansListEl.innerHTML = '';
    plansListEl.appendChild(ul);

    plansListEl.querySelectorAll<HTMLButtonElement>('.switch-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const planId = btn.dataset['planId'];
        if (!planId) return;
        try {
          btn.disabled = true;
          const csrf = getCsrfToken();
          const resp = await fetch('/api/v1/subscription/my/switch/', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Accept: 'application/json',
              ...(csrf ? { 'X-CSRFToken': csrf } : {}),
            },
            body: JSON.stringify({ plan_id: planId }),
            credentials: 'same-origin',
          });
          if (!resp.ok) throw new Error(`Switch failed (${resp.status})`);

          const modal = document.getElementById('switchPlanModal');
          if (modal) {
            const bsModal = (
              window as typeof window & {
                bootstrap?: {
                  Modal?: { getInstance?: (el: HTMLElement) => { hide(): void } | null };
                };
              }
            ).bootstrap?.Modal?.getInstance?.(modal);
            bsModal?.hide();
          }
          setFlash('Plan switched successfully.', 'info');
          await loadAll();
        } catch (err) {
          setFlash(String(err), 'error');
          btn.disabled = false;
        }
      });
    });
  } catch (err) {
    plansListEl.innerHTML = `<div class="text-secondary small">Error: ${String(err)}</div>`;
  }
}

async function loadAll(): Promise<void> {
  const subInfoEl = qs<HTMLElement>('#sub-info');
  const usageBarsEl = qs<HTMLElement>('#usage-bars');
  const plansListEl = qs<HTMLElement>('#available-plans-list');
  if (!subInfoEl || !usageBarsEl) return;

  try {
    const [subResp, usageResp] = await Promise.all([
      fetch('/api/v1/subscription/my/', {
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
      }),
      fetch('/api/v1/subscription/my/usage/', {
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
      }),
    ]);

    if (!subResp.ok) {
      setFlash(`Failed to load subscription (${subResp.status}).`, 'error');
      return;
    }

    const sub = (await subResp.json()) as Sub;
    renderSubInfo(sub, subInfoEl);

    if (usageResp.ok) {
      const usage = (await usageResp.json()) as Usage;
      renderUsageBars(usage, usageBarsEl);
    } else {
      usageBarsEl.innerHTML = `<div class="text-secondary small">Failed to load usage (${usageResp.status}).</div>`;
    }

    if (plansListEl) {
      await loadAvailablePlans(plansListEl);
    }
  } catch (err) {
    setFlash(`Error: ${String(err)}`, 'error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  void loadAll();
});
