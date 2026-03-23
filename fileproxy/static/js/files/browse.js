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
    uploadFile: () => mustGet('#upload-file'),
    uploadName: () => mustGet('#upload-name'),
    uploadNameWrap: () => mustGet('#upload-name-wrap'),
    uploadBtn: () => mustGet('#upload'),
    uploadHint: () => mustGet('#upload-hint'),
    uploadStatus: () => mustGet('#upload-status'),
    uploadProgressWrap: () => mustGet('#upload-progress-wrap'),
    uploadProgressBar: () => mustGet('#upload-progress-bar'),
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
function setUploadEnabled(enabled) {
    el.uploadFile().disabled = !enabled;
    el.uploadName().disabled = !enabled;
    el.uploadBtn().disabled = !enabled;
}
function updateUploadNameVisibility() {
    const count = el.uploadFile().files?.length ?? 0;
    el.uploadNameWrap().style.display = count > 1 ? 'none' : '';
}
function updateUploadButtonState() {
    const hasFile = (el.uploadFile().files?.length ?? 0) > 0;
    el.uploadBtn().disabled = !(state.vault && hasFile);
}
function setBrowserHeader() {
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
    el.title().textContent = state.vault;
    el.subtitle().textContent = state.prefix ? `/${state.prefix}` : '/';
    el.uploadHint().textContent = state.prefix
        ? `Uploading into /${state.prefix}`
        : 'Uploading into /';
    setUploadEnabled(true);
    updateUploadButtonState();
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
async function fetchPending() {
    const vault = state.vault;
    if (!vault)
        return [];
    try {
        const data = await apiJson(`/api/v1/files/${encodeURIComponent(vault)}/pending/`);
        // Discard result if the user switched vaults while the request was in-flight
        if (state.vault !== vault)
            return pendingEntries;
        pendingEntries = data;
        return data;
    }
    catch {
        return pendingEntries; // keep stale on error
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
        const current = await fetchPending();
        if (pollGeneration !== myGen)
            return; // vault changed while request was in-flight
        const currentPaths = new Set(current.map((p) => p.path));
        // Find paths that completed (were pending, now gone)
        const completed = [...prevPaths].filter((path) => !currentPaths.has(path));
        prevPaths = currentPaths;
        // Re-render pending rows
        renderWithPending(el.entries());
        // If any file completed, refresh the main listing to show it
        if (completed.length > 0) {
            void refresh();
        }
        // Stop polling when nothing is pending
        if (current.length === 0) {
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
function makePendingRow(p) {
    const tr = document.createElement('tr');
    const isFailed = p.status === 'failed';
    tr.className = isFailed ? 'table-danger' : 'table-warning';
    const filename = p.path.split('/').pop() || p.path;
    const tdName = document.createElement('td');
    const iconEl = document.createElement('i');
    iconEl.className = isFailed
        ? 'bi bi-exclamation-triangle me-2 text-danger opacity-75'
        : 'bi bi-hourglass-split me-2 text-warning opacity-75';
    const filenameEl = document.createElement('em');
    filenameEl.className = 'text-muted';
    filenameEl.textContent = filename;
    tdName.appendChild(iconEl);
    tdName.appendChild(filenameEl);
    const tdPath = document.createElement('td');
    const pathSpan = document.createElement('span');
    pathSpan.className = 'text-muted';
    pathSpan.textContent = p.path;
    tdPath.appendChild(pathSpan);
    const tdSize = document.createElement('td');
    tdSize.textContent = fmtBytes(p.expected_size);
    const tdModified = document.createElement('td');
    tdModified.textContent = '—';
    const tdAct = document.createElement('td');
    tdAct.className = 'text-end';
    if (isFailed) {
        tdAct.innerHTML = `<span class="badge bg-danger">Failed</span>`;
    }
    else {
        tdAct.innerHTML = `<span class="badge bg-warning text-dark">Pending</span>`;
    }
    tr.appendChild(tdName);
    tr.appendChild(tdPath);
    tr.appendChild(tdSize);
    tr.appendChild(tdModified);
    tr.appendChild(tdAct);
    return tr;
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
function renderWithPending(tbody) {
    // Remove existing pending rows (rows with data-pending attribute)
    for (const row of Array.from(tbody.querySelectorAll('tr[data-pending]'))) {
        row.remove();
    }
    if (pendingEntries.length === 0)
        return;
    // Remove the "empty folder" placeholder row if present — it should not
    // coexist with pending rows (the folder is not actually empty).
    for (const row of Array.from(tbody.querySelectorAll('tr'))) {
        if (row.querySelector('td[colspan]')) {
            row.remove();
        }
    }
    // Only show pending entries whose path is under the currently-browsed prefix
    // (mirrors the toEntries() prefix filter so uploads elsewhere don't pollute the view).
    const visible = pendingEntries.filter((p) => p.path.startsWith(state.prefix));
    if (visible.length === 0)
        return;
    // Prepend pending rows
    const frag = document.createDocumentFragment();
    for (const p of visible) {
        const row = makePendingRow(p);
        row.setAttribute('data-pending', p.id);
        frag.appendChild(row);
    }
    tbody.insertBefore(frag, tbody.firstChild);
}
function render(entries) {
    currentEntries = entries;
    const tbody = el.entries();
    tbody.innerHTML = '';
    if (!state.vault) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-muted small">Choose a vault from the left to start browsing.</td></tr>`;
        return;
    }
    if (!entries.length && !pendingEntries.length) {
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
    // Prepend pending rows on top
    renderWithPending(tbody);
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
    updateUploadButtonState();
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
async function doUpload() {
    if (!state.vault)
        return;
    const files = Array.from(el.uploadFile().files ?? []);
    if (!files.length)
        return;
    const isMulti = files.length > 1;
    // For single file, respect the name override; for multi, use each file's name
    if (!isMulti) {
        const name = (el.uploadName().value || files[0].name).trim();
        if (!name) {
            setFlash('Name is required.', 'error');
            return;
        }
    }
    setUploadEnabled(false);
    el.uploadProgressWrap().style.display = '';
    el.uploadProgressBar().style.width = '5%';
    el.uploadProgressBar().setAttribute('aria-valuenow', '5');
    try {
        let anyQueued = false;
        let successCount = 0;
        const errors = [];
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const name = isMulti ? file.name : (el.uploadName().value || file.name).trim();
            const path = `${state.prefix}${name}`;
            el.uploadStatus().textContent = isMulti
                ? `Uploading ${i + 1} of ${files.length}: ${file.name}…`
                : 'Uploading…';
            try {
                const form = new FormData();
                form.append('path', path);
                form.append('file', file);
                const result = await uploadWithProgress(`/api/v1/files/${encodeURIComponent(state.vault)}/write/`, form, (pct) => {
                    // For multi-file, show overall progress across files
                    const overall = ((i + pct / 100) / files.length) * 100;
                    const pctStr = (isMulti ? overall : pct).toFixed(0);
                    el.uploadProgressBar().style.width = `${pctStr}%`;
                    el.uploadProgressBar().setAttribute('aria-valuenow', pctStr);
                });
                if (result.status === 202) {
                    anyQueued = true;
                }
                successCount++;
            }
            catch (e) {
                errors.push(`${file.name}: ${e instanceof Error ? e.message : 'Upload failed'}`);
            }
        }
        el.uploadProgressBar().style.width = '100%';
        el.uploadProgressBar().setAttribute('aria-valuenow', '100');
        await new Promise((r) => setTimeout(r, 300));
        el.uploadProgressWrap().style.display = 'none';
        el.uploadProgressBar().style.width = '0%';
        el.uploadProgressBar().setAttribute('aria-valuenow', '0');
        el.uploadFile().value = '';
        el.uploadName().value = '';
        updateUploadNameVisibility();
        if (errors.length) {
            setFlash(errors.join('; '), 'error');
        }
        if (anyQueued) {
            el.uploadStatus().textContent =
                successCount > 1
                    ? `${successCount} files queued — writing to backend…`
                    : 'Queued — writing to backend…';
            await fetchPending();
            renderWithPending(el.entries());
            void refresh();
            startPendingPoll();
        }
        else if (successCount > 0) {
            el.uploadStatus().textContent =
                successCount > 1 ? `${successCount} files uploaded.` : 'Uploaded.';
            if (!errors.length)
                setFlash('Upload complete.', 'success');
            await refresh();
        }
    }
    finally {
        el.uploadProgressWrap().style.display = 'none';
        el.uploadProgressBar().style.width = '0%';
        el.uploadProgressBar().setAttribute('aria-valuenow', '0');
        setUploadEnabled(true);
        updateUploadButtonState();
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
    updateUploadButtonState();
    el.vaultRefresh().addEventListener('click', () => void loadVaults());
    el.refresh().addEventListener('click', () => void refresh());
    el.up().addEventListener('click', goUp);
    el.uploadFile().addEventListener('change', () => {
        const files = el.uploadFile().files;
        // For single-file selection, pre-fill the name field
        if (files?.length === 1)
            el.uploadName().value = files[0].name;
        updateUploadNameVisibility();
        updateUploadButtonState();
    });
    el.uploadName().addEventListener('input', updateUploadButtonState);
    el.uploadBtn().addEventListener('click', () => void doUpload());
});
//# sourceMappingURL=browse.js.map