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

type BackendObject = {
  name: string;
  path: string;
  size: number | null;
  last_modified: string | null;
};

type ObjectPage = { objects: BackendObject[]; next_cursor: string | null };

type SortState = { col: 'name' | 'path' | 'size' | 'modified'; dir: 'asc' | 'desc' };

type Entry =
  | { kind: 'folder'; name: string; path: string }
  | { kind: 'file'; name: string; path: string; size: number | null; last_modified: string | null };

type PendingEntry = {
  id: string;
  path: string;
  expected_size: number;
  status: 'pending' | 'uploading' | 'failed';
  created_at: string;
};

type TransferStatus = 'uploading' | 'queued' | 'done' | 'failed';

type TransferItem = {
  id: string;
  serverId?: string;
  fileName: string;
  fileSizeFmt: string;
  path: string;
  vault: string;
  status: TransferStatus;
  progress: number;
  cancel?: () => void;
};

type State = {
  vault: string | null;
  prefix: string;
  pageSize: number; // 25 | 50 | 100 | 200
  cursors: Array<string | null>; // cursors[i] = cursor needed to fetch page i; cursors[0] = null
  page: number; // current 0-indexed page
  hasNextPage: boolean;
  sort: SortState | null;
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

  uploadTriggerBtn: () => mustGet<HTMLButtonElement>('#upload-trigger-btn'),
  uploadFile: () => mustGet<HTMLInputElement>('#upload-file'),
  uploadPanelList: () => mustGet<HTMLElement>('#upload-panel-list'),
  uploadPanelEmpty: () => mustGet<HTMLElement>('#upload-panel-empty'),

  uploadOverlay: () => mustGet<HTMLElement>('#upload-overlay'),
  uploadOverlaySummary: () => mustGet<HTMLElement>('#upload-overlay-summary'),
  uploadOverlayToggle: () => mustGet<HTMLButtonElement>('#upload-overlay-toggle'),
  uploadOverlayDismiss: () => mustGet<HTMLButtonElement>('#upload-overlay-dismiss'),
  uploadOverlayBody: () => mustGet<HTMLElement>('#upload-overlay-body'),

  uploadNameModal: () => mustGet<HTMLElement>('#upload-name-modal'),
  uploadNameInput: () => mustGet<HTMLInputElement>('#upload-name-input'),
  uploadNameConfirm: () => mustGet<HTMLButtonElement>('#upload-name-confirm'),

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
  sort: null,
};

const pendingByVault = new Map<string, PendingEntry[]>();
const vaultPolls = new Map<string, { gen: number; timer: ReturnType<typeof setTimeout> | null }>();
let currentEntries: Entry[] = [];
let transfers: TransferItem[] = [];

/* ----------------------------- Small utils ----------------------------- */

function fmtDate(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

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

function setBrowserHeader(): void {
  const hasVault = Boolean(state.vault);

  el.up().disabled = !hasVault || state.prefix === '';
  el.refresh().disabled = !hasVault;
  el.uploadTriggerBtn().disabled = !hasVault;

  if (!hasVault) {
    el.title().textContent = 'Select a vault';
    el.subtitle().textContent = '';
    return;
  }

  el.title().textContent = state.vault!;
  el.subtitle().textContent = state.prefix ? `/${state.prefix}` : '/';
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

    files.push({
      kind: 'file',
      name: rest,
      path: key,
      size: obj.size ?? null,
      last_modified: obj.last_modified ?? null,
    });
  }

  return [...folders.values(), ...files];
}

function sortEntries(entries: Entry[], sort: SortState | null): Entry[] {
  const folders = entries.filter((e) => e.kind === 'folder');
  const files = entries.filter((e) => e.kind === 'file') as Extract<Entry, { kind: 'file' }>[];

  // Default: sort folders and files alphabetically by name
  if (!sort) {
    folders.sort((a, b) => a.name.localeCompare(b.name));
    files.sort((a, b) => a.name.localeCompare(b.name));
    return [...folders, ...files];
  }

  folders.sort((a, b) => a.name.localeCompare(b.name));
  files.sort((a, b) => {
    let cmp = 0;
    switch (sort.col) {
      case 'name':
        cmp = a.name.localeCompare(b.name);
        break;
      case 'path':
        cmp = a.path.localeCompare(b.path);
        break;
      case 'size': {
        const aN = a.size == null;
        const bN = b.size == null;
        if (aN && bN) {
          cmp = 0;
          break;
        }
        if (aN) return 1; // nulls always sort to the end regardless of direction
        if (bN) return -1;
        cmp = a.size! - b.size!;
        break;
      }
      case 'modified': {
        const aN = !a.last_modified;
        const bN = !b.last_modified;
        if (aN && bN) {
          cmp = 0;
          break;
        }
        if (aN) return 1; // nulls always sort to the end regardless of direction
        if (bN) return -1;
        cmp = a.last_modified!.localeCompare(b.last_modified!);
        break;
      }
    }
    return sort.dir === 'asc' ? cmp : -cmp;
  });

  return [...folders, ...files];
}

