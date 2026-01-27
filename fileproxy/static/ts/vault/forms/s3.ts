import { initProviderForm } from "./core.js";
import { qs, setFlash } from "../../utils/dom.js";

function val(form: HTMLFormElement, name: string): string {
  const el = qs<HTMLInputElement | HTMLSelectElement>(`[name="${name}"]`, form);
  return (el?.value ?? "").trim();
}

function requireField(form: HTMLFormElement, name: string, label: string): string {
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
    endpoint: "/api/v1/vault-items/s3/",
    successMessage: "S3 credentials saved.",
    successRedirect: "/vault/",
    buildPayload: (form) => ({
      provider: "s3",
      name: requireField(form, "name", "Name"),
      access_key_id: requireField(form, "access_key_id", "Access key id"),
      secret_access_key: requireField(form, "secret_access_key", "Secret access key"),
      region: val(form, "region") || null,
    }),
  });
});