import { getCsrfToken } from '../utils/cookies.js';
import { qs, setFlash } from '../utils/dom.js';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type UserProfile = {
  status: 'pending' | 'active' | 'rejected' | 'suspended';
  signup_source: 'normal' | 'beta';
  status_updated_at: string;
  review_note: string;
};

type User = {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  is_staff: boolean;
  is_active: boolean;
  date_joined: string;
  last_login: string | null;
  profile: UserProfile | null;
  plan_name: string | null;
};

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

function csrf(): Record<string, string> {
  const token = getCsrfToken();
  return token ? { 'X-CSRFToken': token } : {};
}

async function apiPost(url: string, body: unknown = {}): Promise<User> {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...csrf() },
    credentials: 'same-origin',
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = (await resp.json().catch(() => ({}))) as Record<string, string>;
    throw new Error(err['detail'] ?? `Request failed (${resp.status})`);
  }
  return resp.json() as Promise<User>;
}

async function apiPatch(url: string, body: unknown): Promise<User> {
  const resp = await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...csrf() },
    credentials: 'same-origin',
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = (await resp.json().catch(() => ({}))) as Record<string, string>;
    throw new Error(err['detail'] ?? `Request failed (${resp.status})`);
  }
  return resp.json() as Promise<User>;
}

async function apiDelete(url: string): Promise<void> {
  const resp = await fetch(url, {
    method: 'DELETE',
    headers: { Accept: 'application/json', ...csrf() },
    credentials: 'same-origin',
  });
  if (!resp.ok) {
    const err = (await resp.json().catch(() => ({}))) as Record<string, string>;
    throw new Error(err['detail'] ?? `Delete failed (${resp.status})`);
  }
}

async function fetchUsers(status: string, search: string): Promise<User[]> {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (search) params.set('search', search);
  const resp = await fetch(`/api/v1/users/?${params.toString()}`, {
    headers: { Accept: 'application/json' },
    credentials: 'same-origin',
  });
  if (!resp.ok) throw new Error(`Failed to load users (${resp.status})`);
  const data = (await resp.json()) as User[] | { results: User[] };
  return Array.isArray(data) ? data : ((data as { results: User[] }).results ?? []);
}

// ---------------------------------------------------------------------------
// Rendering helpers
// ---------------------------------------------------------------------------

function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function statusBadge(user: User): string {
  const s = user.profile?.status ?? (user.is_active ? 'active' : 'inactive');
  const cls: Record<string, string> = {
    pending: 'bg-warning text-dark',
    active: 'bg-success',
    rejected: 'bg-danger',
    suspended: 'bg-secondary',
    inactive: 'bg-secondary',
  };
  const label: Record<string, string> = {
    pending: 'Pending',
    active: 'Active',
    rejected: 'Rejected',
    suspended: 'Suspended',
    inactive: 'Inactive',
  };
  return `<span class="badge ${cls[s] ?? 'bg-light text-dark'}">${label[s] ?? s}</span>`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  return iso.slice(0, 10);
}

function sourceLabel(user: User): string {
  const src = user.profile?.signup_source;
  if (src === 'beta') return '<span class="badge bg-info text-dark">Beta</span>';
  if (src === 'normal') return 'Normal';
  return '—';
}

// ---------------------------------------------------------------------------
// User list page
// ---------------------------------------------------------------------------

let currentStatus = '';
let currentSearch = '';
let searchTimer: ReturnType<typeof setTimeout> | null = null;
let pendingAction: { userId: number; action: string } | null = null;

function renderUserRows(tbody: HTMLTableSectionElement, users: User[]): void {
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
    const rowClass = user.profile?.status === 'pending' ? ' class="table-warning"' : '';
    const tr = document.createElement('tr');
    if (user.profile?.status === 'pending') tr.classList.add('table-warning');

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

    const actionsTd = tr.querySelector('td:last-child') as HTMLTableCellElement;
    actionsTd.appendChild(buildActionsDropdown(user));
    tbody.appendChild(tr);
  }
}

function buildActionsDropdown(user: User): HTMLElement {
  const group = document.createElement('div');
  group.className = 'dropdown';

  const status = user.profile?.status;

  group.innerHTML = `
    <button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown">
      Actions
    </button>
    <ul class="dropdown-menu dropdown-menu-end">
      <li><a class="dropdown-item" href="/users/${user.id}/">View / Edit</a></li>
      <li><hr class="dropdown-divider"></li>
      ${status === 'pending' || status === 'rejected' ? `<li><button class="dropdown-item" data-action="approve" data-id="${user.id}">Approve</button></li>` : ''}
      ${status === 'pending' ? `<li><button class="dropdown-item text-danger" data-action="reject" data-id="${user.id}">Reject</button></li>` : ''}
      ${user.is_active ? `<li><button class="dropdown-item text-warning" data-action="suspend" data-id="${user.id}">Suspend</button></li>` : ''}
      ${status === 'suspended' || status === 'rejected' ? `<li><button class="dropdown-item text-success" data-action="activate" data-id="${user.id}">Activate</button></li>` : ''}
      <li><button class="dropdown-item" data-action="reset-password" data-id="${user.id}">Reset password</button></li>
      <li><button class="dropdown-item" data-action="change-plan" data-id="${user.id}">Change plan</button></li>
      <li><hr class="dropdown-divider"></li>
      <li><button class="dropdown-item text-danger" data-action="delete" data-id="${user.id}">Delete</button></li>
    </ul>
  `;

  group.addEventListener('click', (e) => {
    const btn = (e.target as HTMLElement).closest('[data-action]') as HTMLElement | null;
    if (!btn) return;
    const action = btn.dataset['action']!;
    const userId = parseInt(btn.dataset['id']!, 10);
    void handleAction(userId, action);
  });

  return group;
}

