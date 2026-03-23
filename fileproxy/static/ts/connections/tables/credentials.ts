import { qs, setFlash } from '../../utils/dom.js';
import { getCsrfToken } from '../../utils/cookies.js';

const KIND_META: Record<string, { label: string; src: string }> = {
  aws_s3: { label: 'Amazon S3', src: '/static/images/logos/s3.svg' },
  gdrive_oauth2: { label: 'Google Drive', src: '/static/images/logos/gdrive.svg' },
  dropbox_oauth2: { label: 'Dropbox', src: '/static/images/logos/dropbox.png' },
  azure_blob: { label: 'Azure Blob Storage', src: '/static/images/logos/azure.svg' },
};

async function deleteConnection(id: string | number): Promise<Response> {
  const csrf = getCsrfToken();
  return fetch(`/api/v1/connections/${id}/`, {
    method: 'DELETE',
    headers: {
      Accept: 'application/json',
      ...(csrf ? { 'X-CSRFToken': csrf } : {}),
    },
    credentials: 'same-origin',
  });
}

type Connection = {
  id?: string | number;
  name?: string | null;
  kind?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  rotated_at?: string | null;
};

type SortCol = 'name' | 'kind' | 'created_at' | 'updated_at' | 'rotated_at';

type ConnectionListResponse = Connection[] | { results: Connection[] };

function toItems(payload: ConnectionListResponse): Connection[] {
  if (Array.isArray(payload)) return payload;
  const results = (payload as { results?: unknown }).results;
  return Array.isArray(results) ? (results as Connection[]) : [];
}

