import { getCsrfToken } from '../utils/cookies.js';
import { qs, setFlash } from '../utils/dom.js';
function formatDate(iso) {
    if (!iso)
        return '—';
    return new Date(iso).toLocaleString();
}
function buildRow(key) {
    const tr = document.createElement('tr');
    tr.dataset.id = key.id;
    const nameTd = document.createElement('td');
    nameTd.textContent = key.name;
    tr.appendChild(nameTd);
    const createdTd = document.createElement('td');
    createdTd.textContent = formatDate(key.created_at);
    tr.appendChild(createdTd);
    const lastUsedTd = document.createElement('td');
    lastUsedTd.className = 'text-secondary';
    lastUsedTd.textContent = formatDate(key.last_used_at);
    tr.appendChild(lastUsedTd);
    const actionsTd = document.createElement('td');
    actionsTd.className = 'text-end';
    const revokeBtn = document.createElement('button');
    revokeBtn.className = 'btn btn-sm btn-outline-danger btn-revoke';
    revokeBtn.dataset.id = key.id;
    revokeBtn.dataset.name = key.name;
    revokeBtn.textContent = 'Revoke';
    actionsTd.appendChild(revokeBtn);
    tr.appendChild(actionsTd);
    revokeBtn.addEventListener('click', handleRevoke);
    return tr;
}
async function loadKeys() {
    const tbody = qs('#api-key-rows');
    try {
        const res = await fetch('/api/v1/accounts/api-keys/', { credentials: 'same-origin' });
        const keys = await res.json();
        tbody.innerHTML = '';
        if (keys.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-secondary">No API keys yet.</td></tr>';
            return;
        }
        for (const key of keys) {
            tbody.appendChild(buildRow(key));
        }
    }
    catch {
        setFlash('Failed to load API keys.', 'error');
    }
}
async function handleRevoke(e) {
    const btn = e.currentTarget;
    const id = btn.dataset.id;
    const name = btn.dataset.name;
    if (!confirm(`Revoke API key "${name}"? This cannot be undone.`))
        return;
    try {
        const res = await fetch(`/api/v1/accounts/api-keys/${id}/`, {
            method: 'DELETE',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': getCsrfToken() ?? '' },
        });
        if (res.status === 204) {
            const row = qs(`tr[data-id="${id}"]`);
            row?.remove();
            const tbody = qs('#api-key-rows');
            if (!tbody.querySelector('tr')) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-secondary">No API keys yet.</td></tr>';
            }
            setFlash(`Key "${name}" revoked.`, 'success');
        }
        else {
            setFlash('Failed to revoke key.', 'error');
        }
    }
    catch {
        setFlash('Failed to revoke key.', 'error');
    }
}
async function handleCreate(e) {
    e.preventDefault();
    const form = e.currentTarget;
    const nameInput = qs('#key-name', form);
    const name = nameInput.value.trim();
    if (!name)
        return;
    try {
        const res = await fetch('/api/v1/accounts/api-keys/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken() ?? '',
            },
            body: JSON.stringify({ name }),
        });
        if (res.status === 201) {
            const key = await res.json();
            const tbody = qs('#api-key-rows');
            const placeholder = tbody.querySelector('td[colspan]');
            if (placeholder)
                tbody.innerHTML = '';
            tbody.insertBefore(buildRow(key), tbody.firstChild);
            nameInput.value = '';
            // Show token modal
            const tokenInput = qs('#token-value');
            tokenInput.value = key.token ?? '';
            const modalEl = document.getElementById('token-modal');
            const modal = new window.bootstrap.Modal(modalEl);
            modal.show();
            setFlash(`Key "${key.name}" created.`, 'success');
        }
        else {
            const body = await res.json();
            setFlash(body?.name?.[0] ?? 'Failed to create key.', 'error');
        }
    }
    catch {
        setFlash('Failed to create key.', 'error');
    }
}
document.addEventListener('DOMContentLoaded', () => {
    loadKeys();
    qs('#new-key-form').addEventListener('submit', handleCreate);
    qs('#btn-copy-token')?.addEventListener('click', () => {
        const val = qs('#token-value')?.value ?? '';
        navigator.clipboard.writeText(val).then(() => {
            const btn = qs('#btn-copy-token');
            btn.innerHTML = '<i class="bi bi-check me-1"></i>Copied';
            setTimeout(() => {
                btn.innerHTML = '<i class="bi bi-clipboard me-1"></i>Copy';
            }, 2000);
        });
    });
});
//# sourceMappingURL=profile.js.map