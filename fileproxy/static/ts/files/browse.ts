import { qs as qsMaybe, setFlash } from '../utils/dom.js';
import { apiJson } from '../utils/api.js';
import { getCsrfToken } from '../utils/cookies.js';

/* ----------------------------- Types ----------------------------- */

type ConnectionMeta = {
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
  | { kind: 'folder'; name: string; path: string }
  | { kind: 'file'; name: string; path: string; size: number | null };

type PendingEntry = {
  id: string;
  path: string;
  expected_size: number;
  status: 'pending' | 'uploading' | 'failed';
  created_at: string;
};

type State = {
  vault: string | null;
  prefix: string;
  pageSize: number; // 25 | 50 | 100 | 200
  cursors: Array<string | null>; // cursors[i] = cursor needed to fetch page i; cursors[0] = null
  page: number; // current 0-indexed page
  hasNextPage: boolean;
};

/* ----------------------------- DOM helpers ----------------------------- */

function mustGet<T extends Element>(selector: string, root: ParentNode = document): T {
  const el = qsMaybe(selector, root) as T | null;
  if (!el) throw new Error(`Missing element: ${selector}`);
  return el;
}

const el = {
  vaultList: () => mustGet<HTMLElement>('#vault-list'),
  entries: () => mustGet<HTMLTableSectionElement>('#entries'),
  crumbs: () => mustGet<HTMLOListElement>('#path-crumbs'),

  title: () => mustGet<HTMLElement>('#browser-title'),
  subtitle: () => mustGet<HTMLElement>('#browser-subtitle'),

  refresh: () => mustGet<HTMLButtonElement>('#refresh'),
  vaultRefresh: () => mustGet<HTMLButtonElement>('#vault-refresh'),
  up: () => mustGet<HTMLButtonElement>('#up'),

  uploadFile: () => mustGet<HTMLInputElement>('#upload-file'),
  uploadName: () => mustGet<HTMLInputElement>('#upload-name'),
  uploadBtn: () => mustGet<HTMLButtonElement>('#upload'),
  uploadHint: () => mustGet<HTMLElement>('#upload-hint'),
  uploadStatus: () => mustGet<HTMLElement>('#upload-status'),
  uploadProgressWrap: () => mustGet<HTMLElement>('#upload-progress-wrap'),
  uploadProgressBar: () => mustGet<HTMLElement>('#upload-progress-bar'),

  pageControls: () => mustGet<HTMLElement>('#page-controls'),
};

/* ----------------------------- State ----------------------------- */

const state: State = {
  vault: null,
  prefix: '',
  pageSize: 50,
  cursors: [null],
  page: 0,
  hasNextPage: false,
};

let pendingEntries: PendingEntry[] = [];
let pendingPollTimer: ReturnType<typeof setInterval> | null = null;

/* ----------------------------- Small utils ----------------------------- */

function fmtBytes(n: number | null | undefined): string {
  if (n == null || n === 0) return '';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return i === 0 ? `${v} ${units[i]}` : `${v.toFixed(1)} ${units[i]}`;
}

function fileIcon(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
  if (['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'bmp'].includes(ext))
    return 'bi-file-earmark-image';
  if (ext === 'pdf') return 'bi-file-earmark-pdf';
  if (['doc', 'docx'].includes(ext)) return 'bi-file-earmark-word';
  if (['xls', 'xlsx', 'csv'].includes(ext)) return 'bi-file-earmark-excel';
  if (['ppt', 'pptx'].includes(ext)) return 'bi-file-earmark-slides';
  if (['zip', 'gz', 'tar', 'bz2', '7z', 'rar'].includes(ext)) return 'bi-file-earmark-zip';
  if (['mp4', 'mov', 'avi', 'mkv', 'webm'].includes(ext)) return 'bi-file-earmark-play';
  if (['mp3', 'wav', 'ogg', 'flac', 'm4a'].includes(ext)) return 'bi-file-earmark-music';
  if (
    [
      'js',
      'ts',
      'py',
      'java',
      'c',
      'cpp',
      'cs',
      'go',
      'rs',
      'rb',
      'php',
      'html',
      'css',
      'json',
      'xml',
      'yaml',
      'yml',
    ].includes(ext)
  )
    return 'bi-file-earmark-code';
  if (['txt', 'md', 'log'].includes(ext)) return 'bi-file-earmark-text';
  return 'bi-file-earmark';
}

function resetPagination(): void {
  state.cursors = [null];
  state.page = 0;
  state.hasNextPage = false;
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

  el.up().disabled = !hasVault || state.prefix === '';
  el.refresh().disabled = !hasVault;

  if (!hasVault) {
    el.title().textContent = 'Select a vault';
    el.subtitle().textContent = '';
    el.uploadHint().textContent = 'Select a vault to enable upload.';
    el.uploadStatus().textContent = '';
    setUploadEnabled(false);
    return;
  }

  el.title().textContent = state.vault!;
  el.subtitle().textContent = state.prefix ? `/${state.prefix}` : '/';
  el.uploadHint().textContent = state.prefix
    ? `Uploading into /${state.prefix}`
    : 'Uploading into /';
  setUploadEnabled(true);
  updateUploadButtonState();
}

function setCrumbs(): void {
  const ol = el.crumbs();
  ol.innerHTML = '';

  if (!state.vault) {
    ol.innerHTML = `<li class="breadcrumb-item text-muted">—</li>`;
    return;
  }

  const parts = state.prefix.split('/').filter(Boolean);

  const addCrumbLink = (label: string, prefix: string) => {
    const li = document.createElement('li');
    li.className = 'breadcrumb-item';
    const a = document.createElement('a');
    a.href = '#';
    a.textContent = label;
    a.addEventListener('click', (e) => {
      e.preventDefault();
      state.prefix = prefix;
      resetPagination();
      void refresh();
    });
    li.appendChild(a);
    ol.appendChild(li);
  };

  addCrumbLink('root', '');

  let accum = '';
  parts.forEach((p, idx) => {
    accum += `${p}/`;
    const isLast = idx === parts.length - 1;

    const li = document.createElement('li');
    li.className = 'breadcrumb-item';

    if (isLast) {
      li.classList.add('active');
      li.setAttribute('aria-current', 'page');
      li.textContent = p;
    } else {
      const a = document.createElement('a');
      a.href = '#';
      a.textContent = p;
      const target = accum;
      a.addEventListener('click', (e) => {
        e.preventDefault();
        state.prefix = target;
        resetPagination();
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
    const key = obj.path || '';
    if (!key.startsWith(prefix)) continue;

    const rest = key.slice(prefix.length);
    if (!rest) continue;

    const slash = rest.indexOf('/');
    if (slash !== -1) {
      const folderName = rest.slice(0, slash);
      const folderPath = `${prefix}${folderName}/`;
      if (!folders.has(folderPath)) {
        folders.set(folderPath, { kind: 'folder', name: folderName, path: folderPath });
      }
      continue;
    }

    files.push({ kind: 'file', name: rest, path: key, size: obj.size ?? null });
  }

  const out: Entry[] = [...folders.values(), ...files];
  out.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === 'folder' ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  return out;
}

/* ----------------------------- Pending uploads ----------------------------- */

async function fetchPending(): Promise<PendingEntry[]> {
  if (!state.vault) return [];
  try {
    const data = await apiJson<PendingEntry[]>(
      `/api/v1/files/${encodeURIComponent(state.vault)}/pending/`,
    );
    pendingEntries = data;
    return data;
  } catch {
    return pendingEntries; // keep stale on error
  }
}

function stopPendingPoll(): void {
  if (pendingPollTimer !== null) {
    clearInterval(pendingPollTimer);
    pendingPollTimer = null;
  }
}

function startPendingPoll(): void {
  if (pendingPollTimer !== null) return; // already running

  // Track which paths were pending so we can refresh when they complete
  let prevPaths = new Set(pendingEntries.map((p) => p.path));

  pendingPollTimer = setInterval(() => {
    void (async () => {
      const current = await fetchPending();
      const currentPaths = new Set(current.map((p) => p.path));

      // Find paths that completed (were pending, now gone)
      const completed = [...prevPaths].filter((path) => !currentPaths.has(path));
      prevPaths = currentPaths;

      // Re-render pending rows on every tick
      const tbody = el.entries();
      // Remove old pending rows and re-render all
      renderWithPending(tbody);

      // If any file completed, refresh the main listing to show it
      if (completed.length > 0) {
        void refresh();
      }

      // Stop polling when nothing is pending
      if (current.length === 0) {
        stopPendingPoll();
      }
    })();
  }, 4000);
}

/* ----------------------------- Rendering ----------------------------- */

function makePendingRow(p: PendingEntry): HTMLTableRowElement {
  const tr = document.createElement('tr');
  const isFailed = p.status === 'failed';
  tr.className = isFailed ? 'table-danger' : 'table-warning';

  const filename = p.path.split('/').pop() || p.path;

  const tdName = document.createElement('td');
  const icon = isFailed
    ? `<i class="bi bi-exclamation-triangle me-2 text-danger opacity-75"></i>`
    : `<i class="bi bi-hourglass-split me-2 text-warning opacity-75"></i>`;
  tdName.innerHTML = `${icon}<em class="text-muted">${filename}</em>`;

  const tdPath = document.createElement('td');
  tdPath.innerHTML = `<span class="text-muted">${p.path}</span>`;

  const tdSize = document.createElement('td');
  tdSize.textContent = fmtBytes(p.expected_size);

  const tdAct = document.createElement('td');
  tdAct.className = 'text-end';
  if (isFailed) {
    tdAct.innerHTML = `<span class="badge bg-danger">Failed</span>`;
  } else {
    tdAct.innerHTML = `<span class="badge bg-warning text-dark">Pending</span>`;
  }

  tr.appendChild(tdName);
  tr.appendChild(tdPath);
  tr.appendChild(tdSize);
  tr.appendChild(tdAct);
  return tr;
}

function makeFileActions(entry: Extract<Entry, { kind: 'file' }>): HTMLElement {
  const dd = document.createElement('div');
  dd.className = 'dropdown dropup';

  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'btn btn-sm btn-outline-secondary dropdown-toggle';
  toggle.setAttribute('data-bs-toggle', 'dropdown');
  toggle.setAttribute('data-bs-boundary', 'viewport');
  toggle.setAttribute('data-bs-reference', 'parent');
  toggle.setAttribute('aria-expanded', 'false');
  toggle.title = 'Actions';
  toggle.innerHTML = `<i class="bi bi-three-dots"></i>`;

  const menu = document.createElement('ul');
  menu.className = 'dropdown-menu dropdown-menu-end';

  const addItem = (
    html: string,
    onClick: () => void | Promise<void>,
    className = 'dropdown-item',
  ) => {
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = className;
    btn.innerHTML = html;
    btn.addEventListener('click', () => void onClick());
    li.appendChild(btn);
    menu.appendChild(li);
  };

  const addDivider = () => {
    const li = document.createElement('li');
    li.innerHTML = `<hr class="dropdown-divider">`;
    menu.appendChild(li);
  };

  addItem(`<i class="bi bi-download me-2"></i>Download`, () => {
    if (!state.vault) return;
    const url = `/api/v1/files/${encodeURIComponent(state.vault)}/download/?path=${encodeURIComponent(entry.path)}`;
    const a = document.createElement('a');
    a.href = url;
    a.download = entry.name || 'download';
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
          { method: 'DELETE' },
        );
        setFlash('Deleted.', 'success');
        await refresh();
      } catch (err) {
        setFlash(err instanceof Error ? err.message : 'Delete failed.', 'error');
      }
    },
    'dropdown-item text-danger',
  );

  dd.appendChild(toggle);
  dd.appendChild(menu);
  return dd;
}

function renderWithPending(tbody: HTMLTableSectionElement): void {
  // Remove existing pending rows (rows with data-pending attribute)
  for (const row of Array.from(tbody.querySelectorAll('tr[data-pending]'))) {
    row.remove();
  }

  // Prepend pending rows
  const frag = document.createDocumentFragment();
  for (const p of pendingEntries) {
    const row = makePendingRow(p);
    row.setAttribute('data-pending', p.id);
    frag.appendChild(row);
  }
  tbody.insertBefore(frag, tbody.firstChild);
}

function render(entries: Entry[]): void {
  const tbody = el.entries();
  tbody.innerHTML = '';

  if (!state.vault) {
    tbody.innerHTML = `<tr><td colspan="4" class="text-muted small">Choose a vault from the left to start browsing.</td></tr>`;
    return;
  }

  if (!entries.length && !pendingEntries.length) {
    tbody.innerHTML = `<tr><td colspan="4" class="text-muted small">This folder is empty.</td></tr>`;
    return;
  }

  for (const entry of entries) {
    const tr = document.createElement('tr');

    const tdName = document.createElement('td');
    const tdPath = document.createElement('td');
    const tdSize = document.createElement('td');
    const tdAct = document.createElement('td');
    tdAct.className = 'text-end';

    if (entry.kind === 'folder') {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-link btn-sm p-0 text-decoration-none';
      btn.innerHTML = `<i class="bi bi-folder2 me-2 opacity-75"></i>${entry.name}`;
      btn.addEventListener('click', () => {
        state.prefix = entry.path;
        resetPagination();
        void refresh();
      });

      tdName.appendChild(btn);
      tdPath.textContent = entry.path;
      tdSize.textContent = '';
    } else {
      const icon = fileIcon(entry.name);
      tdName.innerHTML = `<i class="bi ${icon} me-2 opacity-75"></i>${entry.name}`;
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

  // Prepend pending rows on top
  renderWithPending(tbody);
}

function renderPagination(): void {
  const host = el.pageControls();
  host.innerHTML = '';

  if (!state.vault) return;

  // Prev button
  const prevBtn = document.createElement('button');
  prevBtn.type = 'button';
  prevBtn.className = 'btn btn-sm btn-outline-secondary';
  prevBtn.innerHTML = `<i class="bi bi-chevron-left"></i>`;
  prevBtn.disabled = state.page === 0;
  prevBtn.addEventListener('click', () => {
    state.page--;
    void refresh();
  });

  // Page label
  const pageLabel = document.createElement('span');
  pageLabel.className = 'text-muted';
  pageLabel.textContent = `Page ${state.page + 1}`;

  // Next button
  const nextBtn = document.createElement('button');
  nextBtn.type = 'button';
  nextBtn.className = 'btn btn-sm btn-outline-secondary';
  nextBtn.innerHTML = `<i class="bi bi-chevron-right"></i>`;
  nextBtn.disabled = !state.hasNextPage;
  nextBtn.addEventListener('click', () => {
    state.page++;
    void refresh();
  });

  // Nav group (left side)
  const navGroup = document.createElement('div');
  navGroup.className = 'd-flex align-items-center gap-2';
  navGroup.appendChild(prevBtn);
  navGroup.appendChild(pageLabel);
  navGroup.appendChild(nextBtn);

  // Page size selector (right side)
  const sizeLabel = document.createElement('label');
  sizeLabel.className = 'text-muted d-flex align-items-center gap-1';

  const sizeSelect = document.createElement('select');
  sizeSelect.className = 'form-select form-select-sm';
  sizeSelect.style.width = 'auto';
  for (const size of [25, 50, 100, 200]) {
    const opt = document.createElement('option');
    opt.value = String(size);
    opt.textContent = String(size);
    opt.selected = size === state.pageSize;
    sizeSelect.appendChild(opt);
  }
  sizeSelect.addEventListener('change', () => {
    state.pageSize = Number(sizeSelect.value);
    resetPagination();
    void refresh();
  });

  sizeLabel.appendChild(document.createTextNode('Per page:'));
  sizeLabel.appendChild(sizeSelect);

  host.appendChild(navGroup);
  host.appendChild(sizeLabel);
}

/* ----------------------------- API flows ----------------------------- */

async function refresh(): Promise<void> {
  setBrowserHeader();
  setCrumbs();

  if (!state.vault) {
    render([]);
    renderPagination();
    return;
  }

  const params = new URLSearchParams();
  if (state.prefix) params.set('prefix', state.prefix);
  const cursor = state.cursors[state.page];
  if (cursor) params.set('cursor', cursor);
  params.set('page_size', String(state.pageSize));

  const page = await apiJson<ObjectPage>(
    `/api/v1/files/${encodeURIComponent(state.vault!)}/objects/?${params.toString()}`,
  );

  // Store next cursor for forward navigation
  if (page.next_cursor) {
    state.cursors[state.page + 1] = page.next_cursor;
    state.hasNextPage = true;
  } else {
    state.hasNextPage = false;
  }

  render(toEntries(page.objects, state.prefix));
  renderPagination();

  el.up().disabled = state.prefix === '';
  updateUploadButtonState();
}

function uploadWithProgress(
  url: string,
  formData: FormData,
  onProgress: (pct: number) => void,
): Promise<{ status: number; body: unknown }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const csrf = getCsrfToken();
    xhr.open('POST', url);
    if (csrf) xhr.setRequestHeader('X-CSRFToken', csrf);
    xhr.withCredentials = true;

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        onProgress((e.loaded / e.total) * 100);
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        let body: unknown = null;
        try {
          body = JSON.parse(xhr.responseText) as unknown;
        } catch {
          /* ignore parse errors */
        }
        resolve({ status: xhr.status, body });
      } else {
        let detail = `Request failed (${xhr.status})`;
        try {
          const data = JSON.parse(xhr.responseText) as { detail?: unknown };
          if (data?.detail) detail = String(data.detail);
        } catch {
          /* ignore parse errors */
        }
        reject(new Error(detail));
      }
    };
    xhr.onerror = () => reject(new Error('Network error'));
    xhr.send(formData);
  });
}

async function doUpload(): Promise<void> {
  if (!state.vault) return;

  const file = el.uploadFile().files?.[0] ?? null;
  if (!file) return;

  const name = (el.uploadName().value || file.name).trim();
  if (!name) {
    setFlash('Name is required.', 'error');
    return;
  }

  const path = `${state.prefix}${name}`;

  // Show progress bar
  el.uploadProgressWrap().style.display = '';
  el.uploadProgressBar().style.width = '0%';
  el.uploadProgressBar().setAttribute('aria-valuenow', '0');
  el.uploadStatus().textContent = 'Uploading…';
  el.uploadBtn().disabled = true;

  try {
    const form = new FormData();
    form.append('path', path);
    form.append('file', file);

    const result = await uploadWithProgress(
      `/api/v1/files/${encodeURIComponent(state.vault)}/write/`,
      form,
      (pct) => {
        const pctStr = pct.toFixed(0);
        el.uploadProgressBar().style.width = `${pctStr}%`;
        el.uploadProgressBar().setAttribute('aria-valuenow', pctStr);
      },
    );

    el.uploadProgressWrap().style.display = 'none';
    el.uploadProgressBar().style.width = '0%';

    if (result.status === 202) {
      // Async path: file is queued, Celery will write to backend
      el.uploadStatus().textContent = 'Queued — writing to backend…';
      el.uploadFile().value = '';
      el.uploadName().value = '';
      // Fetch pending immediately so the row appears without waiting for the first poll tick
      await fetchPending();
      render([]); // re-render with current entries will be overwritten by next refresh
      void refresh();
      startPendingPoll();
    } else {
      // Sync path: write completed immediately
      el.uploadStatus().textContent = 'Uploaded.';
      setFlash('Upload complete.', 'success');
      el.uploadFile().value = '';
      el.uploadName().value = '';
      await refresh();
    }
  } catch (e) {
    el.uploadProgressWrap().style.display = 'none';
    el.uploadProgressBar().style.width = '0%';
    el.uploadStatus().textContent = '';
    setFlash(e instanceof Error ? e.message : 'Upload failed.', 'error');
  } finally {
    updateUploadButtonState();
  }
}

function goUp(): void {
  if (!state.prefix) return;
  const parts = state.prefix.split('/').filter(Boolean);
  parts.pop();
  state.prefix = parts.length ? `${parts.join('/')}/` : '';
  resetPagination();
  void refresh();
}

async function loadVaults(): Promise<void> {
  const host = el.vaultList();
  host.innerHTML = `<div class="text-muted small">Loading…</div>`;

  const items = await apiJson<ConnectionMeta[]>('/api/v1/files/');

  if (!items.length) {
    host.innerHTML = `<div class="text-muted small">No vault items yet.</div>`;
    state.vault = null;
    state.prefix = '';
    setBrowserHeader();
    setCrumbs();
    render([]);
    return;
  }

  host.innerHTML = '';

  let firstAnchor: HTMLAnchorElement | null = null;

  for (const it of items) {
    const a = document.createElement('a');
    a.href = '#';
    a.className =
      'list-group-item list-group-item-action d-flex align-items-center justify-content-between files-vault-item';
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

    a.addEventListener('click', (e) => {
      e.preventDefault();

      state.vault = it.name;
      state.prefix = '';
      resetPagination();

      // Reset pending state when switching vaults
      stopPendingPoll();
      pendingEntries = [];

      void (async () => {
        // Fetch pending uploads for this vault before refreshing so they show immediately
        await fetchPending();
        void refresh();
        if (pendingEntries.length > 0) {
          startPendingPoll();
        }
      })();

      for (const elItem of Array.from(host.querySelectorAll('.list-group-item'))) {
        elItem.classList.remove('active');
      }
      a.classList.add('active');
    });

    if (!firstAnchor) firstAnchor = a;
    host.appendChild(a);
  }

  if (!state.vault && firstAnchor) firstAnchor.click();
}

/* ----------------------------- Boot ----------------------------- */

document.addEventListener('DOMContentLoaded', async () => {
  await loadVaults();
  setBrowserHeader();
  setCrumbs();
  updateUploadButtonState();

  el.vaultRefresh().addEventListener('click', () => void loadVaults());
  el.refresh().addEventListener('click', () => void refresh());
  el.up().addEventListener('click', goUp);

  el.uploadFile().addEventListener('change', () => {
    const f = el.uploadFile().files?.[0];
    if (f) el.uploadName().value = f.name;
    updateUploadButtonState();
  });

  el.uploadName().addEventListener('input', updateUploadButtonState);
  el.uploadBtn().addEventListener('click', () => void doUpload());
});