function fmtDate(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;

  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/* ----------------------------- Sort state ----------------------------- */

let sortCol: SortCol = 'updated_at';
let sortDir: 'asc' | 'desc' = 'desc';
let allItems: Connection[] = [];

function sortItems(items: Connection[]): Connection[] {
  return [...items].sort((a, b) => {
    const av = a[sortCol] ?? '';
    const bv = b[sortCol] ?? '';
    // Nulls/empty always sort to the end regardless of direction
    if (!av && !bv) return 0;
    if (!av) return 1;
    if (!bv) return -1;
    const cmp = av.localeCompare(bv);
    return sortDir === 'asc' ? cmp : -cmp;
  });
}

function updateSortIndicators(): void {
  const thead = document.getElementById('connection-head');
  if (!thead) return;
  for (const th of Array.from(thead.querySelectorAll<HTMLElement>('th[data-sort]'))) {
    const col = th.getAttribute('data-sort') as SortCol;
    const indicator = th.querySelector('.sort-indicator');
    if (col === sortCol) {
      th.setAttribute('aria-sort', sortDir === 'asc' ? 'ascending' : 'descending');
      if (indicator) indicator.textContent = sortDir === 'asc' ? ' ▲' : ' ▼';
    } else {
      th.setAttribute('aria-sort', 'none');
      if (indicator) indicator.textContent = '';
    }
  }
}

/* ----------------------------- DOM helpers ----------------------------- */

function clear(tbody: HTMLTableSectionElement): void {
  tbody.innerHTML = '';
}

function messageRow(tbody: HTMLTableSectionElement, text: string): void {
  const tr = document.createElement('tr');
  const td = document.createElement('td');
  td.colSpan = 6;
  td.className = 'text-secondary';
  td.textContent = text;
  tr.appendChild(td);
  tbody.appendChild(tr);
}

function bsIcon(className: string): HTMLElement {
  const i = document.createElement('i');
  i.className = className;
  i.setAttribute('aria-hidden', 'true');
  return i;
}

function actionButton(
  label: string,
  btnClasses: string,
  iconClasses: string,
  onClick: () => void,
): HTMLButtonElement {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = `btn ${btnClasses}`;
  btn.title = label;
  btn.setAttribute('aria-label', label);

  btn.appendChild(bsIcon(`${iconClasses} me-1`));
  btn.appendChild(document.createTextNode(label));

  btn.addEventListener('click', onClick);
  return btn;
}

function renderItems(tbody: HTMLTableSectionElement, items: Connection[]): void {
  clear(tbody);

  if (!items.length) {
    messageRow(tbody, 'No credentials yet.');
    return;
  }

  for (const item of sortItems(items)) {
    const tr = document.createElement('tr');

    const nameTd = document.createElement('td');
    nameTd.textContent = item.name ?? '—';

    const kindTd = document.createElement('td');
    const km = KIND_META[item.kind ?? ''];
    if (km) {
      const img = document.createElement('img');
      img.src = km.src;
      img.alt = '';
      img.width = 14;
      img.height = 14;
      img.className = 'me-1 opacity-75';
      img.setAttribute('aria-hidden', 'true');
      kindTd.appendChild(img);
      kindTd.appendChild(document.createTextNode(km.label));
    } else {
      kindTd.textContent = item.kind ?? '—';
    }

    const createdTd = document.createElement('td');
    createdTd.textContent = fmtDate(item.created_at);

    const updatedTd = document.createElement('td');
    updatedTd.textContent = fmtDate(item.updated_at);

    const rotatedTd = document.createElement('td');
    rotatedTd.textContent = fmtDate(item.rotated_at);

    const actionsTd = document.createElement('td');
    actionsTd.className = 'text-end';

    const group = document.createElement('div');
    group.className = 'btn-group btn-group-sm';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', 'Connection actions');

    const id = item.id;

    const viewBtn = actionButton('View', 'btn-outline-secondary', 'bi bi-eye', () => {
      if (id != null) {
        window.location.href = `/connections/item/${id}/`;
      }
    });

    const deleteBtn = actionButton('Delete', 'btn-outline-danger', 'bi bi-trash', async () => {
      if (id == null) return;
      if (!confirm('Delete this credential? This cannot be undone.')) return;

      try {
        deleteBtn.disabled = true;

        const resp = await deleteConnection(id);
        if (!resp.ok) {
          const msg = `Delete failed (${resp.status}).`;
          setFlash(msg, 'error');
          deleteBtn.disabled = false;
          return;
        }

        tr.remove();
        allItems = allItems.filter((c) => c.id !== id);
        setFlash('Deleted.', 'info');

        // If we removed the last row, show empty state
        if (tbody.querySelectorAll('tr').length === 0) {
          messageRow(tbody, 'No credentials yet.');
        }
      } catch (err) {
        setFlash(`Delete failed: ${String(err)}`, 'error');
        deleteBtn.disabled = false;
      }
    });

    group.appendChild(viewBtn);
    group.appendChild(deleteBtn);
    actionsTd.appendChild(group);

    tr.appendChild(nameTd);
    tr.appendChild(kindTd);
    tr.appendChild(createdTd);
    tr.appendChild(updatedTd);
    tr.appendChild(rotatedTd);
    tr.appendChild(actionsTd);

    tbody.appendChild(tr);
  }
}

function initSortHeaders(tbody: HTMLTableSectionElement): void {
  const thead = document.getElementById('connection-head');
  if (!thead) return;

  for (const th of Array.from(thead.querySelectorAll<HTMLElement>('th[data-sort]'))) {
    // Add sort indicator span
    const indicator = document.createElement('span');
    indicator.className = 'sort-indicator';
    indicator.setAttribute('aria-hidden', 'true');
    const col = th.getAttribute('data-sort') as SortCol;
    th.setAttribute('tabindex', '0');
    th.setAttribute('aria-sort', col === sortCol ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none');
    if (col === sortCol) {
      indicator.textContent = sortDir === 'asc' ? ' ▲' : ' ▼';
    }
    th.appendChild(indicator);

    const activate = () => {
      const c = th.getAttribute('data-sort') as SortCol;
      if (c === sortCol) {
        sortDir = sortDir === 'asc' ? 'desc' : 'asc';
      } else {
        sortCol = c;
        sortDir = 'asc';
      }
      updateSortIndicators();
      renderItems(tbody, allItems);
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

export async function loadConnectionsTable(): Promise<void> {
  const tbody = qs<HTMLTableSectionElement>('#connection-rows');
  if (!tbody) return;

  initSortHeaders(tbody);

  try {
    const resp = await fetch('/api/v1/connections/', {
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
    });

    if (!resp.ok) {
      const msg = `Failed to load connections (${resp.status}).`;
      setFlash(msg, 'error');
      messageRow(tbody, msg);
      return;
    }

    const data = (await resp.json()) as ConnectionListResponse;
    allItems = toItems(data);
    renderItems(tbody, allItems);
  } catch (err) {
    const msg = `Network error loading connections: ${String(err)}`;
    setFlash(msg, 'error');
    messageRow(tbody, msg);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  void loadConnectionsTable();
});
