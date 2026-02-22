import { qs as qsMaybe, setFlash } from "../utils/dom.js";
import { apiJson } from "../utils/api.js";
import { getCsrfToken } from "../utils/cookies.js";
/* ----------------------------- DOM helpers ----------------------------- */
function mustGet(selector, root = document) {
    const el = qsMaybe(selector, root);
    if (!el)
        throw new Error(`Missing element: ${selector}`);
    return el;
}
const el = {
    vaultList: () => mustGet("#vault-list"),
    entries: () => mustGet("#entries"),
    crumbs: () => mustGet("#path-crumbs"),
    title: () => mustGet("#browser-title"),
    subtitle: () => mustGet("#browser-subtitle"),
    refresh: () => mustGet("#refresh"),
    vaultRefresh: () => mustGet("#vault-refresh"),
    up: () => mustGet("#up"),
    uploadFile: () => mustGet("#upload-file"),
    uploadName: () => mustGet("#upload-name"),
    uploadBtn: () => mustGet("#upload"),
    uploadHint: () => mustGet("#upload-hint"),
    uploadStatus: () => mustGet("#upload-status"),
    pageControls: () => mustGet("#page-controls"),
};
/* ----------------------------- State ----------------------------- */
const state = {
    vault: null,
    prefix: "",
    pageSize: 50,
    cursors: [null],
    page: 0,
    hasNextPage: false,
};
/* ----------------------------- Small utils ----------------------------- */
function fmtBytes(n) {
    if (n == null)
        return "";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let v = n;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) {
        v /= 1024;
        i += 1;
    }
    return i === 0 ? `${v} ${units[i]}` : `${v.toFixed(1)} ${units[i]}`;
}
function fileIcon(name) {
    const ext = name.split(".").pop()?.toLowerCase() ?? "";
    if (["jpg", "jpeg", "png", "gif", "svg", "webp", "bmp"].includes(ext))
        return "bi-file-earmark-image";
    if (ext === "pdf")
        return "bi-file-earmark-pdf";
    if (["doc", "docx"].includes(ext))
        return "bi-file-earmark-word";
    if (["xls", "xlsx", "csv"].includes(ext))
        return "bi-file-earmark-excel";
    if (["ppt", "pptx"].includes(ext))
        return "bi-file-earmark-slides";
    if (["zip", "gz", "tar", "bz2", "7z", "rar"].includes(ext))
        return "bi-file-earmark-zip";
    if (["mp4", "mov", "avi", "mkv", "webm"].includes(ext))
        return "bi-file-earmark-play";
    if (["mp3", "wav", "ogg", "flac", "m4a"].includes(ext))
        return "bi-file-earmark-music";
    if (["js", "ts", "py", "java", "c", "cpp", "cs", "go", "rs", "rb", "php", "html", "css", "json", "xml", "yaml", "yml"].includes(ext))
        return "bi-file-earmark-code";
    if (["txt", "md", "log"].includes(ext))
        return "bi-file-earmark-text";
    return "bi-file-earmark";
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
function updateUploadButtonState() {
    const hasFile = Boolean(el.uploadFile().files?.[0]);
    el.uploadBtn().disabled = !(state.vault && hasFile);
}
function setBrowserHeader() {
    const hasVault = Boolean(state.vault);
    el.up().disabled = !hasVault || state.prefix === "";
    el.refresh().disabled = !hasVault;
    if (!hasVault) {
        el.title().textContent = "Select a vault";
        el.subtitle().textContent = "";
        el.uploadHint().textContent = "Select a vault to enable upload.";
        el.uploadStatus().textContent = "";
        setUploadEnabled(false);
        return;
    }
    el.title().textContent = state.vault;
    el.subtitle().textContent = state.prefix ? `/${state.prefix}` : "/";
    el.uploadHint().textContent = state.prefix ? `Uploading into /${state.prefix}` : "Uploading into /";
    setUploadEnabled(true);
    updateUploadButtonState();
}
function setCrumbs() {
    const ol = el.crumbs();
    ol.innerHTML = "";
    if (!state.vault) {
        ol.innerHTML = `<li class="breadcrumb-item text-muted">—</li>`;
        return;
    }
    const parts = state.prefix.split("/").filter(Boolean);
    const addCrumbLink = (label, prefix) => {
        const li = document.createElement("li");
        li.className = "breadcrumb-item";
        const a = document.createElement("a");
        a.href = "#";
        a.textContent = label;
        a.addEventListener("click", (e) => {
            e.preventDefault();
            state.prefix = prefix;
            resetPagination();
            void refresh();
        });
        li.appendChild(a);
        ol.appendChild(li);
    };
    addCrumbLink("root", "");
    let accum = "";
    parts.forEach((p, idx) => {
        accum += `${p}/`;
        const isLast = idx === parts.length - 1;
        const li = document.createElement("li");
        li.className = "breadcrumb-item";
        if (isLast) {
            li.classList.add("active");
            li.setAttribute("aria-current", "page");
            li.textContent = p;
        }
        else {
            const a = document.createElement("a");
            a.href = "#";
            a.textContent = p;
            const target = accum;
            a.addEventListener("click", (e) => {
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
        const key = obj.path || "";
        if (!key.startsWith(prefix))
            continue;
        const rest = key.slice(prefix.length);
        if (!rest)
            continue;
        const slash = rest.indexOf("/");
        if (slash !== -1) {
            const folderName = rest.slice(0, slash);
            const folderPath = `${prefix}${folderName}/`;
            if (!folders.has(folderPath)) {
                folders.set(folderPath, { kind: "folder", name: folderName, path: folderPath });
            }
            continue;
        }
        files.push({ kind: "file", name: rest, path: key, size: obj.size ?? null });
    }
    const out = [...folders.values(), ...files];
    out.sort((a, b) => {
        if (a.kind !== b.kind)
            return a.kind === "folder" ? -1 : 1;
        return a.name.localeCompare(b.name);
    });
    return out;
}
/* ----------------------------- Rendering ----------------------------- */
function makeFileActions(entry) {
    const dd = document.createElement("div");
    dd.className = "dropdown dropup";
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "btn btn-sm btn-outline-secondary dropdown-toggle";
    toggle.setAttribute("data-bs-toggle", "dropdown");
    toggle.setAttribute("data-bs-boundary", "viewport");
    toggle.setAttribute("data-bs-reference", "parent");
    toggle.setAttribute("aria-expanded", "false");
    toggle.title = "Actions";
    toggle.innerHTML = `<i class="bi bi-three-dots"></i>`;
    const menu = document.createElement("ul");
    menu.className = "dropdown-menu dropdown-menu-end";
    const addItem = (html, onClick, className = "dropdown-item") => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = className;
        btn.innerHTML = html;
        btn.addEventListener("click", () => void onClick());
        li.appendChild(btn);
        menu.appendChild(li);
    };
    const addDivider = () => {
        const li = document.createElement("li");
        li.innerHTML = `<hr class="dropdown-divider">`;
        menu.appendChild(li);
    };
    addItem(`<i class="bi bi-download me-2"></i>Download`, () => {
        if (!state.vault)
            return;
        const url = `/api/v1/files/${encodeURIComponent(state.vault)}/download/?path=${encodeURIComponent(entry.path)}`;
        const a = document.createElement("a");
        a.href = url;
        a.download = entry.name || "download";
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
            await apiJson(`/api/v1/files/${encodeURIComponent(state.vault)}/object/?path=${encodeURIComponent(entry.path)}`, { method: "DELETE" });
            setFlash("Deleted.", "success");
            await refresh();
        }
        catch (err) {
            setFlash(err instanceof Error ? err.message : "Delete failed.", "error");
        }
    }, "dropdown-item text-danger");
    dd.appendChild(toggle);
    dd.appendChild(menu);
    return dd;
}
function render(entries) {
    const tbody = el.entries();
    tbody.innerHTML = "";
    if (!state.vault) {
        tbody.innerHTML =
            `<tr><td colspan="4" class="text-muted small">Choose a vault from the left to start browsing.</td></tr>`;
        return;
    }
    if (!entries.length) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-muted small">This folder is empty.</td></tr>`;
        return;
    }
    for (const entry of entries) {
        const tr = document.createElement("tr");
        const tdName = document.createElement("td");
        const tdPath = document.createElement("td");
        const tdSize = document.createElement("td");
        const tdAct = document.createElement("td");
        tdAct.className = "text-end";
        if (entry.kind === "folder") {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "btn btn-link btn-sm p-0 text-decoration-none";
            btn.innerHTML = `<i class="bi bi-folder2 me-2 opacity-75"></i>${entry.name}`;
            btn.addEventListener("click", () => {
                state.prefix = entry.path;
                resetPagination();
                void refresh();
            });
            tdName.appendChild(btn);
            tdPath.textContent = entry.path;
            tdSize.textContent = "";
        }
        else {
            const icon = fileIcon(entry.name);
            tdName.innerHTML = `<i class="bi ${icon} me-2 opacity-75"></i>${entry.name}`;
            tdPath.textContent = entry.path;
            tdSize.textContent = fmtBytes(entry.size);
            tdAct.appendChild(makeFileActions(entry));
        }
        tr.appendChild(tdName);
        tr.appendChild(tdPath);
        tr.appendChild(tdSize);
        tr.appendChild(tdAct);
        tbody.appendChild(tr);
    }
}
function renderPagination() {
    const host = el.pageControls();
    host.innerHTML = "";
    if (!state.vault)
        return;
    // Prev button
    const prevBtn = document.createElement("button");
    prevBtn.type = "button";
    prevBtn.className = "btn btn-sm btn-outline-secondary";
    prevBtn.innerHTML = `<i class="bi bi-chevron-left"></i>`;
    prevBtn.disabled = state.page === 0;
    prevBtn.addEventListener("click", () => {
        state.page--;
        void refresh();
    });
    // Page label
    const pageLabel = document.createElement("span");
    pageLabel.className = "text-muted";
    pageLabel.textContent = `Page ${state.page + 1}`;
    // Next button
    const nextBtn = document.createElement("button");
    nextBtn.type = "button";
    nextBtn.className = "btn btn-sm btn-outline-secondary";
    nextBtn.innerHTML = `<i class="bi bi-chevron-right"></i>`;
    nextBtn.disabled = !state.hasNextPage;
    nextBtn.addEventListener("click", () => {
        state.page++;
        void refresh();
    });
    // Nav group (left side)
    const navGroup = document.createElement("div");
    navGroup.className = "d-flex align-items-center gap-2";
    navGroup.appendChild(prevBtn);
    navGroup.appendChild(pageLabel);
    navGroup.appendChild(nextBtn);
    // Page size selector (right side)
    const sizeLabel = document.createElement("label");
    sizeLabel.className = "text-muted d-flex align-items-center gap-1";
    const sizeSelect = document.createElement("select");
    sizeSelect.className = "form-select form-select-sm";
    sizeSelect.style.width = "auto";
    for (const size of [25, 50, 100, 200]) {
        const opt = document.createElement("option");
        opt.value = String(size);
        opt.textContent = String(size);
        opt.selected = size === state.pageSize;
        sizeSelect.appendChild(opt);
    }
    sizeSelect.addEventListener("change", () => {
        state.pageSize = Number(sizeSelect.value);
        resetPagination();
        void refresh();
    });
    sizeLabel.appendChild(document.createTextNode("Per page:"));
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
        params.set("prefix", state.prefix);
    const cursor = state.cursors[state.page];
    if (cursor)
        params.set("cursor", cursor);
    params.set("page_size", String(state.pageSize));
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
    el.up().disabled = state.prefix === "";
    updateUploadButtonState();
}
function uploadWithProgress(url, formData) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const csrf = getCsrfToken();
        xhr.open("POST", url);
        if (csrf)
            xhr.setRequestHeader("X-CSRFToken", csrf);
        xhr.withCredentials = true;
        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                resolve();
            }
            else {
                let detail = `Request failed (${xhr.status})`;
                try {
                    const data = JSON.parse(xhr.responseText);
                    if (data?.detail)
                        detail = String(data.detail);
                }
                catch { /* ignore parse errors */ }
                reject(new Error(detail));
            }
        };
        xhr.onerror = () => reject(new Error("Network error"));
        xhr.send(formData);
    });
}
async function doUpload() {
    if (!state.vault)
        return;
    const file = el.uploadFile().files?.[0] ?? null;
    if (!file)
        return;
    const name = (el.uploadName().value || file.name).trim();
    if (!name) {
        setFlash("Name is required.", "error");
        return;
    }
    const path = `${state.prefix}${name}`;
    el.uploadStatus().textContent = "Uploading…";
    el.uploadBtn().disabled = true;
    try {
        const form = new FormData();
        form.append("path", path);
        form.append("file", file);
        await uploadWithProgress(`/api/v1/files/${encodeURIComponent(state.vault)}/write/`, form);
        el.uploadStatus().textContent = "Uploaded.";
        setFlash("Upload complete.", "success");
        el.uploadFile().value = "";
        el.uploadName().value = "";
        await refresh();
    }
    catch (e) {
        el.uploadStatus().textContent = "";
        setFlash(e instanceof Error ? e.message : "Upload failed.", "error");
    }
    finally {
        updateUploadButtonState();
    }
}
function goUp() {
    if (!state.prefix)
        return;
    const parts = state.prefix.split("/").filter(Boolean);
    parts.pop();
    state.prefix = parts.length ? `${parts.join("/")}/` : "";
    resetPagination();
    void refresh();
}
async function loadVaults() {
    const host = el.vaultList();
    host.innerHTML = `<div class="text-muted small">Loading…</div>`;
    const items = await apiJson("/api/v1/files/");
    if (!items.length) {
        host.innerHTML = `<div class="text-muted small">No vault items yet.</div>`;
        state.vault = null;
        state.prefix = "";
        setBrowserHeader();
        setCrumbs();
        render([]);
        return;
    }
    host.innerHTML = "";
    let firstAnchor = null;
    for (const it of items) {
        const a = document.createElement("a");
        a.href = "#";
        a.className =
            "list-group-item list-group-item-action d-flex align-items-center justify-content-between files-vault-item";
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
        a.addEventListener("click", (e) => {
            e.preventDefault();
            state.vault = it.name;
            state.prefix = "";
            resetPagination();
            void refresh();
            for (const elItem of Array.from(host.querySelectorAll(".list-group-item"))) {
                elItem.classList.remove("active");
            }
            a.classList.add("active");
        });
        if (!firstAnchor)
            firstAnchor = a;
        host.appendChild(a);
    }
    if (!state.vault && firstAnchor)
        firstAnchor.click();
}
/* ----------------------------- Boot ----------------------------- */
document.addEventListener("DOMContentLoaded", async () => {
    await loadVaults();
    setBrowserHeader();
    setCrumbs();
    updateUploadButtonState();
    el.vaultRefresh().addEventListener("click", () => void loadVaults());
    el.refresh().addEventListener("click", () => void refresh());
    el.up().addEventListener("click", goUp);
    el.uploadFile().addEventListener("change", () => {
        const f = el.uploadFile().files?.[0];
        if (f)
            el.uploadName().value = f.name;
        updateUploadButtonState();
    });
    el.uploadName().addEventListener("input", updateUploadButtonState);
    el.uploadBtn().addEventListener("click", () => void doUpload());
});
//# sourceMappingURL=browse.js.map