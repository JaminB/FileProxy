import { initProviderForm } from './core.js';

document.addEventListener('DOMContentLoaded', () => {
  initProviderForm({
    formSelector: '#credential-form',
    endpoint: '/api/v1/connections/gdrive/',
    buildPayload: (form) => ({
      name: form.querySelector<HTMLInputElement>('[name="name"]')!.value.trim(),
    }),
    onSuccess: (data) => {
      const url = (data as { auth_url: string }).auth_url;
      window.location.href = url;
    },
  });
});
