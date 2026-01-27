/**
 * Typed querySelector helper.
 */
export function qs<T extends Element>(
  selector: string,
  root: ParentNode = document
): T | null {
  return root.querySelector(selector) as T | null;
}

/**
 * Set a flash/status message in #flash.
 */
export function setFlash(
  message: string,
  kind: "info" | "error" = "info"
): void {
  const el = qs<HTMLDivElement>("#flash");
  if (!el) return;

  el.textContent = message;
  el.setAttribute("data-kind", kind);

  // Keep styling minimal and predictable
  el.style.marginTop = "16px";
  el.style.padding = "12px 16px";
  el.style.border = "1px solid var(--border)";
  el.style.borderRadius = "var(--r-6)";
  el.style.background = "var(--bg)";
  el.style.color = "var(--text)";
}