/**
 * Create an SVG icon referencing the global sprite (<symbol>).
 *
 * Usage:
 *   el.appendChild(spriteIcon("i-eye"))
 */
export function spriteIcon(id: string): SVGSVGElement {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");

  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#${id}`);

  svg.appendChild(use);
  return svg;
}