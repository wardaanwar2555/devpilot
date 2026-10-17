// Provenance tag: every claim in the UI says where it came from.
const LABELS = {
  static: "Static analysis",
  deterministic: "Static analysis",
  llm: "Model",
  rule: "Rule-based",
  sandbox: "Sandbox run",
};

export default function Tag({ kind }) {
  const key = LABELS[kind] ? kind : "static";
  return <span className={`tag tag-${key === "deterministic" ? "static" : key}`}>{LABELS[key]}</span>;
}
