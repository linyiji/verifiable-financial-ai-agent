// Offline test harness: production uses Vite's resolver, including extensionless
// TypeScript imports. Native Node strip-only mode does not implement that contract.
import { readFile } from "node:fs/promises";
import { stripTypeScriptTypes } from "node:module";

export async function resolve(specifier, context, nextResolve) {
  try {
    return await nextResolve(specifier, context);
  } catch (error) {
    if (!specifier.startsWith(".")) throw error;
    for (const extension of [".ts", ".tsx", "/index.ts"]) {
      try { return await nextResolve(specifier + extension, context); } catch { /* next candidate */ }
    }
    throw error;
  }
}

export async function load(url, context, nextLoad) {
  if (!/\.tsx?$/.test(url)) return nextLoad(url, context);
  const source = await readFile(new URL(url), "utf8");
  return {
    format: "module", shortCircuit: true,
    source: stripTypeScriptTypes(source, { mode: "transform", sourceUrl: url }),
  };
}
