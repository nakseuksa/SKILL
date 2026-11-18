// A caller can check that a method exists without trusting its result type.
export interface Exportable {
  readonly kind: "exportable";
  toCsv(): unknown;
}

export function isExportable(value: unknown): value is Exportable {
  if (typeof value !== "object" || value === null) return false;
  return "kind" in value && value.kind === "exportable" &&
    "toCsv" in value && typeof value.toCsv === "function";
}

export function readCsv(value: unknown): string {
  if (!isExportable(value)) throw new TypeError("Expected CSV exporter");
  const result = value.toCsv();
  if (typeof result !== "string") throw new TypeError("Expected CSV string");
  return result;
}
