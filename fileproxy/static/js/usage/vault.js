import { apiJson } from "../utils/api.js";
import { setFlash } from "../utils/dom.js";
const KIND_LABELS = {
    aws_s3: "Amazon S3",
    gdrive_oauth2: "Google Drive",
    dropbox_oauth2: "Dropbox",
};
function fmtDate(value) {
    const d = new Date(value);
    if (Number.isNaN(d.getTime()))
        return value;
    return d.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    });
}
function renderKindCards(metrics) {
    const container = document.getElementById("kind-cards");
    if (!container)
        return;
    container.innerHTML = "";
    const entries = [
        { label: "Total", value: metrics.total },
        ...Object.entries(metrics.by_kind).map(([kind, count]) => ({
            label: KIND_LABELS[kind] ?? kind,
            value: count,
        })),
    ];
    for (const entry of entries) {
        const col = document.createElement("div");
        col.className = "col-md-3 col-sm-4 col-6";
        col.innerHTML = `
      <div class="card ab-card h-100">
        <div class="card-body text-center">
          <div class="mb-1"><i class="bi bi-hdd-stack fs-4 text-secondary" aria-hidden="true"></i></div>
          <div class="fw-semibold">${entry.value}</div>
          <div class="small text-secondary">${entry.label}</div>
        </div>
      </div>`;
        container.appendChild(col);
    }
}
function renderRecent(recent) {
    const tbody = document.getElementById("recent-rows");
    if (!tbody)
        return;
    tbody.innerHTML = "";
    if (!recent.length) {
        tbody.innerHTML =
            '<tr><td colspan="3" class="text-secondary">No credentials yet.</td></tr>';
        return;
    }
    for (const item of recent) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
      <td>${item.name}</td>
      <td><code class="small">${KIND_LABELS[item.kind] ?? item.kind}</code></td>
      <td>${fmtDate(item.created_at)}</td>`;
        tbody.appendChild(tr);
    }
}
async function load() {
    try {
        const metrics = await apiJson("/api/v1/usage/vault-metrics/");
        renderKindCards(metrics);
        renderRecent(metrics.recent);
    }
    catch (err) {
        setFlash(`Failed to load vault metrics: ${String(err)}`, "error");
    }
}
document.addEventListener("DOMContentLoaded", () => {
    void load();
});
//# sourceMappingURL=vault.js.map