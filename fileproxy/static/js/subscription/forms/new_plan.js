import { getCsrfToken } from '../../utils/cookies.js';
import { qs, setFlash } from '../../utils/dom.js';
function numOrNull(form, name) {
    const el = qs(`[name="${name}"]`, form);
    const val = (el?.value ?? '').trim();
    if (!val)
        return null;
    const n = parseInt(val, 10);
    return isNaN(n) ? null : n;
}
function requireStr(form, name, label) {
    const el = qs(`[name="${name}"]`, form);
    const val = (el?.value ?? '').trim();
    if (!val) {
        setFlash(`${label} is required.`, 'error');
        throw new Error('validation');
    }
    return val;
}
document.addEventListener('DOMContentLoaded', () => {
    const form = qs('#plan-form');
    const submitBtn = qs('#submit-btn');
    if (!form || !submitBtn)
        return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        let name;
        try {
            name = requireStr(form, 'name', 'Plan name');
        }
        catch {
            return;
        }
        const isDefaultEl = qs("[name='is_default']", form);
        const is_default = isDefaultEl?.checked ?? false;
        const payload = {
            name,
            is_default,
            enumerate_limit: numOrNull(form, 'enumerate_limit'),
            read_limit: numOrNull(form, 'read_limit'),
            write_limit: numOrNull(form, 'write_limit'),
            delete_limit: numOrNull(form, 'delete_limit'),
            read_transfer_limit_bytes: numOrNull(form, 'read_transfer_limit_bytes'),
            write_transfer_limit_bytes: numOrNull(form, 'write_transfer_limit_bytes'),
        };
        submitBtn.disabled = true;
        try {
            const csrf = getCsrfToken();
            const resp = await fetch('/api/v1/subscription/plans/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Accept: 'application/json',
                    ...(csrf ? { 'X-CSRFToken': csrf } : {}),
                },
                body: JSON.stringify(payload),
                credentials: 'same-origin',
            });
            if (!resp.ok) {
                const data = (await resp.json().catch(() => ({})));
                const msg = data['detail'] ?? data['name'] ?? `Error ${resp.status}`;
                setFlash(String(msg), 'error');
                submitBtn.disabled = false;
                return;
            }
            setFlash('Plan created.', 'info');
            window.location.href = '/subscription/plans/';
        }
        catch (err) {
            setFlash(`Network error: ${String(err)}`, 'error');
            submitBtn.disabled = false;
        }
    });
});
//# sourceMappingURL=new_plan.js.map