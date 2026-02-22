import { setFlash } from "../../utils/dom.js";
function qs(selector, root = document) {
    const el = root.querySelector(selector);
    if (!el)
        throw new Error(`Missing element: ${selector}`);
    return el;
}
function getItemId() {
    const el = document.getElementById("vault-item-id");
    if (!el)
        throw new Error("Missing vault-item-id script tag");
    const n = JSON.parse(el.textContent || "0");
    if (!Number.isFinite(n))
        throw new Error("Invalid item id");
    return n;
}
function getCSRFToken() {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : null;
}
async function api(path, opts = {}) {
    const headers = new Headers(opts.headers || {});
    headers.set("Accept", "application/json");
    const csrf = getCSRFToken();
    const method = (opts.method || "GET").toUpperCase();
    if (csrf && method !== "GET")
        headers.set("X-CSRFToken", csrf);
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
        return "Never";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime()))
        return iso;
    return d.toLocaleString();
}
function render(item) {
    qs("#item-title").textContent = item.name;
    qs("#item-subtitle").textContent = "Credential metadata and actions.";
    qs("#meta-name").textContent = item.name;
    qs("#meta-kind").textContent = item.kind;
    qs("#meta-bucket").textContent = item.bucket ?? "—";
    qs("#meta-created").textContent = fmtDate(item.created_at);
    qs("#meta-updated").textContent = fmtDate(item.updated_at);
    qs("#meta-rotated").textContent = fmtDate(item.rotated_at);
    qs("#meta-id").textContent = String(item.id);
    qs("#edit-name").value = item.name;
}
function showEdit(show) {
    qs("#edit-panel").style.display = show ? "block" : "none";
}
document.addEventListener("DOMContentLoaded", async () => {
    const itemId = getItemId();
    const btnTest = qs("#btn-test");
    const btnEdit = qs("#btn-edit");
    const btnDelete = qs("#btn-delete");
    const btnSave = qs("#btn-save");
    const btnCancelEdit = qs("#btn-cancel-edit");
    const editName = qs("#edit-name");
    let current = null;
    async function load() {
        try {
            const item = await api(`/api/v1/vault-items/${itemId}/`);
            current = item;
            render(item);
        }
        catch (e) {
            setFlash(`Failed to load item: ${e.message}`, "error");
        }
    }
    btnEdit.addEventListener("click", () => {
        showEdit(true);
        editName.focus();
    });
    btnCancelEdit.addEventListener("click", () => {
        showEdit(false);
        if (current)
            editName.value = current.name;
    });
    btnSave.addEventListener("click", async () => {
        const name = editName.value.trim();
        if (!name)
            return setFlash("Name is required.", "error");
        try {
            await api(`/api/v1/vault-items/${itemId}/rename/`, {
                method: "POST",
                body: JSON.stringify({ name }),
            });
            setFlash("Updated.", "success");
            showEdit(false);
            await load();
        }
        catch (e) {
            setFlash(`Update failed: ${e.message}`, "error");
        }
    });
    btnTest.addEventListener("click", async () => {
        const prevText = btnTest.textContent || "Test";
        btnTest.disabled = true;
        btnTest.textContent = "Testing…";
        try {
            const out = await api(`/api/v1/vault-items/${itemId}/test/`, { method: "POST" });
            if (out.ok) {
                setFlash(out.message || "Connection OK.", "success");
            }
            else {
                setFlash(out.message || "Test failed.", "error");
            }
        }
        catch (e) {
            setFlash(`Test failed: ${e.message}`, "error");
        }
        finally {
            btnTest.disabled = false;
            btnTest.textContent = prevText;
        }
    });
    btnDelete.addEventListener("click", async () => {
        if (!confirm("Delete this credential? This cannot be undone."))
            return;
        try {
            await api(`/api/v1/vault-items/${itemId}/`, { method: "DELETE" });
            window.location.href = "/vault/";
        }
        catch (e) {
            setFlash(`Delete failed: ${e.message}`, "error");
        }
    });
    await load();
});
//# sourceMappingURL=detail.js.map