/* ----------------------------- Pending uploads ----------------------------- */

// Fetches pending entries for a specific vault and stores in pendingByVault.
// Returns true on success, false on network error (stale data preserved).
async function fetchPendingForVault(vault: string): Promise<boolean> {
  try {
    const data = await apiJson<PendingEntry[]>(
      `/api/v1/files/${encodeURIComponent(vault)}/pending/`,
    );
    pendingByVault.set(vault, data);
    return true;
  } catch {
    return false; // keep stale on error
  }
}

function stopVaultPoll(vault: string): void {
  const poll = vaultPolls.get(vault);
  if (!poll) return;
  if (poll.timer !== null) {
    clearTimeout(poll.timer);
    poll.timer = null;
  }
  poll.gen++;
}

function startVaultPoll(vault: string): void {
  stopVaultPoll(vault);

  const entry = { gen: 1, timer: null as ReturnType<typeof setTimeout> | null };
  vaultPolls.set(vault, entry);
  const myGen = entry.gen;

  let prevPaths = new Set((pendingByVault.get(vault) ?? []).map((p) => p.path));

  async function poll(): Promise<void> {
    const cur = vaultPolls.get(vault);
    if (!cur || cur.gen !== myGen) return;

    const ok = await fetchPendingForVault(vault);

    const cur2 = vaultPolls.get(vault);
    if (!cur2 || cur2.gen !== myGen) return;

    if (!ok) {
      cur2.timer = setTimeout(() => void poll(), 4000);
      return;
    }

    const entries = pendingByVault.get(vault) ?? [];
    const currentPaths = new Set(entries.map((p) => p.path));
    const completed = [...prevPaths].filter((path) => !currentPaths.has(path));
    prevPaths = currentPaths;

    syncPendingToTransfers();

    if (completed.length > 0 && state.vault === vault) {
      void refresh();
    }

    if (entries.length === 0) {
      stopVaultPoll(vault);
      return;
    }

    cur2.timer = setTimeout(() => void poll(), 4000);
  }

  entry.timer = setTimeout(() => void poll(), 4000);
}

/* ----------------------------- Rendering ----------------------------- */

