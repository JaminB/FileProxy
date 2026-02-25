"use strict";
const STORAGE_KEY = 'fp-theme';
function applyTheme(theme) {
    document.documentElement.setAttribute('data-bs-theme', theme === 'dark' ? 'dark' : 'light');
}
function saveTheme(theme) {
    localStorage.setItem(STORAGE_KEY, theme);
}
function loadTheme() {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'dark')
        return stored;
    return 'light';
}
function updateButtons(theme) {
    document.querySelectorAll('[data-fp-theme]').forEach((btn) => {
        const active = btn.dataset.fpTheme === theme;
        btn.classList.toggle('active', active);
        btn.classList.toggle('btn-secondary', active);
        btn.classList.toggle('btn-outline-secondary', !active);
    });
}
document.addEventListener('DOMContentLoaded', () => {
    const theme = loadTheme();
    updateButtons(theme);
    document.querySelectorAll('[data-fp-theme]').forEach((btn) => {
        btn.addEventListener('click', () => {
            const t = btn.dataset.fpTheme;
            saveTheme(t);
            applyTheme(t);
            updateButtons(t);
        });
    });
});
//# sourceMappingURL=theme.js.map