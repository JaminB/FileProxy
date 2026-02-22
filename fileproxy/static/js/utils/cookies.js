/**
 * Read a cookie value by name.
 * Safe for Django CSRF and general use.
 */
export function getCookie(name) {
    if (!document.cookie)
        return null;
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
export function getCsrfToken() {
    return getCookie("csrftoken");
}
//# sourceMappingURL=cookies.js.map