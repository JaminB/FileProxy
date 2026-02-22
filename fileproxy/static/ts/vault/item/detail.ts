import { setFlash } from "../../utils/dom.js";

const KIND_META: Record<string, { label: string; src: string }> = {
  aws_s3:         { label: "Amazon S3",    src: "/static/images/logos/s3.svg" },
  gdrive_oauth2:  { label: "Google Drive", src: "/static/images/logos/gdrive.svg" },
  dropbox_oauth2: { label: "Dropbox",      src: "/static/images/logos/dropbox.png" },
};

type VaultItemDetail = {
  id: number;
  name: string;
  kind: string;
  created_at: string;
  updated_at: string;
  rotated_at: string | null;
};

function qs<T extends Element>(selector: string, root: ParentNode = document): T {
  const el = root.querySelector(selector);
  if (!el) throw new Error(`Missing element: ${selector}`);
  return el as T;
}

function getItemId(): number {
  const el = document.getElementById("vault-item-id");
  if (!el) throw new Error("Missing vault-item-id script tag");
  const n = JSON.parse(el.textContent || "0");
  if (!Number.isFinite(n)) throw new Error("Invalid item id");
  return n;
}

function getCSRFToken(): string | null {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

async function api<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers = new Headers(opts.headers || {});
  headers.set("Accept", "application/json");

  const csrf = getCSRFToken();
  const method = (opts.method || "GET").toUpperCase();
  if (csrf && method !== "GET") headers.set("X-CSRFToken", csrf);

  if (opts.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const resp = await fetch(path, {
    credentials: "same-origin",
    ...opts,
    headers,
  });

  if (!resp.ok) {
    let msg = `${resp.status} ${resp.statusText}`;
    try {
      const j = await resp.json();
      msg = typeof j?.detail === "string" ? j.detail : JSON.stringify(j);
    } catch {
      // ignore
    }
    throw new Error(msg);
  }

  // Some endpoints (DELETE) may return empty body
  const text = await resp.text();
  return (text ? JSON.parse(text) : ({} as T)) as T;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "Never";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function render(item: VaultItemDetail): void {
  qs<HTMLElement>("#item-title").textContent = item.name;

  qs<HTMLElement>("#meta-name").textContent = item.name;

  const kindEl = qs<HTMLElement>("#meta-kind");
  const km = KIND_META[item.kind ?? ""];
  if (km) {
    const img = document.createElement("img");
    img.src = km.src; img.alt = ""; img.width = 14; img.height = 14;
    img.className = "me-1 opacity-75";
    img.setAttribute("aria-hidden", "true");
    kindEl.innerHTML = "";
    kindEl.appendChild(img);
    kindEl.appendChild(document.createTextNode(km.label));
  } else {
    kindEl.textContent = item.kind;
  }

  qs<HTMLElement>("#meta-created").textContent = fmtDate(item.created_at);
  qs<HTMLElement>("#meta-updated").textContent = fmtDate(item.updated_at);
  qs<HTMLElement>("#meta-rotated").textContent = fmtDate(item.rotated_at);
  qs<HTMLElement>("#meta-id").textContent = String(item.id);

  qs<HTMLInputElement>("#edit-name").value = item.name;
}

function showEdit(show: boolean): void {
  qs<HTMLElement>("#edit-panel").style.display = show ? "block" : "none";
}

document.addEventListener("DOMContentLoaded", async () => {
  const itemId = getItemId();

  const btnTest = qs<HTMLButtonElement>("#btn-test");
  const btnEdit = qs<HTMLButtonElement>("#btn-edit");
  const btnDelete = qs<HTMLButtonElement>("#btn-delete");
  const btnSave = qs<HTMLButtonElement>("#btn-save");
  const btnCancelEdit = qs<HTMLButtonElement>("#btn-cancel-edit");
  const editName = qs<HTMLInputElement>("#edit-name");

  let current: VaultItemDetail | null = null;

  async function load(): Promise<void> {
    try {
      const item = await api<VaultItemDetail>(`/api/v1/vault-items/${itemId}/`);
      current = item;
      render(item);
    } catch (e) {
      setFlash(`Failed to load item: ${(e as Error).message}`, "error");
    }
  }

  btnEdit.addEventListener("click", () => {
    showEdit(true);
    editName.focus();
  });

  btnCancelEdit.addEventListener("click", () => {
    showEdit(false);
    if (current) editName.value = current.name;
  });

  btnSave.addEventListener("click", async () => {
    const name = editName.value.trim();
    if (!name) return setFlash("Name is required.", "error");

    try {
      await api(`/api/v1/vault-items/${itemId}/rename/`, {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      setFlash("Updated.", "success");
      showEdit(false);
      await load();
    } catch (e) {
      setFlash(`Update failed: ${(e as Error).message}`, "error");
    }
  });

  btnTest.addEventListener("click", async () => {
    const prevText = btnTest.textContent || "Test";
    btnTest.disabled = true;
    btnTest.textContent = "Testing…";

    try {
      const out = await api<{ ok: boolean; message: string; details?: unknown }>(
        `/api/v1/vault-items/${itemId}/test/`,
        { method: "POST" },
      );
      if (out.ok) {
        setFlash(out.message || "Connection OK.", "success");
      } else {
        setFlash(out.message || "Test failed.", "error");
      }
    } catch (e) {
      setFlash(`Test failed: ${(e as Error).message}`, "error");
    } finally {
      btnTest.disabled = false;
      btnTest.textContent = prevText;
    }
  });

  btnDelete.addEventListener("click", async () => {
    if (!confirm("Delete this credential? This cannot be undone.")) return;

    try {
      await api(`/api/v1/vault-items/${itemId}/`, { method: "DELETE" });
      window.location.href = "/vault/";
    } catch (e) {
      setFlash(`Delete failed: ${(e as Error).message}`, "error");
    }
  });

  await load();
});