async function loadUsers(): Promise<void> {
  const tbody = qs<HTMLTableSectionElement>('#users-rows');
  if (!tbody) return;

  try {
    const users = await fetchUsers(currentStatus, currentSearch);
    renderUserRows(tbody, users);
    updatePendingBadge(users);
  } catch (err) {
    setFlash(String(err), 'error');
  }
}

function updatePendingBadge(users: User[]): void {
  const badge = qs<HTMLElement>('#badge-pending');
  if (!badge) return;
  const count = users.filter((u) => u.profile?.status === 'pending').length;
  badge.textContent = count > 0 ? String(count) : '';
}

async function handleAction(userId: number, action: string): Promise<void> {
  if (action === 'reject' || action === 'suspend') {
    pendingAction = { userId, action };
    const modal = document.getElementById('noteModal');
    if (modal) {
      const noteInput = qs<HTMLTextAreaElement>('#note-input');
      if (noteInput) noteInput.value = '';
      const label = qs<HTMLElement>('#noteModalLabel');
      if (label) label.textContent = action === 'reject' ? 'Reject user' : 'Suspend user';
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const bsModal = (window as any).bootstrap?.Modal?.getOrCreateInstance(modal) as
        | { show(): void }
        | undefined;
      bsModal?.show();
    }
    return;
  }

  if (action === 'change-plan') {
    pendingAction = { userId, action };
    const modal = document.getElementById('changePlanModal');
    if (modal) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const bsModal = (window as any).bootstrap?.Modal?.getOrCreateInstance(modal) as
        | { show(): void }
        | undefined;
      bsModal?.show();
    }
    return;
  }

  if (action === 'delete') {
    if (!confirm('Delete this user? This cannot be undone.')) return;
    try {
      await apiDelete(`/api/v1/users/${userId}/`);
      setFlash('User deleted.', 'success');
      await loadUsers();
    } catch (err) {
      setFlash(String(err), 'error');
    }
    return;
  }

  try {
    await apiPost(`/api/v1/users/${userId}/${action}/`);
    setFlash('Done.', 'success');
    await loadUsers();
  } catch (err) {
    setFlash(String(err), 'error');
  }
}

function initListPage(): void {
  const tabs = document.querySelectorAll<HTMLButtonElement>('#status-tabs [data-status]');
  tabs.forEach((tab) => {
    tab.addEventListener('click', async () => {
      tabs.forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      currentStatus = tab.dataset['status'] ?? '';
      await loadUsers();
    });
  });

  const searchInput = qs<HTMLInputElement>('#search-input');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(async () => {
        currentSearch = searchInput.value.trim();
        await loadUsers();
      }, 300);
    });
  }

  // Note modal confirm
  const confirmNoteBtn = qs<HTMLButtonElement>('#confirm-note-action');
  if (confirmNoteBtn) {
    confirmNoteBtn.addEventListener('click', async () => {
      if (!pendingAction) return;
      const note = (qs<HTMLTextAreaElement>('#note-input')?.value ?? '').trim();
      const modal = document.getElementById('noteModal');
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const bsModal = (window as any).bootstrap?.Modal?.getInstance(modal) as
        | { hide(): void }
        | undefined;
      bsModal?.hide();

      try {
        await apiPost(`/api/v1/users/${pendingAction.userId}/${pendingAction.action}/`, { note });
        setFlash('Done.', 'success');
        await loadUsers();
      } catch (err) {
        setFlash(String(err), 'error');
      } finally {
        pendingAction = null;
      }
    });
  }

  // Change plan modal confirm
  const confirmPlanBtn = qs<HTMLButtonElement>('#confirm-change-plan');
  if (confirmPlanBtn) {
    confirmPlanBtn.addEventListener('click', async () => {
      if (!pendingAction) return;
      const planId = qs<HTMLSelectElement>('#plan-select')?.value;
      if (!planId) return;
      const modal = document.getElementById('changePlanModal');
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const bsModal = (window as any).bootstrap?.Modal?.getInstance(modal) as
        | { hide(): void }
        | undefined;
      bsModal?.hide();

      try {
        await apiPost(`/api/v1/users/${pendingAction.userId}/change-plan/`, { plan_id: planId });
        setFlash('Plan updated.', 'success');
        await loadUsers();
      } catch (err) {
        setFlash(String(err), 'error');
      } finally {
        pendingAction = null;
      }
    });
  }

  void loadUsers();
}

