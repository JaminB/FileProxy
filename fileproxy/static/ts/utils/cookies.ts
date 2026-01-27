/**
 * Read a cookie value by name.
 * Safe for Django CSRF and general use.
 */
export function getCookie(name: string): string | null {
  if (!document.cookie) return null;

  const cookies = document.cookie.split("; ");
  for (const cookie of cookies) {
    const [key, ...rest] = cookie.split("=");
    if (key === name) {
      return decodeURIComponent(rest.join("="));
    }
  }
  return null;
}

/**
 * Convenience helper for Django CSRF.
 */
export function getCsrfToken(): string | null {
  return getCookie("csrftoken");
}