function newTransferId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `t_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function removeTransferItem(id: string): void {
  transfers = transfers.filter((t) => t.id !== id);
  el.uploadPanelList().querySelector(`[data-transfer-id="${id}"]`)?.remove();
  if (transfers.length === 0) {
    el.uploadPanelEmpty().style.display = '';
  }
  syncOverlayVisibility();
}

function syncOverlayVisibility(): void {
  const overlay = el.uploadOverlay();
  const summary = el.uploadOverlaySummary();
  const dismiss = el.uploadOverlayDismiss();

  if (transfers.length === 0) {
    overlay.style.display = 'none';
    return;
  }

  overlay.style.display = '';

  const active = transfers.filter((t) => t.status === 'uploading' || t.status === 'queued').length;
  if (active > 0) {
    summary.textContent = `${active} uploading`;
    dismiss.style.display = 'none';
  } else {
    summary.textContent = `${transfers.length} transfer${transfers.length !== 1 ? 's' : ''}`;
    dismiss.style.display = '';
  }
}

function addTransferItem(item: TransferItem): void {
  el.uploadPanelEmpty().style.display = 'none';

  const div = document.createElement('div');
  div.className = 'upload-item';
  div.setAttribute('data-transfer-id', item.id);

  // Flex row: info + badge + cancel
  const flexRow = document.createElement('div');
  flexRow.className = 'd-flex align-items-start justify-content-between gap-2';

  const infoDiv = document.createElement('div');
  infoDiv.className = 'upload-item-info flex-grow-1 overflow-hidden';

  const nameDiv = document.createElement('div');
  nameDiv.className = 'upload-item-name text-truncate small fw-medium';
  nameDiv.setAttribute('title', item.fileName);
  nameDiv.textContent = item.fileName;

  const metaDiv = document.createElement('div');
  metaDiv.className = 'upload-item-meta text-muted';
  metaDiv.style.fontSize = '0.72rem';
  metaDiv.textContent = `${item.fileSizeFmt} · ${item.vault}`;

  infoDiv.appendChild(nameDiv);
  infoDiv.appendChild(metaDiv);

  const rightDiv = document.createElement('div');
  rightDiv.className = 'd-flex align-items-center gap-1 flex-shrink-0';

  const badge = document.createElement('span');
  badge.className = 'upload-item-badge badge';

  const cancelBtn = document.createElement('button');
  cancelBtn.type = 'button';
  cancelBtn.className = 'upload-item-cancel btn-close';
  cancelBtn.setAttribute('aria-label', 'Cancel or dismiss');
  cancelBtn.addEventListener('click', () => {
    if (item.cancel) {
      item.cancel();
    } else {
      removeTransferItem(item.id);
    }
  });

  rightDiv.appendChild(badge);
  rightDiv.appendChild(cancelBtn);

  flexRow.appendChild(infoDiv);
  flexRow.appendChild(rightDiv);

  // Progress bar
  const progressOuter = document.createElement('div');
  progressOuter.className = 'progress mt-1';
  progressOuter.style.height = '4px';

  const bar = document.createElement('div');
  bar.className = 'upload-item-bar progress-bar';
  bar.setAttribute('role', 'progressbar');
  bar.style.width = '0%';
  bar.setAttribute('aria-valuenow', '0');
  bar.setAttribute('aria-valuemin', '0');
  bar.setAttribute('aria-valuemax', '100');

  progressOuter.appendChild(bar);
  div.appendChild(flexRow);
  div.appendChild(progressOuter);

  // Prepend so newest appears at the top
  el.uploadPanelList().insertBefore(div, el.uploadPanelList().firstChild);
  updateTransferItem(item);
  syncOverlayVisibility();
}

function updateTransferItem(item: TransferItem): void {
  const node = el.uploadPanelList().querySelector<HTMLElement>(`[data-transfer-id="${item.id}"]`);
  if (!node) return;
  const badge = node.querySelector<HTMLElement>('.upload-item-badge')!;
  const bar = node.querySelector<HTMLElement>('.upload-item-bar')!;

  const pct = `${Math.round(item.progress)}%`;
  bar.style.width = pct;
  bar.setAttribute('aria-valuenow', String(Math.round(item.progress)));

  badge.className = 'upload-item-badge badge';
  bar.className = 'upload-item-bar progress-bar';

  switch (item.status) {
    case 'uploading':
      badge.classList.add('bg-primary');
      badge.textContent = 'Uploading';
      break;
    case 'queued':
      badge.classList.add('bg-warning', 'text-dark');
      badge.textContent = 'Queued';
      bar.classList.add('bg-warning');
      bar.style.width = '100%';
      break;
    case 'done':
      badge.classList.add('bg-success');
      badge.textContent = 'Done';
      bar.classList.add('bg-success');
      bar.style.width = '100%';
      break;
    case 'failed':
      badge.classList.add('bg-danger');
      badge.textContent = 'Failed';
      bar.classList.add('bg-danger');
      bar.style.width = '100%';
      break;
  }
}

function syncPendingToTransfers(): void {
  for (const [vault, entries] of pendingByVault) {
    const serverById = new Map(entries.map((p) => [p.id, p]));
    const serverByPath = new Map(entries.map((p) => [p.path, p]));

    for (const item of transfers) {
      if (item.vault !== vault) continue;
      if (item.status !== 'queued' && item.status !== 'failed') continue;
      const serverEntry =
        (item.serverId ? serverById.get(item.serverId) : undefined) ?? serverByPath.get(item.path);

      if (!serverEntry) {
        item.status = 'done';
      } else {
        item.serverId = serverEntry.id;
        item.status = serverEntry.status === 'failed' ? 'failed' : 'queued';
      }
      updateTransferItem(item);
    }
  }
  syncOverlayVisibility();
}

function addPendingAsTransfers(vault: string): void {
  const entries = pendingByVault.get(vault) ?? [];
  const knownPaths = new Set(transfers.filter((t) => t.vault === vault).map((t) => t.path));
  for (const p of entries) {
    if (!knownPaths.has(p.path)) {
      const item: TransferItem = {
        id: newTransferId(),
        serverId: p.id,
        fileName: p.path.split('/').pop() || p.path,
        fileSizeFmt: fmtBytes(p.expected_size) || '0 B',
        path: p.path,
        vault,
        status: p.status === 'failed' ? 'failed' : 'queued',
        progress: 100,
      };
      transfers.push(item);
      addTransferItem(item);
    }
  }
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

function render(entries: Entry[]): void {
  currentEntries = entries;
  const tbody = el.entries();
  tbody.innerHTML = '';

  if (!state.vault) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-muted small">Choose a vault from the left to start browsing.</td></tr>`;
    return;
  }

  if (!entries.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-muted small">This folder is empty.</td></tr>`;
    return;
  }

  const sorted = sortEntries(entries, state.sort);

  for (const entry of sorted) {
    const tr = document.createElement('tr');

    const tdName = document.createElement('td');
    const tdPath = document.createElement('td');
    const tdSize = document.createElement('td');
    const tdModified = document.createElement('td');
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
      tdModified.textContent = '—';
    } else {
      const icon = fileIcon(entry.name);
      const iconEl = document.createElement('i');
      iconEl.className = `bi ${icon} me-2 opacity-75`;
      iconEl.setAttribute('aria-hidden', 'true');
      tdName.appendChild(iconEl);
      tdName.appendChild(document.createTextNode(entry.name));
      tdPath.textContent = entry.path;
      tdSize.textContent = fmtBytes(entry.size);
      tdModified.textContent = fmtDate(entry.last_modified);
      tdAct.appendChild(makeFileActions(entry));
    }

    tr.appendChild(tdName);
    tr.appendChild(tdPath);
    tr.appendChild(tdSize);
    tr.appendChild(tdModified);
    tr.appendChild(tdAct);
    tbody.appendChild(tr);
  }
}

