import { initProviderForm } from "./core.js";
import { qs, setFlash } from "../../utils/dom.js";
function getField(form, name) {
    const el = qs(`[name="${name}"]`, form);
    if (!el)
        return null;
    if (el instanceof HTMLInputElement ||
        el instanceof HTMLTextAreaElement ||
        el instanceof HTMLSelectElement) {
        return el;
    }
    return null;
}
function val(form, name) {
    const el = getField(form, name);
    return (el?.value ?? "").trim();
}
function requireField(form, name, label) {
    const v = val(form, name);
    if (!v) {
        setFlash(`${label} is required.`, "error");
        throw new Error("validation");
    }
    return v;
}
document.addEventListener("DOMContentLoaded", () => {
    initProviderForm({
        formSelector: "#credential-form",
        endpoint: "/api/v1/vault-items/azure/",
        successMessage: "Azure credentials saved.",
        successRedirect: "/vault/",
        buildPayload: (form) => ({
            name: requireField(form, "name", "Name"),
            account_name: requireField(form, "account_name", "Storage account name"),
            container_name: requireField(form, "container_name", "Container name"),
            tenant_id: requireField(form, "tenant_id", "Tenant ID"),
            client_id: requireField(form, "client_id", "Client ID"),
            client_secret: requireField(form, "client_secret", "Client secret"),
        }),
    });
});
//# sourceMappingURL=azure.js.map