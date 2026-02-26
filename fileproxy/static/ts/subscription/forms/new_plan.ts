import { getCsrfToken } from '../../utils/cookies.js';
import { qs, setFlash } from '../../utils/dom.js';

function numOrNull(form: HTMLFormElement, name: string): number | null {
  const el = qs<HTMLInputElement>(`[name="${name}"]`, form);
  const val = (el?.value ?? '').trim();
  if (!val) return null;
  const n = parseInt(val, 10);
  return isNaN(n) ? null : n;
}

function floatOrNull(form: HTMLFormElement, name: string): number | null {
  const el = qs<HTMLInputElement>(`[name="${name}"]`, form);
  const val = (el?.value ?? '').trim();
  if (!val) return null;
  const n = parseFloat(val);
  return isNaN(n) ? null : n;
}

function requireStr(form: HTMLFormElement, name: string, label: string): string {
  const el = qs<HTMLInputElement>(`[name="${name}"]`, form);
  const val = (el?.value ?? '').trim();
  if (!val) {
    setFlash(`${label} is required.`, 'error');
    throw new Error('validation');
  }
  return val;
}

document.addEventListener('DOMContentLoaded', () => {
  const form = qs<HTMLFormElement>('#plan-form');
  const submitBtn = qs<HTMLButtonElement>('#submit-btn');
  if (!form || !submitBtn) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    let name: string;
    try {
      name = requireStr(form, 'name', 'Plan name');
    } catch {
      return;
    }

    const isDefaultEl = qs<HTMLInputElement>("[name='is_default']", form);
    const is_default = isDefaultEl?.checked ?? false;

    const read_mb = floatOrNull(form, 'read_transfer_limit_mb');
    const write_mb = floatOrNull(form, 'write_transfer_limit_mb');
    const payload = {
      name,
      is_default,
      enumerate_limit: numOrNull(form, 'enumerate_limit'),
      read_limit: numOrNull(form, 'read_limit'),
      write_limit: numOrNull(form, 'write_limit'),
      delete_limit: numOrNull(form, 'delete_limit'),
      read_transfer_limit_bytes: read_mb !== null ? Math.round(read_mb * 1_048_576) : null,
      write_transfer_limit_bytes: write_mb !== null ? Math.round(write_mb * 1_048_576) : null,
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
        const data = (await resp.json().catch(() => ({}))) as Record<string, unknown>;
        const msg = data['detail'] ?? data['name'] ?? `Error ${resp.status}`;
        setFlash(String(msg), 'error');
        submitBtn.disabled = false;
        return;
      }

      setFlash('Plan created.', 'info');
      window.location.href = '/subscription/plans/';
    } catch (err) {
      setFlash(`Network error: ${String(err)}`, 'error');
      submitBtn.disabled = false;
    }
  });
});
