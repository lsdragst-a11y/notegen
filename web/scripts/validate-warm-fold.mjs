import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const css = fs.readFileSync(path.join(root, "app", "globals.css"), "utf8");
const assets = [
  ["brand-mark.svg", 4096, 8],
  ["brand-logo.svg", 18432, 80],
  ["favicon.svg", 4096, 8],
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function selectorBlock(selector) {
  const start = css.indexOf(selector);
  assert(start >= 0, `Missing selector ${selector}`);
  const open = css.indexOf("{", start);
  let depth = 0;

  for (let index = open; index < css.length; index += 1) {
    if (css[index] === "{") depth += 1;
    if (css[index] === "}" && --depth === 0) return css.slice(start, index + 1);
  }

  throw new Error(`Unclosed selector ${selector}`);
}

for (const [name, maxBytes, maxPaths] of assets) {
  const file = path.join(root, "public", "brand", name);
  const source = fs.readFileSync(file, "utf8");
  const document = new JSDOM(source, { contentType: "image/svg+xml" }).window.document;

  assert(document.documentElement.tagName.toLowerCase() === "svg", `${name} is not SVG`);
  assert(document.documentElement.hasAttribute("viewBox"), `${name} lacks viewBox`);
  assert(!source.includes("<image"), `${name} embeds raster content`);
  assert(!source.includes("<metadata"), `${name} contains metadata`);
  assert(!source.includes('display="none"'), `${name} contains hidden layers`);
  assert(Buffer.byteLength(source) <= maxBytes, `${name} exceeds ${maxBytes} bytes`);
  assert((source.match(/<path\b/g) || []).length <= maxPaths, `${name} has too many paths`);
  assert(!/\d+\.\d{4,}/.test(source), `${name} exceeds three decimal places`);
}

const logo = fs.readFileSync(path.join(root, "public", "brand", "brand-logo.svg"), "utf8");
assert(logo.includes('data-min-width="120"'), "brand-logo.svg lacks minimum width metadata");

const legacy = [".apple-card {", ".apple-button {", ".tag-chip {"].map(selectorBlock).join("\n");
assert(!legacy.includes("--wf-"), "Legacy classes reference Warm Fold tokens");
assert(css.includes("--wf-accent: #A34A2F"), "Accessible light accent is missing");
assert(css.includes("--wf-brand-coral: #B65C3A"), "Brand coral is missing");

console.log(`Warm Fold validation passed (${createHash("sha256").update(legacy).digest("hex").slice(0, 12)})`);
