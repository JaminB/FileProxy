import { qs as qsMaybe, setFlash } from "../utils/dom.js";
import { apiJson } from "../utils/api.js";
import { getCsrfToken } from "../utils/cookies.js";

/* ----------------------------- Types ----------------------------- */

type VaultItemMeta = {
  id: number;
  name: string;
  kind: string;
  created_at: string;
  updated_at: string;
  rotated_at: string | null;
};

type BackendObject = { name: string; path: string; size: number | null };

type ObjectPage = { objects: BackendObject[]; next_cursor: string | null };

type Entry =
  | { kind: "folder"; name: string; path: string }
  | { kind: "file"; name: string; path: string; size: number | null };

type State = { vault: string | null; prefix: string };

/* ----------------------------- DOM helpers ----------------------------- */

function mustGet<T extends Element>(selector: string, root: ParentNode = document): T {
  const el = qsMaybe(selector, root) as T | null;
  if (!el) throw new Error(`Missing element: ${selector}`);
  return el;
}

const el = {
  vaultList: () => mustGet<HTMLElement>("#vault-list"),
  entries: () => mustGet<HTMLTableSectionElement>("#entries"),
  crumbs: () => mustGet<HTMLOListElement>("#path-crumbs"),

  title: () => mustGet<HTMLElement>("#browser-title"),
  subtitle: () => mustGet<HTMLElement>("#browser-subtitle"),

  refresh: () => mustGet<HTMLButtonElement>("#refresh"),
  vaultRefresh: () => mustGet<HTMLButtonElement>("#vault-refresh"),
  up: () => mustGet<HTMLButtonElement>("#up"),

  uploadFile: () => mustGet<HTMLInputElement>("#upload-file"),
  uploadName: () => mustGet<HTMLInputElement>("#upload-name"),
  uploadBtn: () => mustGet<HTMLButtonElement>("#upload"),
  uploadHint: () => mustGet<HTMLElement>("#upload-hint"),
  uploadStatus: () => mustGet<HTMLElement>("#upload-status"),
};

/* ----------------------------- State ----------------------------- */

const state: State = { vault: null, prefix: "" };

/* ----------------------------- Small utils ----------------------------- */

function fmtBytes(n: number | null | undefined): string {
  if (n == null) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return i === 0 ? `${v} ${units[i]}` : `${v.toFixed(1)} ${units[i]}`;
}

/* ----------------------------- UI state ----------------------------- */

function setUploadEnabled(enabled: boolean): void {
  el.uploadFile().disabled = !enabled;
  el.uploadName().disabled = !enabled;
  el.uploadBtn().disabled = !enabled;
}

function updateUploadButtonState(): void {
  const hasFile = Boolean(el.uploadFile().files?.[0]);
  el.uploadBtn().disabled = !(state.vault && hasFile);
}

function setBrowserHeader(): void {
  const hasVault = Boolean(state.vault);

  el.up().disabled = !hasVault || state.prefix === "";
  el.refresh().disabled = !hasVault;

  if (!hasVault) {
    el.title().textContent = "Select a vault";
    el.subtitle().textContent = "";
    el.uploadHint().textContent = "Select a vault to enable upload.";
    el.uploadStatus().textContent = "";
    setUploadEnabled(false);
    return;
  }

  el.title().textContent = state.vault!;
  el.subtitle().textContent = state.prefix ? `/${state.prefix}` : "/";
  el.uploadHint().textContent = state.prefix ? `Uploading into /${state.prefix}` : "Uploading into /";
  setUploadEnabled(true);
  updateUploadButtonState();
}

function setCrumbs(): void {
  const ol = el.crumbs();
  ol.innerHTML = "";

  if (!state.vault) {
    ol.innerHTML = `<li class="breadcrumb-item text-muted">—</li>`;
    return;
  }

  const parts = state.prefix.split("/").filter(Boolean);

  const addCrumbLink = (label: string, prefix: string) => {
    const li = document.createElement("li");
    li.className = "breadcrumb-item";
    const a = document.createElement("a");
    a.href = "#";
    a.textContent = label;
    a.addEventListener("click", (e) => {
      e.preventDefault();
      state.prefix = prefix;
      void refresh();
    });
    li.appendChild(a);
    ol.appendChild(li);
  };

  addCrumbLink("root", "");

  let accum = "";
  parts.forEach((p, idx) => {
    accum += `${p}/`;
    const isLast = idx === parts.length - 1;

    const li = document.createElement("li");
    li.className = "breadcrumb-item";

    if (isLast) {
      li.classList.add("active");
      li.setAttribute("aria-current", "page");
      li.textContent = p;
    } else {
      const a = document.createElement("a");
      a.href = "#";
      a.textContent = p;
      const target = accum;
      a.addEventListener("click", (e) => {
        e.preventDefault();
        state.prefix = target;
        void refresh();
      });
      li.appendChild(a);
    }

    ol.appendChild(li);
  });
}

/* ----------------------------- Data -> entries ----------------------------- */

