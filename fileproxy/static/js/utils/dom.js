/**
 * Typed querySelector helper.
 */
export function qs(selector, root = document) {
    return root.querySelector(selector);
}
/**
 * Set a flash/status message in #flash.
 */
export function setFlash(message, kind = 'info') {
    const el = qs('#flash');
    if (!el)
        return;
    el.textContent = message;
    el.setAttribute('data-kind', kind);
    el.style.marginTop = '16px';
    el.style.padding = '12px 16px';
    el.style.borderRadius = 'var(--r-6)';
    // Default (info)
    let border = 'var(--border)';
    let bg = 'var(--bg)';
    let color = 'var(--text)';
    if (kind === 'success') {
        border = 'var(--success-border, #2e7d32)';
        bg = 'var(--success-bg, #e6f4ea)';
        color = 'var(--success-text, #1b5e20)';
    }
    else if (kind === 'error') {
        border = 'var(--danger-border, #b42318)';
        bg = 'var(--danger-bg, #fdecea)';
        color = 'var(--danger-text, #7a1212)';
    }
    el.style.border = `1px solid ${border}`;
    el.style.background = bg;
    el.style.color = color;
}
//# sourceMappingURL=dom.js.map