import { setFlash } from '../../utils/dom.js';
const KIND_META = {
    aws_s3: { label: 'Amazon S3', src: '/static/images/logos/s3.svg' },
    gdrive_oauth2: { label: 'Google Drive', src: '/static/images/logos/gdrive.svg' },
    dropbox_oauth2: { label: 'Dropbox', src: '/static/images/logos/dropbox.png' },
};
function qs(selector, root = document) {
    const el = root.querySelector(selector);
    if (!el)
        throw new Error(`Missing element: ${selector}`);
    return el;
}
function getItemId() {
    const el = document.getElementById('connection-id');
    if (!el)
        throw new Error('Missing connection-id script tag');
    const s = JSON.parse(el.textContent || '""');
    if (typeof s !== 'string' || !s)
        throw new Error('Invalid item id');
    return s;
}
function getCSRFToken() {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : null;
}
async function api(path, opts = {}) {
    const headers = new Headers(opts.headers || {});
    headers.set('Accept', 'application/json');
    const csrf = getCSRFToken();
    const method = (opts.method || 'GET').toUpperCase();
    if (csrf && method !== 'GET')
        headers.set('X-CSRFToken', csrf);
    if (opts.body && !headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
    }
    const resp = await fetch(path, {
        credentials: 'same-origin',
        ...opts,
        headers,
    });
    if (!resp.ok) {
        let msg = `${resp.status} ${resp.statusText}`;
        try {
            const j = await resp.json();
            msg = typeof j?.detail === 'string' ? j.detail : JSON.stringify(j);
        }
        catch {
            // ignore
        }
        throw new Error(msg);
    }
    // Some endpoints (DELETE) may return empty body
    const text = await resp.text();
    return (text ? JSON.parse(text) : {});
}
function fmtDate(iso) {
    if (!iso)
        return 'Never';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime()))
        return iso;
    return d.toLocaleString();
}
function render(item) {
    qs('#item-title').textContent = item.name;
    qs('#meta-name').textContent = item.name;
    const kindEl = qs('#meta-kind');
    const km = KIND_META[item.kind ?? ''];
    if (km) {
        const img = document.createElement('img');
        img.src = km.src;
        img.alt = '';
        img.width = 14;
        img.height = 14;
        img.className = 'me-1 opacity-75';
        img.setAttribute('aria-hidden', 'true');
        kindEl.innerHTML = '';
        kindEl.appendChild(img);
        kindEl.appendChild(document.createTextNode(km.label));
    }
    else {
        kindEl.textContent = item.kind;
    }
    qs('#meta-created').textContent = fmtDate(item.created_at);
    qs('#meta-updated').textContent = fmtDate(item.updated_at);
    qs('#meta-rotated').textContent = fmtDate(item.rotated_at);
    qs('#meta-id').textContent = String(item.id);
    qs('#edit-name').value = item.name;
}
function showEdit(show) {
    qs('#edit-panel').style.display = show ? 'block' : 'none';
}
document.addEventListener('DOMContentLoaded', async () => {
    const itemId = getItemId();
    const btnTest = qs('#btn-test');
    const btnEdit = qs('#btn-edit');
    const btnDelete = qs('#btn-delete');
    const btnSave = qs('#btn-save');
    const btnCancelEdit = qs('#btn-cancel-edit');
    const editName = qs('#edit-name');
    let current = null;
    async function load() {
        try {
            const item = await api(`/api/v1/connections/${itemId}/`);
            current = item;
            render(item);
        }
        catch (e) {
            setFlash(`Failed to load item: ${e.message}`, 'error');
        }
    }
    btnEdit.addEventListener('click', () => {
        showEdit(true);
        editName.focus();
    });
    btnCancelEdit.addEventListener('click', () => {
        showEdit(false);
        if (current)
            editName.value = current.name;
    });
    btnSave.addEventListener('click', async () => {
        const name = editName.value.trim();
        if (!name)
            return setFlash('Name is required.', 'error');
        try {
            await api(`/api/v1/connections/${itemId}/rename/`, {
                method: 'POST',
                body: JSON.stringify({ name }),
            });
            setFlash('Updated.', 'success');
            showEdit(false);
            await load();
        }
        catch (e) {
            setFlash(`Update failed: ${e.message}`, 'error');
        }
    });
    btnTest.addEventListener('click', async () => {
        const prevText = btnTest.textContent || 'Test';
        btnTest.disabled = true;
        btnTest.textContent = 'Testing…';
        try {
            const out = await api(`/api/v1/connections/${itemId}/test/`, { method: 'POST' });
            if (out.ok) {
                setFlash(out.message || 'Connection OK.', 'success');
            }
            else {
                setFlash(out.message || 'Test failed.', 'error');
            }
        }
        catch (e) {
            setFlash(`Test failed: ${e.message}`, 'error');
        }
        finally {
            btnTest.disabled = false;
            btnTest.textContent = prevText;
        }
    });
    btnDelete.addEventListener('click', async () => {
        if (!confirm('Delete this credential? This cannot be undone.'))
            return;
        try {
            await api(`/api/v1/connections/${itemId}/`, { method: 'DELETE' });
            window.location.href = '/connections/';
        }
        catch (e) {
            setFlash(`Delete failed: ${e.message}`, 'error');
        }
    });
    await load();
});
//# sourceMappingURL=detail.js.map