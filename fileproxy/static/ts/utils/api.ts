import { getCookie } from './cookies.js';

export type ApiErrorShape = { detail?: string } | unknown;

export async function apiMultipart<T>(
  url: string,
  formData: FormData,
  opts?: { method?: string },
): Promise<T> {
  const method = (opts?.method ?? 'POST').toUpperCase();
  const headers: Record<string, string> = {};
  const csrf = getCookie('csrftoken');
  if (csrf) headers['X-CSRFToken'] = csrf;

  const resp = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers,
    body: formData,
  });

  const isJson = (resp.headers.get('content-type') ?? '').includes('application/json');
  const data: unknown = isJson ? await resp.json() : await resp.text();

  if (!resp.ok) {
    const detail =
      typeof data === 'object' && data && 'detail' in data
        ? String((data as { detail?: unknown }).detail ?? '')
        : `Request failed (${resp.status})`;
    throw new Error(detail || `Request failed (${resp.status})`);
  }
  return data as T;
}

export async function apiJson<T>(
  url: string,
  opts?: { method?: string; body?: unknown },
): Promise<T> {
  const method = (opts?.method ?? 'GET').toUpperCase();
  const headers: Record<string, string> = {};

  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = getCookie('csrftoken');
    if (csrf) headers['X-CSRFToken'] = csrf;
    headers['Content-Type'] = 'application/json';
  }

  const resp = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers,
    body: opts?.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  const isJson = (resp.headers.get('content-type') ?? '').includes('application/json');
  const data: unknown = isJson ? await resp.json() : await resp.text();

  if (!resp.ok) {
    const detail =
      typeof data === 'object' && data && 'detail' in data
        ? String((data as { detail?: unknown }).detail ?? '')
        : `Request failed (${resp.status})`;
    throw new Error(detail || `Request failed (${resp.status})`);
  }

  return data as T;
}
