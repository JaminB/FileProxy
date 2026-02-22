import { getCsrfToken } from "../../utils/cookies.js";
import { qs, setFlash } from "../../utils/dom.js";
function setSubmitting(form, submitting) {
    const btn = qs('button[type="submit"]', form);
    if (!btn)
        return;
    const original = btn.dataset.originalText ?? btn.textContent ?? "Submit";
    btn.dataset.originalText = original;
    btn.disabled = submitting;
    btn.setAttribute("aria-busy", submitting ? "true" : "false");
    btn.textContent = submitting ? "Saving…" : original;
}
function parseApiError(data, status) {
    if (!data)
        return `Request failed (${status}).`;
    if (typeof data === "string")
        return data;
    const msg = data.detail ?? data.error;
    if (msg)
        return String(msg);
    const errors = data.errors;
    if (errors && typeof errors === "object") {
        const parts = [];
        for (const [field, v] of Object.entries(errors)) {
            if (Array.isArray(v))
                parts.push(`${field}: ${v.join(", ")}`);
            else
                parts.push(`${field}: ${String(v)}`);
        }
        if (parts.length)
            return parts.join(" | ");
    }
    return `Request failed (${status}).`;
}
async function apiPostJson(endpoint, payload) {
    const csrf = getCsrfToken();
    return fetch(endpoint, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Accept": "application/json",
            ...(csrf ? { "X-CSRFToken": csrf } : {}),
        },
        credentials: "same-origin",
        body: JSON.stringify(payload),
    });
}
export function initProviderForm(opts) {
    const form = qs(opts.formSelector);
    if (!form)
        return;
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        setFlash("");
        setSubmitting(form, true);
        try {
            const payload = opts.buildPayload(form);
            const resp = await apiPostJson(opts.endpoint, payload);
            if (resp.ok) {
                if (opts.onSuccess) {
                    const data = await resp.json().catch(() => null);
                    opts.onSuccess(data);
                    return;
                }
                const redirect = form.dataset.successRedirect ?? opts.successRedirect;
                if (redirect) {
                    window.location.assign(redirect);
                    return;
                }
                setFlash(opts.successMessage ?? "Saved.", "info");
                return;
            }
            // Try to read JSON error
            const ct = resp.headers.get("content-type") ?? "";
            if (ct.includes("application/json")) {
                const data = await resp.json().catch(() => null);
                setFlash(parseApiError(data, resp.status), "error");
            }
            else {
                const txt = await resp.text().catch(() => "");
                setFlash(txt || `Request failed (${resp.status}).`, "error");
            }
        }
        catch (err) {
            setFlash(`Network error: ${String(err)}`, "error");
        }
        finally {
            setSubmitting(form, false);
        }
    });
}
//# sourceMappingURL=core.js.map