// ---------------------------------------------------------------------------
// User detail page
// ---------------------------------------------------------------------------

function initDetailPage(): void {
  const actionButtons = qs<HTMLElement>('#action-buttons');
  if (!actionButtons) return;
  const userId = parseInt(actionButtons.dataset['userId'] ?? '0', 10);
  if (!userId) return;

  // Edit form
  const editForm = qs<HTMLFormElement>('#edit-form');
  if (editForm) {
    editForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const data: Record<string, unknown> = {};
      const fd = new FormData(editForm);
      for (const [k, v] of fd.entries()) {
        if (k === 'csrfmiddlewaretoken') continue;
        data[k] = v;
      }
      // is_staff checkbox — if absent from FormData, it's unchecked
      const staffCb = qs<HTMLInputElement>('[name=is_staff]', editForm);
      if (staffCb && !staffCb.disabled) {
        data['is_staff'] = staffCb.checked;
      }
      try {
        await apiPatch(`/api/v1/users/${userId}/`, data);
        setFlash('Saved.', 'success');
      } catch (err) {
        setFlash(String(err), 'error');
      }
    });
  }

  // Action buttons
  actionButtons.addEventListener('click', async (e) => {
    const btn = (e.target as HTMLElement).closest('[data-action]') as HTMLElement | null;
    if (!btn) return;
    const action = btn.dataset['action']!;

    if (action === 'reject' || action === 'suspend') {
      pendingAction = { userId, action };
      const modal = document.getElementById('noteModal');
      if (modal) {
        const noteInput = qs<HTMLTextAreaElement>('#note-input');
        if (noteInput) noteInput.value = '';
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const bsModal = (window as any).bootstrap?.Modal?.getOrCreateInstance(modal) as
          | { show(): void }
          | undefined;
        bsModal?.show();
      }
      return;
    }

    if (action === 'change-plan') {
      pendingAction = { userId, action };
      const modal = document.getElementById('changePlanModal');
      if (modal) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const bsModal = (window as any).bootstrap?.Modal?.getOrCreateInstance(modal) as
          | { show(): void }
          | undefined;
        bsModal?.show();
      }
      return;
    }

    if (action === 'delete') {
      if (!confirm('Delete this user? This cannot be undone.')) return;
      try {
        await apiDelete(`/api/v1/users/${userId}/`);
        window.location.href = '/users/';
      } catch (err) {
        setFlash(String(err), 'error');
      }
      return;
    }

    try {
      btn.setAttribute('disabled', 'true');
      await apiPost(`/api/v1/users/${userId}/${action}/`);
      setFlash('Done. Reload to see updated status.', 'success');
    } catch (err) {
      setFlash(String(err), 'error');
    } finally {
      btn.removeAttribute('disabled');
    }
  });

  // Note modal confirm
  const confirmNoteBtn = qs<HTMLButtonElement>('#confirm-note-action');
  if (confirmNoteBtn) {
    confirmNoteBtn.addEventListener('click', async () => {
      if (!pendingAction) return;
      const note = (qs<HTMLTextAreaElement>('#note-input')?.value ?? '').trim();
      const modal = document.getElementById('noteModal');
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const bsModal = (window as any).bootstrap?.Modal?.getInstance(modal) as
        | { hide(): void }
        | undefined;
      bsModal?.hide();

      try {
        await apiPost(`/api/v1/users/${pendingAction.userId}/${pendingAction.action}/`, { note });
        setFlash('Done. Reload to see updated status.', 'success');
      } catch (err) {
        setFlash(String(err), 'error');
      } finally {
        pendingAction = null;
      }
    });
  }

  // Change plan modal confirm
  const confirmPlanBtn = qs<HTMLButtonElement>('#confirm-change-plan');
  if (confirmPlanBtn) {
    confirmPlanBtn.addEventListener('click', async () => {
      if (!pendingAction) return;
      const planId = qs<HTMLSelectElement>('#plan-select')?.value;
      if (!planId) return;
      const modal = document.getElementById('changePlanModal');
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const bsModal = (window as any).bootstrap?.Modal?.getInstance(modal) as
        | { hide(): void }
        | undefined;
      bsModal?.hide();

      try {
        await apiPost(`/api/v1/users/${pendingAction.userId}/change-plan/`, { plan_id: planId });
        setFlash('Plan updated. Reload to see change.', 'success');
      } catch (err) {
        setFlash(String(err), 'error');
      } finally {
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
  } else if (document.getElementById('action-buttons')) {
    initDetailPage();
  }
});