function toEntries(objects: BackendObject[], prefix: string): Entry[] {
  const folders = new Map<string, Entry>();
  const files: Entry[] = [];

  for (const obj of objects) {
    const key = obj.path || "";
    if (!key.startsWith(prefix)) continue;

    const rest = key.slice(prefix.length);
    if (!rest) continue;

    const slash = rest.indexOf("/");
    if (slash !== -1) {
      const folderName = rest.slice(0, slash);
      const folderPath = `${prefix}${folderName}/`;
      if (!folders.has(folderPath)) {
        folders.set(folderPath, { kind: "folder", name: folderName, path: folderPath });
      }
      continue;
    }

    files.push({ kind: "file", name: rest, path: key, size: obj.size ?? null });
  }

  const out: Entry[] = [...folders.values(), ...files];
  out.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === "folder" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  return out;
}

/* ----------------------------- Rendering ----------------------------- */

function makeFileActions(entry: Extract<Entry, { kind: "file" }>): HTMLElement {
  const dd = document.createElement("div");
  dd.className = "dropdown dropup";

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "btn btn-sm btn-outline-secondary dropdown-toggle";
  toggle.setAttribute("data-bs-toggle", "dropdown");
  toggle.setAttribute("data-bs-boundary", "viewport");
  toggle.setAttribute("data-bs-reference", "parent");
  toggle.setAttribute("aria-expanded", "false");
  toggle.title = "Actions";
  toggle.innerHTML = `<i class="bi bi-three-dots"></i>`;

  const menu = document.createElement("ul");
  menu.className = "dropdown-menu dropdown-menu-end";

  const addItem = (html: string, onClick: () => void | Promise<void>, className = "dropdown-item") => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = className;
    btn.innerHTML = html;
    btn.addEventListener("click", () => void onClick());
    li.appendChild(btn);
    menu.appendChild(li);
  };

  const addDivider = () => {
    const li = document.createElement("li");
    li.innerHTML = `<hr class="dropdown-divider">`;
    menu.appendChild(li);
  };

  addItem(`<i class="bi bi-download me-2"></i>Download`, () => {
    if (!state.vault) return;
    const url = `/api/v1/files/${encodeURIComponent(state.vault)}/download/?path=${encodeURIComponent(entry.path)}`;
    const a = document.createElement("a");
    a.href = url;
    a.download = entry.name || "download";
    document.body.appendChild(a);
    a.click();
    a.remove();
  });

  addDivider();

  addItem(
    `<i class="bi bi-trash me-2"></i>Delete`,
    async () => {
      if (!state.vault) return;
      if (!confirm(`Delete "${entry.path}"?`)) return;

      try {
        await apiJson(
          `/api/v1/files/${encodeURIComponent(state.vault)}/object/?path=${encodeURIComponent(entry.path)}`,
          { method: "DELETE" }
        );
        setFlash("Deleted.", "success");
        await refresh();
      } catch (err) {
        setFlash(err instanceof Error ? err.message : "Delete failed.", "error");
      }
    },
    "dropdown-item text-danger"
  );

  dd.appendChild(toggle);
  dd.appendChild(menu);
  return dd;
}

function render(entries: Entry[]): void {
  const tbody = el.entries();
  tbody.innerHTML = "";

  if (!state.vault) {
    tbody.innerHTML =
      `<tr><td colspan="4" class="text-muted small">Choose a vault from the left to start browsing.</td></tr>`;
    return;
  }

  if (!entries.length) {
    tbody.innerHTML = `<tr><td colspan="4" class="text-muted small">This folder is empty.</td></tr>`;
    return;
  }

  for (const entry of entries) {
    const tr = document.createElement("tr");

    const tdName = document.createElement("td");
    const tdPath = document.createElement("td");
    const tdSize = document.createElement("td");
    const tdAct = document.createElement("td");
    tdAct.className = "text-end";

    if (entry.kind === "folder") {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-link btn-sm p-0 text-decoration-none";
      btn.innerHTML = `<i class="bi bi-folder2 me-2 opacity-75"></i>${entry.name}`;
      btn.addEventListener("click", () => {
        state.prefix = entry.path;
        void refresh();
      });

      tdName.appendChild(btn);
      tdPath.textContent = entry.path;
      tdSize.textContent = "";
    } else {
      tdName.innerHTML = `<i class="bi bi-file-earmark me-2 opacity-75"></i>${entry.name}`;
      tdPath.textContent = entry.path;
      tdSize.textContent = fmtBytes(entry.size);
      tdAct.appendChild(makeFileActions(entry));
    }

    tr.appendChild(tdName);
    tr.appendChild(tdPath);
    tr.appendChild(tdSize);
    tr.appendChild(tdAct);
    tbody.appendChild(tr);
  }
}

/* ----------------------------- API flows ----------------------------- */

