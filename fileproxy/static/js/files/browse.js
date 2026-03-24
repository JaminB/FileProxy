import { qs as qsMaybe, setFlash } from '../utils/dom.js';
import { apiJson } from '../utils/api.js';
import { getCsrfToken } from '../utils/cookies.js';
/* ----------------------------- DOM helpers ----------------------------- */
function mustGet(selector, root = document) {
    const el = qsMaybe(selector, root);
    if (!el)
        throw new Error(`Missing element: ${selector}`);
    return el;
}
const el = {
    vaultList: () => mustGet('#vault-list'),
    entries: () => mustGet('#entries'),
    crumbs: () => mustGet('#path-crumbs'),
    title: () => mustGet('#browser-title'),
    subtitle: () => mustGet('#browser-subtitle'),
    refresh: () => mustGet('#refresh'),
    vaultRefresh: () => mustGet('#vault-refresh'),
    up: () => mustGet('#up'),
    uploadTriggerBtn: () => mustGet('#upload-trigger-btn'),
    uploadFile: () => mustGet('#upload-file'),
    uploadPanelList: () => mustGet('#upload-panel-list'),
    uploadPanelEmpty: () => mustGet('#upload-panel-empty'),
    uploadNameWrap: () => mustGet('#upload-name-wrap'),
    uploadName: () => mustGet('#upload-name'),
    uploadConfirmBtn: () => mustGet('#upload-confirm-btn'),
    pageControls: () => mustGet('#page-controls'),
};
/* ----------------------------- State ----------------------------- */
const state = {
    vault: null,
    prefix: '',
    pageSize: 50,
    cursors: [null],
    page: 0,
    hasNextPage: false,
    sort: null,
};
let pendingEntries = [];
let pendingPollTimer = null;
let pollGeneration = 0;
let currentEntries = [];
let transfers = [];
/* ----------------------------- Small utils ----------------------------- */
function fmtDate(value) {
    if (!value)
        return '—';
    const d = new Date(value);
    if (Number.isNaN(d.getTime()))
        return '—';
    return d.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });
}
function fmtBytes(n) {
    if (n == null || n === 0)
        return '';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let v = n;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) {
        v /= 1024;
        i += 1;
    }
    return i === 0 ? `${v} ${units[i]}` : `${v.toFixed(1)} ${units[i]}`;
}
function fileIcon(name) {
    const ext = name.split('.').pop()?.toLowerCase() ?? '';
    if (['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'bmp'].includes(ext))
        return 'bi-file-earmark-image';
    if (ext === 'pdf')
        return 'bi-file-earmark-pdf';
    if (['doc', 'docx'].includes(ext))
        return 'bi-file-earmark-word';
    if (['xls', 'xlsx', 'csv'].includes(ext))
        return 'bi-file-earmark-excel';
    if (['ppt', 'pptx'].includes(ext))
        return 'bi-file-earmark-slides';
    if (['zip', 'gz', 'tar', 'bz2', '7z', 'rar'].includes(ext))
        return 'bi-file-earmark-zip';
    if (['mp4', 'mov', 'avi', 'mkv', 'webm'].includes(ext))
        return 'bi-file-earmark-play';
    if (['mp3', 'wav', 'ogg', 'flac', 'm4a'].includes(ext))
        return 'bi-file-earmark-music';
    if ([
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
    ].includes(ext))
        return 'bi-file-earmark-code';
    if (['txt', 'md', 'log'].includes(ext))
        return 'bi-file-earmark-text';
    return 'bi-file-earmark';
}
function resetPagination() {
    state.cursors = [null];
    state.page = 0;
    state.hasNextPage = false;
}
/* ----------------------------- UI state ----------------------------- */
function setBrowserHeader() {
    const hasVault = Boolean(state.vault);
    el.up().disabled = !hasVault || state.prefix === '';
    el.refresh().disabled = !hasVault;
    el.uploadTriggerBtn().disabled = !hasVault;
    if (!hasVault) {
        el.title().textContent = 'Select a vault';
        el.subtitle().textContent = '';
        return;
    }
    el.title().textContent = state.vault;
    el.subtitle().textContent = state.prefix ? `/${state.prefix}` : '/';
}
function setCrumbs() {
    const ol = el.crumbs();
    ol.innerHTML = '';
    if (!state.vault) {
        ol.innerHTML = `<li class="breadcrumb-item text-muted">—</li>`;
        return;
    }
    const parts = state.prefix.split('/').filter(Boolean);
    const addCrumbLink = (label, prefix) => {
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
        }
        else {
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
function toEntries(objects, prefix) {
    const folders = new Map();
    const files = [];
    for (const obj of objects) {
        const key = obj.path || '';
        if (!key.startsWith(prefix))
            continue;
        const rest = key.slice(prefix.length);
        if (!rest)
            continue;
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
function sortEntries(entries, sort) {
    const folders = entries.filter((e) => e.kind === 'folder');
    const files = entries.filter((e) => e.kind === 'file');
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
                if (aN)
                    return 1; // nulls always sort to the end regardless of direction
                if (bN)
                    return -1;
                cmp = a.size - b.size;
                break;
            }
            case 'modified': {
                const aN = !a.last_modified;
                const bN = !b.last_modified;
                if (aN && bN) {
                    cmp = 0;
                    break;
                }
                if (aN)
                    return 1; // nulls always sort to the end regardless of direction
                if (bN)
                    return -1;
                cmp = a.last_modified.localeCompare(b.last_modified);
                break;
            }
        }
        return sort.dir === 'asc' ? cmp : -cmp;
    });
    return [...folders, ...files];
}
/* ----------------------------- Pending uploads ----------------------------- */
// Returns true when pendingEntries was successfully refreshed, false on error or
// vault mismatch. Callers must NOT use pendingEntries to make state-transition
// decisions (queued → done) unless this returns true.
async function fetchPending() {
    const vault = state.vault;
    if (!vault) {
        pendingEntries = [];
        return true;
    }
    try {
        const data = await apiJson(`/api/v1/files/${encodeURIComponent(vault)}/pending/`);
        // Discard result if the user switched vaults while the request was in-flight
        if (state.vault !== vault)
            return false;
        pendingEntries = data;
        return true;
    }
    catch {
        return false; // keep stale on error; caller must skip sync
    }
}
function stopPendingPoll() {
    if (pendingPollTimer !== null) {
        clearTimeout(pendingPollTimer);
        pendingPollTimer = null;
    }
    // Increment generation so any in-flight poll() tick sees it is stale
    // and does not re-arm the timer after stop/vault-switch.
    pollGeneration++;
}
function startPendingPoll() {
    if (pendingPollTimer !== null)
        return; // already running
    // Capture the current generation — in-flight ticks from a previous poll
    // loop will have a different (older) generation and will bail out.
    const myGen = ++pollGeneration;
    // Track which paths were pending so we can refresh when they complete
    let prevPaths = new Set(pendingEntries.map((p) => p.path));
    // Use recursive setTimeout so the next tick only fires after the previous
    // one fully completes — prevents overlapping fetches if the request is slow.
    async function poll() {
        if (pollGeneration !== myGen)
            return; // stale — vault switched or poll stopped
        const ok = await fetchPending();
        if (pollGeneration !== myGen)
            return; // vault changed while request was in-flight
        if (!ok) {
            // Fetch failed — skip sync so we don't incorrectly mark queued items done
            if (pollGeneration === myGen) {
                pendingPollTimer = setTimeout(() => void poll(), 4000);
            }
            return;
        }
        const currentPaths = new Set(pendingEntries.map((p) => p.path));
        // Find paths that completed (were pending, now gone)
        const completed = [...prevPaths].filter((path) => !currentPaths.has(path));
        prevPaths = currentPaths;
        // Update the transfer panel
        syncPendingToTransfers();
        // If any file completed, refresh the main listing to show it
        if (completed.length > 0) {
            void refresh();
        }
        // Stop polling when nothing is pending
        if (pendingEntries.length === 0) {
            stopPendingPoll();
            return;
        }
        // Schedule the next poll only if this generation is still active
        if (pollGeneration === myGen) {
            pendingPollTimer = setTimeout(() => void poll(), 4000);
        }
    }
    // Mark as active before the first async tick
    pendingPollTimer = setTimeout(() => void poll(), 4000);
}
/* ----------------------------- Rendering ----------------------------- */
function newTransferId() {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID();
    }
    return `t_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}
function addTransferItem(item) {
    el.uploadPanelEmpty().style.display = 'none';
    const div = document.createElement('div');
    div.className = 'upload-item';
    div.setAttribute('data-transfer-id', item.id);
    // Flex row: info + badge
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
    metaDiv.textContent = item.fileSizeFmt;
    infoDiv.appendChild(nameDiv);
    infoDiv.appendChild(metaDiv);
    const badge = document.createElement('span');
    badge.className = 'upload-item-badge badge';
    flexRow.appendChild(infoDiv);
    flexRow.appendChild(badge);
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
}
function updateTransferItem(item) {
    const node = el.uploadPanelList().querySelector(`[data-transfer-id="${item.id}"]`);
    if (!node)
        return;
    const badge = node.querySelector('.upload-item-badge');
    const bar = node.querySelector('.upload-item-bar');
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
function syncPendingToTransfers() {
    const serverById = new Map(pendingEntries.map((p) => [p.id, p]));
    const serverByPath = new Map(pendingEntries.map((p) => [p.path, p]));
    for (const item of transfers) {
        if (item.status !== 'queued' && item.status !== 'failed')
            continue;
        const serverEntry = (item.serverId ? serverById.get(item.serverId) : undefined) ?? serverByPath.get(item.path);
        if (!serverEntry) {
            item.status = 'done';
        }
        else {
            item.serverId = serverEntry.id;
            item.status = serverEntry.status === 'failed' ? 'failed' : 'queued';
        }
        updateTransferItem(item);
    }
}
function addPendingAsTransfers() {
    const knownPaths = new Set(transfers.map((t) => t.path));
    for (const p of pendingEntries) {
        if (!knownPaths.has(p.path)) {
            const item = {
                id: newTransferId(),
                serverId: p.id,
                fileName: p.path.split('/').pop() || p.path,
                fileSizeFmt: fmtBytes(p.expected_size) || '0 B',
                path: p.path,
                status: p.status === 'failed' ? 'failed' : 'queued',
                progress: 100,
            };
            transfers.push(item);
            addTransferItem(item);
        }
    }
}
function makeFileActions(entry) {
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
    const addItem = (html, onClick, className = 'dropdown-item') => {
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
        if (!state.vault)
            return;
        const url = `/api/v1/files/${encodeURIComponent(state.vault)}/download/?path=${encodeURIComponent(entry.path)}`;
        const a = document.createElement('a');
        a.href = url;
        a.download = entry.name || 'download';
        document.body.appendChild(a);
        a.click();
        a.remove();
    });
    addDivider();
    addItem(`<i class="bi bi-trash me-2"></i>Delete`, async () => {
        if (!state.vault)
            return;
        if (!confirm(`Delete "${entry.path}"?`))
            return;
        try {
            await apiJson(`/api/v1/files/${encodeURIComponent(state.vault)}/object/?path=${encodeURIComponent(entry.path)}`, { method: 'DELETE' });
            setFlash('Deleted.', 'success');
            await refresh();
        }
        catch (err) {
            setFlash(err instanceof Error ? err.message : 'Delete failed.', 'error');
        }
    }, 'dropdown-item text-danger');
    dd.appendChild(toggle);
    dd.appendChild(menu);
    return dd;
}
function render(entries) {
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
        }
        else {
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
function initFileSortHeaders() {
    const thead = document.getElementById('entries-head');
    if (!thead)
        return;
    const updateHeaderAriaSort = () => {
        for (const t of Array.from(thead.querySelectorAll('th[data-sort]'))) {
            const col = t.getAttribute('data-sort');
            const ind = t.querySelector('.sort-indicator');
            if (col === state.sort?.col) {
                t.setAttribute('aria-sort', state.sort.dir === 'asc' ? 'ascending' : 'descending');
                if (ind)
                    ind.textContent = state.sort.dir === 'asc' ? ' ▲' : ' ▼';
            }
            else {
                t.setAttribute('aria-sort', 'none');
                if (ind)
                    ind.textContent = '';
            }
        }
    };
    for (const th of Array.from(thead.querySelectorAll('th[data-sort]'))) {
        const indicator = document.createElement('span');
        indicator.className = 'sort-indicator';
        indicator.setAttribute('aria-hidden', 'true');
        th.appendChild(indicator);
        th.setAttribute('tabindex', '0');
        th.setAttribute('aria-sort', 'none');
        const activate = () => {
            const col = th.getAttribute('data-sort');
            if (state.sort?.col === col) {
                state.sort = { col, dir: state.sort.dir === 'asc' ? 'desc' : 'asc' };
            }
            else {
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
function renderPagination() {
    const host = el.pageControls();
    host.innerHTML = '';
    if (!state.vault)
        return;
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
async function refresh() {
    setBrowserHeader();
    setCrumbs();
    if (!state.vault) {
        render([]);
        renderPagination();
        return;
    }
    const params = new URLSearchParams();
    if (state.prefix)
        params.set('prefix', state.prefix);
    const cursor = state.cursors[state.page];
    if (cursor)
        params.set('cursor', cursor);
    params.set('page_size', String(state.pageSize));
    const page = await apiJson(`/api/v1/files/${encodeURIComponent(state.vault)}/objects/?${params.toString()}`);
    // Store next cursor for forward navigation
    if (page.next_cursor) {
        state.cursors[state.page + 1] = page.next_cursor;
        state.hasNextPage = true;
    }
    else {
        state.hasNextPage = false;
    }
    render(toEntries(page.objects, state.prefix));
    renderPagination();
    el.up().disabled = state.prefix === '';
}
function uploadWithProgress(url, formData, onProgress) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const csrf = getCsrfToken();
        xhr.open('POST', url);
        if (csrf)
            xhr.setRequestHeader('X-CSRFToken', csrf);
        xhr.withCredentials = true;
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                onProgress((e.loaded / e.total) * 100);
            }
        };
        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                let body = null;
                try {
                    body = JSON.parse(xhr.responseText);
                }
                catch {
                    /* ignore parse errors */
                }
                resolve({ status: xhr.status, body });
            }
            else {
                let detail = `Request failed (${xhr.status})`;
                try {
                    const data = JSON.parse(xhr.responseText);
                    if (data?.detail)
                        detail = String(data.detail);
                }
                catch {
                    /* ignore parse errors */
                }
                reject(new Error(detail));
            }
        };
        xhr.onerror = () => reject(new Error('Network error'));
        xhr.send(formData);
    });
}
async function startUpload(files, nameOverride) {
    if (!state.vault)
        return;
    const vault = state.vault;
    const isMulti = files.length > 1;
    el.uploadNameWrap().style.display = 'none';
    el.uploadTriggerBtn().disabled = true;
    // Create transfer items and prepend to panel (newest at top)
    const localItems = files.map((file) => {
        const name = !isMulti && nameOverride ? nameOverride : file.name;
        const item = {
            id: newTransferId(),
            fileName: name,
            fileSizeFmt: fmtBytes(file.size) || '0 B',
            path: `${state.prefix}${name}`,
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
            const result = await uploadWithProgress(`/api/v1/files/${encodeURIComponent(vault)}/write/`, form, (pct) => {
                item.progress = pct;
                updateTransferItem(item);
            });
            item.status = result.status === 202 ? 'queued' : 'done';
            if (result.status === 202)
                anyQueued = true;
        }
        catch (e) {
            item.status = 'failed';
            setFlash(`${item.fileName}: ${e instanceof Error ? e.message : 'Upload failed'}`, 'error');
        }
        item.progress = 100;
        updateTransferItem(item);
    }
    el.uploadFile().value = '';
    el.uploadTriggerBtn().disabled = !state.vault;
    // If the user switched vaults while these uploads were in flight, skip
    // post-upload work (fetchPending/refresh) so we don't affect the new vault.
    if (state.vault !== vault)
        return;
    if (anyQueued) {
        const ok = await fetchPending();
        if (ok)
            syncPendingToTransfers();
        startPendingPoll();
    }
    else if (localItems.every((t) => t.status === 'done')) {
        setFlash('Upload complete.', 'success');
        await refresh();
    }
}
function goUp() {
    if (!state.prefix)
        return;
    const parts = state.prefix.split('/').filter(Boolean);
    parts.pop();
    state.prefix = parts.length ? `${parts.join('/')}/` : '';
    resetPagination();
    void refresh();
}
async function loadVaults() {
    const host = el.vaultList();
    host.innerHTML = `<div class="text-muted small">Loading…</div>`;
    const items = await apiJson('/api/v1/files/');
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
    let firstAnchor = null;
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
            // Clear all transfers when switching vaults to prevent cross-vault state mixing.
            // In-flight XHRs still complete in the background but are not shown in the new vault's panel.
            transfers = [];
            for (const node of Array.from(el.uploadPanelList().querySelectorAll('.upload-item'))) {
                node.remove();
            }
            el.uploadPanelEmpty().style.display = '';
            void (async () => {
                // Fetch pending uploads for this vault before refreshing so they show immediately
                const ok = await fetchPending();
                if (ok)
                    addPendingAsTransfers();
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
        if (!firstAnchor)
            firstAnchor = a;
        host.appendChild(a);
    }
    if (!state.vault && firstAnchor)
        firstAnchor.click();
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
        if (!state.vault)
            return;
        el.uploadFile().click();
    });
    el.uploadFile().addEventListener('change', () => {
        const files = Array.from(el.uploadFile().files ?? []);
        if (!files.length)
            return;
        if (files.length === 1) {
            el.uploadName().value = files[0].name;
            el.uploadNameWrap().style.display = '';
        }
        else {
            void startUpload(files, '');
        }
    });
    el.uploadConfirmBtn().addEventListener('click', () => {
        const files = Array.from(el.uploadFile().files ?? []);
        if (!files.length)
            return;
        el.uploadConfirmBtn().disabled = true;
        void startUpload(files, el.uploadName().value.trim() || files[0].name).finally(() => {
            el.uploadConfirmBtn().disabled = false;
        });
    });
});
//# sourceMappingURL=browse.js.map