function initFileSortHeaders(): void {
  const thead = document.getElementById('entries-head');
  if (!thead) return;

  const updateHeaderAriaSort = () => {
    for (const t of Array.from(thead.querySelectorAll<HTMLElement>('th[data-sort]'))) {
      const col = t.getAttribute('data-sort');
      const ind = t.querySelector('.sort-indicator');
      if (col === state.sort?.col) {
        t.setAttribute('aria-sort', state.sort.dir === 'asc' ? 'ascending' : 'descending');
        if (ind) ind.textContent = state.sort.dir === 'asc' ? ' ▲' : ' ▼';
      } else {
        t.setAttribute('aria-sort', 'none');
        if (ind) ind.textContent = '';
      }
    }
  };

  for (const th of Array.from(thead.querySelectorAll<HTMLElement>('th[data-sort]'))) {
    const indicator = document.createElement('span');
    indicator.className = 'sort-indicator';
    indicator.setAttribute('aria-hidden', 'true');
    th.appendChild(indicator);

    th.setAttribute('tabindex', '0');
    th.setAttribute('aria-sort', 'none');

    const activate = () => {
      const col = th.getAttribute('data-sort') as SortState['col'];
      if (state.sort?.col === col) {
        state.sort = { col, dir: state.sort.dir === 'asc' ? 'desc' : 'asc' };
      } else {
        state.sort = { col, dir: 'asc' };
      }
      updateHeaderAriaSort();
      render(currentEntries);
    };

    th.addEventListener('click', activate);
    th.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        activate();
      }
    });
  }
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
}

function uploadWithProgress(
  url: string,
  formData: FormData,
  onProgress: (pct: number) => void,
  onCancel?: (cancelFn: () => void) => void,
): Promise<{ status: number; body: unknown }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const csrf = getCsrfToken();
    xhr.open('POST', url);
    if (csrf) xhr.setRequestHeader('X-CSRFToken', csrf);
    xhr.withCredentials = true;

    if (onCancel) onCancel(() => xhr.abort());

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        onProgress((e.loaded / e.total) * 100);
      }
    };

    xhr.onabort = () => resolve({ status: 0, body: null });

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

