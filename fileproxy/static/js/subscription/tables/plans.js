import { getCsrfToken } from '../../utils/cookies.js';
import { qs, setFlash } from '../../utils/dom.js';
function fmtLimit(val) {
    return val === null ? '∞' : String(val);
}
function esc(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}
async function deletePlan(id) {
    const csrf = getCsrfToken();
    const resp = await fetch(`/api/v1/subscription/plans/${id}/`, {
        method: 'DELETE',
        headers: { Accept: 'application/json', ...(csrf ? { 'X-CSRFToken': csrf } : {}) },
        credentials: 'same-origin',
    });
    if (!resp.ok)
        throw new Error(`Delete failed (${resp.status})`);
}
async function setDefault(id) {
    const csrf = getCsrfToken();
    const resp = await fetch(`/api/v1/subscription/plans/${id}/set-default/`, {
        method: 'POST',
        headers: { Accept: 'application/json', ...(csrf ? { 'X-CSRFToken': csrf } : {}) },
        credentials: 'same-origin',
    });
    if (!resp.ok)
        throw new Error(`Set default failed (${resp.status})`);
}
function renderPlans(tbody, plans, staffMode) {
    tbody.innerHTML = '';
    const warningEl = qs('#no-default-warning');
    if (warningEl) {
        const hasDefault = plans.some((p) => p.is_default && !p.expires_at);
        warningEl.classList.toggle('d-none', hasDefault);
    }
    if (!plans.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = staffMode ? 7 : 6;
        td.className = 'text-secondary';
        td.textContent = 'No plans defined.';
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }
    for (const plan of plans) {
        const tr = document.createElement('tr');
        const nameTd = document.createElement('td');
        if (staffMode) {
            const a = document.createElement('a');
            a.href = `/subscription/plans/${plan.id}/`;
            a.textContent = plan.name;
            nameTd.appendChild(a);
        }
        else {
            nameTd.textContent = plan.name;
        }
        const defaultTd = document.createElement('td');
        if (plan.is_default) {
            const badge = document.createElement('span');
            badge.className = 'badge bg-success';
            badge.textContent = 'Default';
            defaultTd.appendChild(badge);
        }
        else {
            defaultTd.textContent = '—';
        }
        const enumTd = document.createElement('td');
        enumTd.textContent = fmtLimit(plan.enumerate_limit);
        const readTd = document.createElement('td');
        readTd.textContent = fmtLimit(plan.read_limit);
        const writeTd = document.createElement('td');
        writeTd.textContent = fmtLimit(plan.write_limit);
        const deleteTd = document.createElement('td');
        deleteTd.textContent = fmtLimit(plan.delete_limit);
        tr.appendChild(nameTd);
        tr.appendChild(defaultTd);
        tr.appendChild(enumTd);
        tr.appendChild(readTd);
        tr.appendChild(writeTd);
        tr.appendChild(deleteTd);
        if (staffMode) {
            const actionsTd = document.createElement('td');
            actionsTd.className = 'text-end';
            const group = document.createElement('div');
            group.className = 'btn-group btn-group-sm';
            if (!plan.is_default) {
                const defaultBtn = document.createElement('button');
                defaultBtn.type = 'button';
                defaultBtn.className = 'btn btn-outline-secondary';
                defaultBtn.textContent = 'Set Default';
                defaultBtn.addEventListener('click', async () => {
                    try {
                        defaultBtn.disabled = true;
                        await setDefault(plan.id);
                        setFlash('Default plan updated.', 'info');
                        await loadPlans();
                    }
                    catch (err) {
                        setFlash(String(err), 'error');
                        defaultBtn.disabled = false;
                    }
                });
                group.appendChild(defaultBtn);
            }
            const deleteBtn = document.createElement('button');
            deleteBtn.type = 'button';
            deleteBtn.className = 'btn btn-outline-danger';
            deleteBtn.textContent = 'Delete';
            deleteBtn.addEventListener('click', async () => {
                if (!confirm(`Delete plan "${esc(plan.name)}"?`))
                    return;
                try {
                    deleteBtn.disabled = true;
                    await deletePlan(plan.id);
                    setFlash('Plan deleted.', 'info');
                    tr.remove();
                }
                catch (err) {
                    setFlash(String(err), 'error');
                    deleteBtn.disabled = false;
                }
            });
            group.appendChild(deleteBtn);
            actionsTd.appendChild(group);
            tr.appendChild(actionsTd);
        }
        tbody.appendChild(tr);
    }
}
async function loadPlans() {
    const tbody = qs('#plans-rows');
    if (!tbody)
        return;
    const isStaff = tbody.dataset.isStaff === 'true';
    try {
        const resp = await fetch('/api/v1/subscription/plans/', {
            headers: { Accept: 'application/json' },
            credentials: 'same-origin',
        });
        if (!resp.ok) {
            setFlash(`Failed to load plans (${resp.status}).`, 'error');
            return;
        }
        const data = (await resp.json());
        const plans = Array.isArray(data) ? data : (data.results ?? []);
        renderPlans(tbody, plans, isStaff);
    }
    catch (err) {
        setFlash(`Network error: ${String(err)}`, 'error');
    }
}
document.addEventListener('DOMContentLoaded', () => {
    void loadPlans();
});
//# sourceMappingURL=plans.js.map