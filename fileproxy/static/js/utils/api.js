import { getCookie } from "./cookies.js";
export async function apiMultipart(url, formData, opts) {
    const method = (opts?.method ?? "POST").toUpperCase();
    const headers = {};
    const csrf = getCookie("csrftoken");
    if (csrf)
        headers["X-CSRFToken"] = csrf;
    const resp = await fetch(url, {
        method,
        credentials: "same-origin",
        headers,
        body: formData,
    });
    const isJson = (resp.headers.get("content-type") ?? "").includes("application/json");
    const data = isJson ? await resp.json() : await resp.text();
    if (!resp.ok) {
        const detail = typeof data === "object" && data && "detail" in data
            ? String(data.detail ?? "")
            : `Request failed (${resp.status})`;
        throw new Error(detail || `Request failed (${resp.status})`);
    }
    return data;
}
export async function apiJson(url, opts) {
    const method = (opts?.method ?? "GET").toUpperCase();
    const headers = {};
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
        const csrf = getCookie("csrftoken");
        if (csrf)
            headers["X-CSRFToken"] = csrf;
        headers["Content-Type"] = "application/json";
    }
    const resp = await fetch(url, {
        method,
        credentials: "same-origin",
        headers,
        body: opts?.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
    const isJson = (resp.headers.get("content-type") ?? "").includes("application/json");
    const data = isJson ? await resp.json() : await resp.text();
    if (!resp.ok) {
        const detail = typeof data === "object" && data && "detail" in data
            ? String(data.detail ?? "")
            : `Request failed (${resp.status})`;
        throw new Error(detail || `Request failed (${resp.status})`);
    }
    return data;
}
//# sourceMappingURL=api.js.map