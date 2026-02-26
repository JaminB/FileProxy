import { initProviderForm } from './core.js';
document.addEventListener('DOMContentLoaded', () => {
    initProviderForm({
        formSelector: '#credential-form',
        endpoint: '/api/v1/connections/dropbox/',
        buildPayload: (form) => ({
            name: form.querySelector('[name="name"]').value.trim(),
        }),
        onSuccess: (data) => {
            const url = data.auth_url;
            window.location.href = url;
        },
    });
});
//# sourceMappingURL=dropbox.js.map