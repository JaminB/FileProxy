import { qs, setFlash } from "../../utils/dom.js";
import { spriteIcon } from "../../utils/icons.js";
import { getCsrfToken } from "../../utils/cookies.js";

async function deleteVaultItem(id: string | number): Promise<Response> {
  const csrf = getCsrfToken();
  return fetch(`/api/v1/vault-items/${id}/`, {
    method: "DELETE",
    headers: {
      Accept: "application/json",
      ...(csrf ? { "X-CSRFToken": csrf } : {}),
    },
    credentials: "same-origin",
  });
}

type VaultItem = {
  id?: string | number;
  name?: string | null;
  kind?: string | null;
  updated?: string | null;
  rotated?: string | null;
};

type VaultListResponse =
  | VaultItem[]
  | { results: VaultItem[] };

function toItems(payload: VaultListResponse): VaultItem[] {
  if (Array.isArray(payload)) return payload;
  const results = (payload as any)?.results;
  return Array.isArray(results) ? results : [];
}

function fmtDate(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;

  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function clear(tbody: HTMLTableSectionElement): void {
  tbody.innerHTML = "";
}

function messageRow(tbody: HTMLTableSectionElement, text: string): void {
  const tr = document.createElement("tr");
  const td = document.createElement("td");
  td.colSpan = 5;
  td.className = "muted";
  td.textContent = text;
  tr.appendChild(td);
  tbody.appendChild(tr);
}

function iconButton(title: string, onClick?: () => void): HTMLButtonElement {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "btn ghost icon-btn";
  btn.title = title;
  btn.setAttribute("aria-label", title);

  if (onClick) btn.addEventListener("click", onClick);
  return btn;
}

function renderItems(tbody: HTMLTableSectionElement, items: VaultItem[]): void {
  clear(tbody);

  if (!items.length) {
    messageRow(tbody, "No credentials yet.");
    return;
  }

  for (const item of items) {
    const tr = document.createElement("tr");

    const nameTd = document.createElement("td");
    nameTd.textContent = item.name ?? "—";

    const kindTd = document.createElement("td");
    kindTd.textContent = item.kind ?? "—";

    const updatedTd = document.createElement("td");
    updatedTd.textContent = fmtDate(item.updated);

    const rotatedTd = document.createElement("td");
    rotatedTd.textContent = fmtDate(item.rotated);

    const actionsTd = document.createElement("td");
    actionsTd.className = "num";

    const row = document.createElement("div");
    row.className = "row";
    row.style.justifyContent = "flex-end";

    const id = item.id;

    // View
    const viewBtn = iconButton("View", () => {
      if (id != null) {
        window.location.href = `/vault/item/${id}/`;
      }
    });
    viewBtn.appendChild(spriteIcon("i-eye"));

    // Delete
    const deleteBtn = iconButton("Delete", async () => {
      if (id == null) return;
      if (!confirm("Delete this credential? This cannot be undone.")) return;

      try {
        deleteBtn.disabled = true;

        const resp = await deleteVaultItem(id);
        if (!resp.ok) {
          const msg = `Delete failed (${resp.status}).`;
          setFlash(msg, "error");
          deleteBtn.disabled = false;
          return;
        }

        tr.remove();
        setFlash("Deleted.", "info");

        if (tbody.children.length === 0) {
          messageRow(tbody, "No credentials yet.");
        }
      } catch (err) {
        setFlash(`Delete failed: ${String(err)}`, "error");
        deleteBtn.disabled = false;
      }
    });
    deleteBtn.appendChild(spriteIcon("i-trash"));

    row.appendChild(viewBtn);
    row.appendChild(deleteBtn);
    actionsTd.appendChild(row);

    tr.appendChild(nameTd);
    tr.appendChild(kindTd);
    tr.appendChild(updatedTd);
    tr.appendChild(rotatedTd);
    tr.appendChild(actionsTd);

    tbody.appendChild(tr);
  }
}

export async function loadVaultCredentialsTable(): Promise<void> {
  const tbody = qs<HTMLTableSectionElement>("#vault-rows");
  if (!tbody) return;

  try {
    const resp = await fetch("/api/v1/vault-items/", {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });

    if (!resp.ok) {
      const msg = `Failed to load vault items (${resp.status}).`;
      setFlash(msg, "error");
      messageRow(tbody, msg);
      return;
    }

    const data = (await resp.json()) as VaultListResponse;
    renderItems(tbody, toItems(data));
  } catch (err) {
    const msg = `Network error loading vault items: ${String(err)}`;
    setFlash(msg, "error");
    messageRow(tbody, msg);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  void loadVaultCredentialsTable();
});