async function startUpload(files: File[], nameOverride: string, vault: string): Promise<void> {
  const isMulti = files.length > 1;

  el.uploadTriggerBtn().disabled = true;

  // Create transfer items and prepend to panel (newest at top)
  const localItems: TransferItem[] = files.map((file) => {
    const name = !isMulti && nameOverride ? nameOverride : file.name;
    const item: TransferItem = {
      id: newTransferId(),
      fileName: name,
      fileSizeFmt: fmtBytes(file.size) || '0 B',
      path: `${state.prefix}${name}`,
      vault,
      status: 'uploading',
      progress: 0,
    };
    transfers.push(item);
    addTransferItem(item);
    return item;
  });

  let anyQueued = false;

  for (const [idx, file] of files.entries()) {
    const item = localItems[idx];
    try {
      const form = new FormData();
      form.append('path', item.path);
      form.append('file', file);
      const result = await uploadWithProgress(
        `/api/v1/files/${encodeURIComponent(vault)}/write/`,
        form,
        (pct) => {
          item.progress = pct;
          updateTransferItem(item);
        },
        (cancelFn) => {
          item.cancel = cancelFn;
        },
      );
      if (result.status === 0) {
        // Aborted by user — remove from panel
        removeTransferItem(item.id);
        continue;
      }
      item.cancel = undefined;
      item.status = result.status === 202 ? 'queued' : 'done';
      if (result.status === 202) anyQueued = true;
    } catch (e) {
      item.cancel = undefined;
      item.status = 'failed';
      setFlash(`${item.fileName}: ${e instanceof Error ? e.message : 'Upload failed'}`, 'error');
    }
    item.progress = 100;
    updateTransferItem(item);
  }

  el.uploadFile().value = '';
  el.uploadTriggerBtn().disabled = !state.vault;

  if (anyQueued) {
    const ok = await fetchPendingForVault(vault);
    if (ok) syncPendingToTransfers();
    startVaultPoll(vault);
  } else if (localItems.every((t) => t.status === 'done')) {
    setFlash('Upload complete.', 'success');
    if (state.vault === vault) await refresh();
  }

  syncOverlayVisibility();
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

      void (async () => {
        // Fetch pending uploads for this vault so in-progress server-side uploads appear immediately
        const ok = await fetchPendingForVault(it.name);
        if (ok) addPendingAsTransfers(it.name);
        void refresh();
        if ((pendingByVault.get(it.name) ?? []).length > 0) {
          startVaultPoll(it.name);
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
  initFileSortHeaders();

  await loadVaults();
  setBrowserHeader();
  setCrumbs();

  el.vaultRefresh().addEventListener('click', () => void loadVaults());
  el.refresh().addEventListener('click', () => void refresh());
  el.up().addEventListener('click', goUp);

  el.uploadTriggerBtn().addEventListener('click', () => {
    if (!state.vault) return;
    el.uploadFile().click();
  });

  // File picker → single file shows rename modal, multi-file uploads directly
  el.uploadFile().addEventListener('change', () => {
    const files = Array.from(el.uploadFile().files ?? []);
    if (!files.length || !state.vault) return;
    if (files.length === 1) {
      el.uploadNameInput().value = files[0].name;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const bsModal = new (window as any).bootstrap.Modal(el.uploadNameModal());
      bsModal.show();
    } else {
      void startUpload(files, '', state.vault);
    }
  });

  // Rename modal confirm
  el.uploadNameConfirm().addEventListener('click', () => {
    const files = Array.from(el.uploadFile().files ?? []);
    if (!files.length || !state.vault) return;
    const name = el.uploadNameInput().value.trim() || files[0].name;
    const vault = state.vault;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const bsModal = (window as any).bootstrap.Modal.getInstance(el.uploadNameModal());
    bsModal?.hide();
    void startUpload(files, name, vault);
  });

  function toggleOverlay(): void {
    const overlay = el.uploadOverlay();
    overlay.classList.toggle('collapsed');
    const icon = el.uploadOverlayToggle().querySelector('i');
    if (icon) {
      icon.className = overlay.classList.contains('collapsed')
        ? 'bi bi-chevron-up'
        : 'bi bi-chevron-down';
    }
  }

  // Overlay toggle button
  el.uploadOverlayToggle().addEventListener('click', (e) => {
    e.stopPropagation();
    toggleOverlay();
  });

  // Overlay header click also toggles
  el.uploadOverlay()
    .querySelector('.upload-overlay-header')
    ?.addEventListener('click', () => {
      toggleOverlay();
    });

  // Dismiss button hides overlay (transfers preserved in memory)
  el.uploadOverlayDismiss().addEventListener('click', (e) => {
    e.stopPropagation();
    el.uploadOverlay().style.display = 'none';
  });
});
