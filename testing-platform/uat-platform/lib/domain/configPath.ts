// Immutable get and set on a config by dotted path, such as "scope.projectIds"
// or "thresholds.0.percent". Setting undefined removes an optional key.

type Node = Record<string, unknown> | unknown[];

export function getPath(root: unknown, path: string): unknown {
  return path
    .split(".")
    .reduce<unknown>(
      (node, key) => (node == null ? undefined : (node as Record<string, unknown>)[key]),
      root,
    );
}

export function setPath<T>(root: T, path: string, value: unknown): T {
  const [key, ...rest] = path.split(".");
  const node = (root ?? {}) as Node;
  const copy = (Array.isArray(node) ? [...node] : { ...node }) as Record<string, unknown>;
  const next = rest.length === 0 ? value : setPath(copy[key], rest.join("."), value);
  if (next === undefined && !Array.isArray(node)) delete copy[key];
  else copy[key] = next;
  return copy as T;
}

// Deep equality for JSON-like values. NaN equals NaN, so retyping one invalid
// number over another is not a change.
export function sameValue(a: unknown, b: unknown): boolean {
  if (Object.is(a, b)) return true;
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const left = a as Record<string, unknown>;
  const right = b as Record<string, unknown>;
  const keys = Object.keys(left);
  return (
    keys.length === Object.keys(right).length &&
    keys.every((key) => sameValue(left[key], right[key]))
  );
}
