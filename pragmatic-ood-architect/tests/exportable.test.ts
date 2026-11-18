import { isExportable, readCsv } from "../examples/code/exportable";

for (const value of [null, 1, {}, { kind: "exportable" }, { kind: "exportable", toCsv: 7 },
  { kind: "unknown", toCsv: () => "x" }]) {
  if (isExportable(value)) throw new Error("guard accepted missing capability");
}
if (readCsv({ kind: "exportable", toCsv: () => "a,b" }) !== "a,b") throw new Error("wrong CSV");
let rejected = false;
try { readCsv({ kind: "exportable", toCsv: () => 42 }); }
catch (e) { if (!(e instanceof TypeError)) throw e; rejected = true; }
if (!rejected) throw new Error("unverified result accepted");
