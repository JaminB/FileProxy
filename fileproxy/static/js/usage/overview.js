import { apiJson } from "../utils/api.js";
import { setFlash } from "../utils/dom.js";
const PERIODS = [
    { label: "7d", days: 7 },
    { label: "30d", days: 30 },
    { label: "90d", days: 90 },
    { label: "1y", days: 365 },
];
const DEFAULT_DAYS = 30;
function renderPeriodSelector(activeDays) {
    const container = document.getElementById("period-selector");
    if (!container)
        return;
    container.innerHTML = "";
    for (const period of PERIODS) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className =
            period.days === activeDays
                ? "btn btn-sm btn-secondary"
                : "btn btn-sm btn-outline-secondary";
        btn.textContent = period.label;
        btn.addEventListener("click", () => void load(period.days));
        container.appendChild(btn);
    }
}
function renderSummary(data) {
    const container = document.getElementById("summary-cards");
    if (!container)
        return;
    container.innerHTML = "";
    const entries = [
        { label: "Total", icon: "bi-activity", value: data.total },
        { label: "Enumerate", icon: "bi-list-ul", value: data.ops["enumerate"] ?? 0 },
        { label: "Read", icon: "bi-download", value: data.ops["read"] ?? 0 },
        { label: "Write", icon: "bi-upload", value: data.ops["write"] ?? 0 },
        { label: "Delete", icon: "bi-trash", value: data.ops["delete"] ?? 0 },
    ];
    for (const entry of entries) {
        const col = document.createElement("div");
        col.className = "col-md-2 col-sm-4 col-6";
        col.innerHTML = `
      <div class="card ab-card h-100">
        <div class="card-body text-center">
          <div class="mb-1"><i class="bi ${entry.icon} fs-4 text-secondary" aria-hidden="true"></i></div>
          <div class="fw-semibold">${entry.value}</div>
          <div class="small text-secondary">${entry.label}</div>
        </div>
      </div>`;
        container.appendChild(col);
    }
}
function renderByVault(items) {
    const tbody = document.getElementById("by-vault-rows");
    if (!tbody)
        return;
    tbody.innerHTML = "";
    if (!items.length) {
        tbody.innerHTML =
            '<tr><td colspan="7" class="text-secondary">No operations recorded yet.</td></tr>';
        return;
    }
    for (const item of items) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
      <td><a href="/usage/vault/${item.name}/" class="text-decoration-none text-reset fw-semibold">${item.name}</a></td>
      <td><code class="small">${item.kind}</code></td>
      <td>${item.enumerate}</td>
      <td>${item.read}</td>
      <td>${item.write}</td>
      <td>${item.delete}</td>
      <td><strong>${item.total}</strong></td>`;
        tbody.appendChild(tr);
    }
}
async function load(days = DEFAULT_DAYS) {
    renderPeriodSelector(days);
    try {
        const [summary, byVault] = await Promise.all([
            apiJson(`/api/v1/usage/summary/?days=${days}`),
            apiJson(`/api/v1/usage/by-vault/?days=${days}`),
        ]);
        renderSummary(summary);
        renderByVault(byVault);
    }
    catch (err) {
        setFlash(`Failed to load usage data: ${String(err)}`, "error");
    }
}
document.addEventListener("DOMContentLoaded", () => {
    void load();
});
//# sourceMappingURL=overview.js.map