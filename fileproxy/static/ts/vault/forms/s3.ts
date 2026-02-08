import { initProviderForm } from "./core.js";
import { qs, setFlash } from "../../utils/dom.js";

type FormFieldEl = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;

function getField(form: HTMLFormElement, name: string): FormFieldEl | null {
  const el = qs(`[name="${name}"]`, form);
  if (!el) return null;

  if (
    el instanceof HTMLInputElement ||
    el instanceof HTMLTextAreaElement ||
    el instanceof HTMLSelectElement
  ) {
    return el;
  }

  return null;
}

function val(form: HTMLFormElement, name: string): string {
  const el = getField(form, name);
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
    buildPayload: (form: HTMLFormElement) => ({
      provider: "s3",
      name: requireField(form, "name", "Name"),
      bucket: requireField(form, "bucket", "Bucket name"),
      access_key_id: requireField(form, "access_key_id", "Access key id"),
      secret_access_key: requireField(form, "secret_access_key", "Secret access key"),
      session_token: val(form, "session_token") || null,
    }),
  });
});
