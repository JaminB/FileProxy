import { apiJson } from "../utils/api.js";
import { setFlash } from "../utils/dom.js";

declare const Chart: any;

type SummaryOps = Record<string, number>;

type Summary = {
  days: number;
  total: number;
  ops: SummaryOps;
};

type Timeline = {
  vault_item_name: string;
  days: number;
  dates: string[];
  series: Record<string, number[]>;
};

const PERIODS = [
  { label: "7d", days: 7 },
  { label: "30d", days: 30 },
  { label: "90d", days: 90 },
  { label: "1y", days: 365 },
];
const DEFAULT_DAYS = 30;

function renderPeriodSelector(activeDays: number): void {
  const container = document.getElementById("period-selector");
  if (!container) return;
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

function renderSummary(data: Summary): void {
  const container = document.getElementById("summary-cards");
  if (!container) return;
  container.innerHTML = "";

  const entries: Array<{ label: string; icon: string; value: number }> = [
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

let activeChart: any = null;

function renderChart(data: Timeline): void {
  const canvas = document.getElementById("timeline-chart") as HTMLCanvasElement | null;
  if (!canvas) return;

  if (activeChart) {
    activeChart.destroy();
    activeChart = null;
  }

  const datasets = [
    {
      label: "Enumerate",
      data: data.series["enumerate"] ?? [],
      borderColor: "#6c757d",
      backgroundColor: "#6c757d",
      tension: 0.3,
      pointRadius: 2,
      borderWidth: 2,
      fill: false,
    },
    {
      label: "Read",
      data: data.series["read"] ?? [],
      borderColor: "#0d6efd",
      backgroundColor: "#0d6efd",
      tension: 0.3,
      pointRadius: 2,
      borderWidth: 2,
      fill: false,
    },
    {
      label: "Write",
      data: data.series["write"] ?? [],
      borderColor: "#198754",
      backgroundColor: "#198754",
      tension: 0.3,
      pointRadius: 2,
      borderWidth: 2,
      fill: false,
    },
    {
      label: "Delete",
      data: data.series["delete"] ?? [],
      borderColor: "#dc3545",
      backgroundColor: "#dc3545",
      tension: 0.3,
      pointRadius: 2,
      borderWidth: 2,
      fill: false,
    },
  ];

  activeChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: data.dates,
      datasets,
    },
    options: {
      responsive: true,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: {
          position: "bottom",
        },
        title: {
          display: false,
        },
      },
      scales: {
        x: {
          grid: {
            color: "rgba(0,0,0,0.06)",
          },
        },
        y: {
          min: 0,
          ticks: {
            stepSize: 1,
            callback: (value: number) => Number.isInteger(value) ? value : null,
          },
          grid: {
            color: "rgba(0,0,0,0.06)",
          },
        },
      },
    },
  });
}

async function load(days: number = DEFAULT_DAYS): Promise<void> {
  const nameEl = document.getElementById("vault-name-data");
  const vaultName = nameEl?.dataset["vaultName"] ?? "";
  if (!vaultName) return;

  renderPeriodSelector(days);
  try {
    const [summary, timeline] = await Promise.all([
      apiJson<Summary>(`/api/v1/usage/summary/?vault=${encodeURIComponent(vaultName)}&days=${days}`),
      apiJson<Timeline>(`/api/v1/usage/timeline/?vault=${encodeURIComponent(vaultName)}&days=${days}`),
    ]);
    renderSummary(summary);
    renderChart(timeline);
  } catch (err) {
    setFlash(`Failed to load usage data: ${String(err)}`, "error");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  void load();
});
