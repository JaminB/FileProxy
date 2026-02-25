const STORAGE_KEY = 'fp-theme';
type Theme = 'light' | 'dark';

function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-bs-theme', theme === 'dark' ? 'dark' : 'light');
}

function saveTheme(theme: Theme): void {
  localStorage.setItem(STORAGE_KEY, theme);
}

function loadTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'dark') return stored;
  return 'light';
}

function updateButtons(theme: Theme): void {
  document.querySelectorAll<HTMLButtonElement>('[data-fp-theme]').forEach((btn) => {
    const active = btn.dataset.fpTheme === theme;
    btn.classList.toggle('active', active);
    btn.classList.toggle('btn-secondary', active);
    btn.classList.toggle('btn-outline-secondary', !active);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const theme = loadTheme();
  updateButtons(theme);
  document.querySelectorAll<HTMLButtonElement>('[data-fp-theme]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const t = btn.dataset.fpTheme as Theme;
      saveTheme(t);
      applyTheme(t);
      updateButtons(t);
    });
  });
});
