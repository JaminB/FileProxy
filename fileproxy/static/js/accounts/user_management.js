import { getCsrfToken } from '../utils/cookies.js';
import { qs, setFlash } from '../utils/dom.js';
// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------
function csrf() {
    const token = getCsrfToken();
    return token ? { 'X-CSRFToken': token } : {};
}
async function apiPost(url, body = {}) {
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...csrf() },
        credentials: 'same-origin',
        body: JSON.stringify(body),
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err['detail'] ?? `Request failed (${resp.status})`);
    }
    return resp.json();
}
async function apiPatch(url, body) {
    const resp = await fetch(url, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...csrf() },
        credentials: 'same-origin',
        body: JSON.stringify(body),
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err['detail'] ?? `Request failed (${resp.status})`);
    }
    return resp.json();
}
async function apiDelete(url) {
    const resp = await fetch(url, {
        method: 'DELETE',
        headers: { Accept: 'application/json', ...csrf() },
        credentials: 'same-origin',
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err['detail'] ?? `Delete failed (${resp.status})`);
    }
}
async function fetchUsers(statusFilter, search) {
    const params = new URLSearchParams();
    if (statusFilter)
        params.set('status', statusFilter);
    if (search)
        params.set('search', search);
    const resp = await fetch(`/api/v1/users/?${params.toString()}`, {
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
    });
    if (!resp.ok)
        throw new Error(`Failed to load users (${resp.status})`);
    const data = await resp.json();
    return Array.isArray(data) ? data : data.results ?? [];
}
/** Fetch the pending count independently of the current tab filter. */
async function fetchPendingCount() {
    try {
        const users = await fetchUsers('pending', '');
        return users.length;
    }
    catch {
        return 0;
    }
}
// ---------------------------------------------------------------------------
// Rendering helpers
// ---------------------------------------------------------------------------
function esc(s) {
    return s
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
function statusBadge(user) {
    const s = user.profile?.status ?? (user.is_active ? 'active' : 'inactive');
    const cls = {
        pending: 'bg-warning text-dark',
        active: 'bg-success',
        rejected: 'bg-danger',
        suspended: 'bg-secondary',
        inactive: 'bg-secondary',
    };
    const label = {
        pending: 'Pending',
        active: 'Active',
        rejected: 'Rejected',
        suspended: 'Suspended',
        inactive: 'Inactive',
    };
    return `<span class="badge ${cls[s] ?? 'bg-light text-dark'}">${label[s] ?? s}</span>`;
}
function fmtDate(iso) {
    if (!iso)
        return '—';
    return iso.slice(0, 10);
}
function sourceLabel(user) {
    const src = user.profile?.signup_source;
    if (src === 'beta')
        return '<span class="badge bg-info text-dark">Beta</span>';
    if (src === 'normal')
        return 'Normal';
    return '—';
}
// ---------------------------------------------------------------------------
// User list page
// ---------------------------------------------------------------------------
let currentStatus = '';
let currentSearch = '';
let searchTimer = null;
let pendingAction = null;
function renderUserRows(tbody, users) {
    tbody.innerHTML = '';
    if (!users.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 9;
        td.className = 'text-secondary';
        td.textContent = 'No users found.';
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }
    for (const user of users) {
        const tr = document.createElement('tr');
        if (user.profile?.status === 'pending')
            tr.classList.add('table-warning');
        tr.innerHTML = `
      <td><a href="/users/${user.id}/">${esc(user.username)}</a></td>
      <td>${esc(`${user.first_name} ${user.last_name}`.trim())}</td>
      <td>${esc(user.email)}</td>
      <td>${sourceLabel(user)}</td>
      <td>${statusBadge(user)}</td>
      <td>${user.plan_name ? esc(user.plan_name) : '<span class="text-secondary">Default</span>'}</td>
      <td>${fmtDate(user.date_joined)}</td>
      <td>${fmtDate(user.last_login)}</td>
      <td class="text-end"></td>
    `;
        const actionsTd = tr.querySelector('td:last-child');
        actionsTd.appendChild(buildActionsDropdown(user));
        tbody.appendChild(tr);
    }
}
/**
 * Build per-row action dropdown.
 *
 * Action rules (aligned with API endpoint guards):
 *   pending  → Approve, Reject
 *   rejected → Approve, Reject (re-reject with new note)
 *   active   → Suspend
 *   suspended → Activate
 */
function buildActionsDropdown(user) {
    const group = document.createElement('div');
    group.className = 'dropdown';
    const profileStatus = user.profile?.status;
    const canApproveReject = profileStatus === 'pending' || profileStatus === 'rejected';
    const canSuspend = user.is_active;
    const canActivate = profileStatus === 'suspended';
    group.innerHTML = `
    <button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown">
      Actions
    </button>
    <ul class="dropdown-menu dropdown-menu-end">
      <li><a class="dropdown-item" href="/users/${user.id}/">View / Edit</a></li>
      <li><hr class="dropdown-divider"></li>
      ${canApproveReject ? `<li><button class="dropdown-item" data-action="approve" data-id="${user.id}">Approve</button></li>` : ''}
      ${canApproveReject ? `<li><button class="dropdown-item text-danger" data-action="reject" data-id="${user.id}">Reject</button></li>` : ''}
      ${canSuspend ? `<li><button class="dropdown-item text-warning" data-action="suspend" data-id="${user.id}">Suspend</button></li>` : ''}
      ${canActivate ? `<li><button class="dropdown-item text-success" data-action="activate" data-id="${user.id}">Activate</button></li>` : ''}
      <li><button class="dropdown-item" data-action="reset-password" data-id="${user.id}">Reset password</button></li>
      <li><button class="dropdown-item" data-action="change-plan" data-id="${user.id}">Change plan</button></li>
      <li><hr class="dropdown-divider"></li>
      <li><button class="dropdown-item text-danger" data-action="delete" data-id="${user.id}">Delete</button></li>
    </ul>
  `;
    group.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-action]');
        if (!btn)
            return;
        const action = btn.dataset['action'];
        const userId = parseInt(btn.dataset['id'], 10);
        void handleAction(userId, action);
    });
    return group;
}
async function loadUsers() {
    const tbody = qs('#users-rows');
    if (!tbody)
        return;
    try {
        const [users, pendingCount] = await Promise.all([
            fetchUsers(currentStatus, currentSearch),
            fetchPendingCount(),
        ]);
        renderUserRows(tbody, users);
        updatePendingBadge(pendingCount);
    }
    catch (err) {
        setFlash(String(err), 'error');
    }
}
function updatePendingBadge(count) {
    const badge = qs('#badge-pending');
    if (!badge)
        return;
    badge.textContent = count > 0 ? String(count) : '';
}
async function handleAction(userId, action) {
    if (action === 'reject' || action === 'suspend') {
        pendingAction = { userId, action };
        const modal = document.getElementById('noteModal');
        if (modal) {
            const noteInput = qs('#note-input');
            if (noteInput)
                noteInput.value = '';
            const label = qs('#noteModalLabel');
            if (label)
                label.textContent = action === 'reject' ? 'Reject user' : 'Suspend user';
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const bsModal = window.bootstrap?.Modal?.getOrCreateInstance(modal);
            bsModal?.show();
        }
        return;
    }
    if (action === 'change-plan') {
        pendingAction = { userId, action };
        const modal = document.getElementById('changePlanModal');
        if (modal) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const bsModal = window.bootstrap?.Modal?.getOrCreateInstance(modal);
            bsModal?.show();
        }
        return;
    }
    if (action === 'delete') {
        if (!confirm('Delete this user? This cannot be undone.'))
            return;
        try {
            await apiDelete(`/api/v1/users/${userId}/`);
            setFlash('User deleted.', 'success');
            await loadUsers();
        }
        catch (err) {
            setFlash(String(err), 'error');
        }
        return;
    }
    try {
        await apiPost(`/api/v1/users/${userId}/${action}/`);
        setFlash('Done.', 'success');
        await loadUsers();
    }
    catch (err) {
        setFlash(String(err), 'error');
    }
}
function initListPage() {
    const tabs = document.querySelectorAll('#status-tabs [data-status]');
    tabs.forEach((tab) => {
        tab.addEventListener('click', async () => {
            tabs.forEach((t) => t.classList.remove('active'));
            tab.classList.add('active');
            currentStatus = tab.dataset['status'] ?? '';
            await loadUsers();
        });
    });
    const searchInput = qs('#search-input');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            if (searchTimer)
                clearTimeout(searchTimer);
            searchTimer = setTimeout(async () => {
                currentSearch = searchInput.value.trim();
                await loadUsers();
            }, 300);
        });
    }
    // Note modal confirm
    const confirmNoteBtn = qs('#confirm-note-action');
    if (confirmNoteBtn) {
        confirmNoteBtn.addEventListener('click', async () => {
            if (!pendingAction)
                return;
            const note = (qs('#note-input')?.value ?? '').trim();
            const modal = document.getElementById('noteModal');
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const bsModal = window.bootstrap?.Modal?.getInstance(modal);
            bsModal?.hide();
            try {
                await apiPost(`/api/v1/users/${pendingAction.userId}/${pendingAction.action}/`, { note });
                setFlash('Done.', 'success');
                await loadUsers();
            }
            catch (err) {
                setFlash(String(err), 'error');
            }
            finally {
                pendingAction = null;
            }
        });
    }
    // Change plan modal confirm
    const confirmPlanBtn = qs('#confirm-change-plan');
    if (confirmPlanBtn) {
        confirmPlanBtn.addEventListener('click', async () => {
            if (!pendingAction)
                return;
            const planId = qs('#plan-select')?.value;
            if (!planId)
                return;
            const modal = document.getElementById('changePlanModal');
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const bsModal = window.bootstrap?.Modal?.getInstance(modal);
            bsModal?.hide();
            try {
                await apiPost(`/api/v1/users/${pendingAction.userId}/change-plan/`, { plan_id: planId });
                setFlash('Plan updated.', 'success');
                await loadUsers();
            }
            catch (err) {
                setFlash(String(err), 'error');
            }
            finally {
                pendingAction = null;
            }
        });
    }
    void loadUsers();
}
// ---------------------------------------------------------------------------
// User detail page
// ---------------------------------------------------------------------------
function initDetailPage() {
    const actionButtons = qs('#action-buttons');
    if (!actionButtons)
        return;
    const userId = parseInt(actionButtons.dataset['userId'] ?? '0', 10);
    if (!userId)
        return;
    // Edit form
    const editForm = qs('#edit-form');
    if (editForm) {
        editForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = {};
            const fd = new FormData(editForm);
            for (const [k, v] of fd.entries()) {
                if (k === 'csrfmiddlewaretoken')
                    continue;
                data[k] = v;
            }
            // is_staff checkbox — if absent from FormData, it's unchecked
            const staffCb = qs('[name=is_staff]', editForm);
            if (staffCb && !staffCb.disabled) {
                data['is_staff'] = staffCb.checked;
            }
            try {
                await apiPatch(`/api/v1/users/${userId}/`, data);
                setFlash('Saved.', 'success');
            }
            catch (err) {
                setFlash(String(err), 'error');
            }
        });
    }
    // Action buttons
    actionButtons.addEventListener('click', async (e) => {
        const btn = e.target.closest('[data-action]');
        if (!btn)
            return;
        const action = btn.dataset['action'];
        if (action === 'reject' || action === 'suspend') {
            pendingAction = { userId, action };
            const modal = document.getElementById('noteModal');
            if (modal) {
                const noteInput = qs('#note-input');
                if (noteInput)
                    noteInput.value = '';
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const bsModal = window.bootstrap?.Modal?.getOrCreateInstance(modal);
                bsModal?.show();
            }
            return;
        }
        if (action === 'change-plan') {
            pendingAction = { userId, action };
            const modal = document.getElementById('changePlanModal');
            if (modal) {
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const bsModal = window.bootstrap?.Modal?.getOrCreateInstance(modal);
                bsModal?.show();
            }
            return;
        }
        if (action === 'delete') {
            if (!confirm('Delete this user? This cannot be undone.'))
                return;
            try {
                await apiDelete(`/api/v1/users/${userId}/`);
                window.location.href = '/users/';
            }
            catch (err) {
                setFlash(String(err), 'error');
            }
            return;
        }
        try {
            btn.setAttribute('disabled', 'true');
            await apiPost(`/api/v1/users/${userId}/${action}/`);
            setFlash('Done. Reload to see updated status.', 'success');
        }
        catch (err) {
            setFlash(String(err), 'error');
        }
        finally {
            btn.removeAttribute('disabled');
        }
    });
    // Note modal confirm
    const confirmNoteBtn = qs('#confirm-note-action');
    if (confirmNoteBtn) {
        confirmNoteBtn.addEventListener('click', async () => {
            if (!pendingAction)
                return;
            const note = (qs('#note-input')?.value ?? '').trim();
            const modal = document.getElementById('noteModal');
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const bsModal = window.bootstrap?.Modal?.getInstance(modal);
            bsModal?.hide();
            try {
                await apiPost(`/api/v1/users/${pendingAction.userId}/${pendingAction.action}/`, { note });
                setFlash('Done. Reload to see updated status.', 'success');
            }
            catch (err) {
                setFlash(String(err), 'error');
            }
            finally {
                pendingAction = null;
            }
        });
    }
    // Change plan modal confirm
    const confirmPlanBtn = qs('#confirm-change-plan');
    if (confirmPlanBtn) {
        confirmPlanBtn.addEventListener('click', async () => {
            if (!pendingAction)
                return;
            const planId = qs('#plan-select')?.value;
            if (!planId)
                return;
            const modal = document.getElementById('changePlanModal');
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const bsModal = window.bootstrap?.Modal?.getInstance(modal);
            bsModal?.hide();
            try {
                await apiPost(`/api/v1/users/${pendingAction.userId}/change-plan/`, { plan_id: planId });
                setFlash('Plan updated. Reload to see change.', 'success');
            }
            catch (err) {
                setFlash(String(err), 'error');
            }
            finally {
                pendingAction = null;
            }
        });
    }
}
// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('users-rows')) {
        initListPage();
    }
    else if (document.getElementById('action-buttons')) {
        initDetailPage();
    }
});
//# sourceMappingURL=user_management.js.map