async function refresh(): Promise<void> {
  setBrowserHeader();
  setCrumbs();

  if (!state.vault) {
    render([]);
    return;
  }

  const allObjects: BackendObject[] = [];
  let cursor: string | null = null;
  do {
    const params = new URLSearchParams();
    if (state.prefix) params.set("prefix", state.prefix);
    if (cursor) params.set("cursor", cursor);
    const qsPart = params.size ? `?${params.toString()}` : "";
    const page = await apiJson<ObjectPage>(
      `/api/v1/files/${encodeURIComponent(state.vault!)}/objects/${qsPart}`
    );
    allObjects.push(...page.objects);
    // Display results incrementally as each page is loaded.
    render(toEntries(allObjects, state.prefix));
    cursor = page.next_cursor;
  } while (cursor !== null);

  render(toEntries(allObjects, state.prefix));
  el.up().disabled = state.prefix === "";
  updateUploadButtonState();
}

function uploadWithProgress(
  url: string,
  formData: FormData
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const csrf = getCsrfToken();
    xhr.open("POST", url);
    if (csrf) xhr.setRequestHeader("X-CSRFToken", csrf);
    xhr.withCredentials = true;
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        let detail = `Request failed (${xhr.status})`;
        try {
          const data = JSON.parse(xhr.responseText) as { detail?: unknown };
          if (data?.detail) detail = String(data.detail);
        } catch { /* ignore parse errors */ }
        reject(new Error(detail));
      }
    };
    xhr.onerror = () => reject(new Error("Network error"));
    xhr.send(formData);
  });
}

async function doUpload(): Promise<void> {
  if (!state.vault) return;

  const file = el.uploadFile().files?.[0] ?? null;
  if (!file) return;

  const name = (el.uploadName().value || file.name).trim();
  if (!name) {
    setFlash("Name is required.", "error");
    return;
  }

  const path = `${state.prefix}${name}`;

  el.uploadStatus().textContent = "Uploading…";
  el.uploadBtn().disabled = true;

  try {
    const form = new FormData();
    form.append("path", path);
    form.append("file", file);
    await uploadWithProgress(
      `/api/v1/files/${encodeURIComponent(state.vault)}/write/`,
      form
    );

    el.uploadStatus().textContent = "Uploaded.";
    setFlash("Upload complete.", "success");

    el.uploadFile().value = "";
    el.uploadName().value = "";

    await refresh();
  } catch (e) {
    el.uploadStatus().textContent = "";
    setFlash(e instanceof Error ? e.message : "Upload failed.", "error");
  } finally {
    updateUploadButtonState();
  }
}

function goUp(): void {
  if (!state.prefix) return;
  const parts = state.prefix.split("/").filter(Boolean);
  parts.pop();
  state.prefix = parts.length ? `${parts.join("/")}/` : "";
  void refresh();
}

async function loadVaults(): Promise<void> {
  const host = el.vaultList();
  host.innerHTML = `<div class="text-muted small">Loading…</div>`;

  const items = await apiJson<VaultItemMeta[]>("/api/v1/files/");

  if (!items.length) {
    host.innerHTML = `<div class="text-muted small">No vault items yet.</div>`;
    state.vault = null;
    state.prefix = "";
    setBrowserHeader();
    setCrumbs();
    render([]);
    return;
  }

  host.innerHTML = "";

  let firstAnchor: HTMLAnchorElement | null = null;

  for (const it of items) {
    const a = document.createElement("a");
    a.href = "#";
    a.className =
      "list-group-item list-group-item-action d-flex align-items-center justify-content-between files-vault-item";
    a.innerHTML = `
      <div class="d-flex align-items-center gap-2">
        <i class="bi bi-drive opacity-75"></i>
        <div class="lh-sm">
          <div class="fw-semibold small mb-0">${it.name}</div>
          <div class="small text-muted">${it.kind}</div>
        </div>
      </div>
      <i class="bi bi-chevron-right opacity-50"></i>
    `;

    a.addEventListener("click", (e) => {
      e.preventDefault();

      state.vault = it.name;
      state.prefix = "";
      void refresh();

      for (const elItem of Array.from(host.querySelectorAll(".list-group-item"))) {
        elItem.classList.remove("active");
      }
      a.classList.add("active");
    });

    if (!firstAnchor) firstAnchor = a;
    host.appendChild(a);
  }

  if (!state.vault && firstAnchor) firstAnchor.click();
}

/* ----------------------------- Boot ----------------------------- */

document.addEventListener("DOMContentLoaded", async () => {
  await loadVaults();
  setBrowserHeader();
  setCrumbs();
  updateUploadButtonState();

  el.vaultRefresh().addEventListener("click", () => void loadVaults());
  el.refresh().addEventListener("click", () => void refresh());
  el.up().addEventListener("click", goUp);

  el.uploadFile().addEventListener("change", () => {
    const f = el.uploadFile().files?.[0];
    if (f) el.uploadName().value = f.name;
    updateUploadButtonState();
  });

  el.uploadName().addEventListener("input", updateUploadButtonState);
  el.uploadBtn().addEventListener("click", () => void doUpload());
});
