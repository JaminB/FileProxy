/**
 * Create an SVG icon referencing the global sprite (<symbol>).
 *
 * Icons are sized using em units so Bootstrap font-size utilities (fs-*)
 * control their rendered size.
 *
 * Usage:
 *   el.appendChild(spriteIcon("i-eye"))
 *   el.appendChild(spriteIcon("i-vault", "fs-5"))
 */
export function spriteIcon(id, extraClass) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    let classes = "icon align-text-bottom";
    if (extraClass) {
        classes += ` ${extraClass}`;
    }
    svg.setAttribute("class", classes);
    svg.setAttribute("aria-hidden", "true");
    svg.style.width = "1em";
    svg.style.height = "1em";
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `#${id}`);
    svg.appendChild(use);
    return svg;
}
//# sourceMappingURL=icons.js.map