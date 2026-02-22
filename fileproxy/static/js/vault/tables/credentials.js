import { qs, setFlash } from "../../utils/dom.js";
import { getCsrfToken } from "../../utils/cookies.js";
const KIND_META = {
    aws_s3: { label: "Amazon S3", src: "/static/images/logos/s3.svg" },
    gdrive_oauth2: { label: "Google Drive", src: "/static/images/logos/gdrive.svg" },
    dropbox_oauth2: { label: "Dropbox", src: "/static/images/logos/dropbox.png" },
};
async function deleteVaultItem(id) {
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
function toItems(payload) {
    if (Array.isArray(payload))
        return payload;
    const results = payload.results;
    return Array.isArray(results) ? results : [];
}
function fmtDate(value) {
    if (!value)
        return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime()))
        return value;
    return d.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    });
}
function clear(tbody) {
    tbody.innerHTML = "";
}
function messageRow(tbody, text) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.className = "text-secondary";
    td.textContent = text;
    tr.appendChild(td);
    tbody.appendChild(tr);
}
function bsIcon(className) {
    const i = document.createElement("i");
    i.className = className;
    i.setAttribute("aria-hidden", "true");
    return i;
}
function actionButton(label, btnClasses, iconClasses, onClick) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `btn ${btnClasses}`;
    btn.title = label;
    btn.setAttribute("aria-label", label);
    btn.appendChild(bsIcon(`${iconClasses} me-1`));
    btn.appendChild(document.createTextNode(label));
    btn.addEventListener("click", onClick);
    return btn;
}
function renderItems(tbody, items) {
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
        const km = KIND_META[item.kind ?? ""];
        if (km) {
            const img = document.createElement("img");
            img.src = km.src;
            img.alt = "";
            img.width = 14;
            img.height = 14;
            img.className = "me-1 opacity-75";
            img.setAttribute("aria-hidden", "true");
            kindTd.appendChild(img);
            kindTd.appendChild(document.createTextNode(km.label));
        }
        else {
            kindTd.textContent = item.kind ?? "—";
        }
        const updatedTd = document.createElement("td");
        updatedTd.textContent = fmtDate(item.updated);
        const rotatedTd = document.createElement("td");
        rotatedTd.textContent = fmtDate(item.rotated);
        const actionsTd = document.createElement("td");
        actionsTd.className = "text-end";
        const group = document.createElement("div");
        group.className = "btn-group btn-group-sm";
        group.setAttribute("role", "group");
        group.setAttribute("aria-label", "Vault item actions");
        const id = item.id;
        const viewBtn = actionButton("View", "btn-outline-secondary", "bi bi-eye", () => {
            if (id != null) {
                window.location.href = `/vault/item/${id}/`;
            }
        });
        const deleteBtn = actionButton("Delete", "btn-outline-danger", "bi bi-trash", async () => {
            if (id == null)
                return;
            if (!confirm("Delete this credential? This cannot be undone."))
                return;
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
                // If we removed the last row, show empty state
                if (tbody.querySelectorAll("tr").length === 0) {
                    messageRow(tbody, "No credentials yet.");
                }
            }
            catch (err) {
                setFlash(`Delete failed: ${String(err)}`, "error");
                deleteBtn.disabled = false;
            }
        });
        group.appendChild(viewBtn);
        group.appendChild(deleteBtn);
        actionsTd.appendChild(group);
        tr.appendChild(nameTd);
        tr.appendChild(kindTd);
        tr.appendChild(updatedTd);
        tr.appendChild(rotatedTd);
        tr.appendChild(actionsTd);
        tbody.appendChild(tr);
    }
}
export async function loadVaultCredentialsTable() {
    const tbody = qs("#vault-rows");
    if (!tbody)
        return;
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
        const data = (await resp.json());
        renderItems(tbody, toItems(data));
    }
    catch (err) {
        const msg = `Network error loading vault items: ${String(err)}`;
        setFlash(msg, "error");
        messageRow(tbody, msg);
    }
}
document.addEventListener("DOMContentLoaded", () => {
    void loadVaultCredentialsTable();
});
//# sourceMappingURL=credentials.js.map