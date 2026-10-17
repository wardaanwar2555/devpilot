import { useMemo, useState } from "react";
import Tag from "./Tag.jsx";

const LEVELS = ["all", "critical", "high", "medium", "low", "info"];
const VERDICT = { likely_bug: "Model: likely a bug", possible_false_positive: "Model: possible false positive", style_only: "Model: style only" };

export default function FindingsPanel({ findings }) {
  const [level, setLevel] = useState("all");
  const [open, setOpen] = useState(null);
  const counts = useMemo(() => {
    const c = { all: findings.length };
    findings.forEach((f) => (c[f.severity] = (c[f.severity] || 0) + 1));
    return c;
  }, [findings]);
  const shown = findings.filter((f) => level === "all" || f.severity === level);

  if (!findings.length) return <p className="empty">The analyzers found nothing to report in the files they could read. That is not proof the code is bug-free.</p>;
  return (
    <>
      <p className="note">Only syntax errors are confirmed. Everything else is a <strong>candidate</strong>: read the code before acting on it.</p>
      <div className="filters" role="group" aria-label="Filter by severity">
        {LEVELS.filter((l) => counts[l]).map((l) => (
          <button key={l} className={level === l ? "chip on" : "chip"} onClick={() => setLevel(l)}>{l} <span>{counts[l]}</span></button>
        ))}
      </div>
      <ul className="findings">
        {shown.map((f) => (
          <li key={f.id} className={`finding sev-${f.severity}`}>
            <button className="finding-head" onClick={() => setOpen(open === f.id ? null : f.id)} aria-expanded={open === f.id}>
              <span className={`sev sev-${f.severity}`}>{f.severity}</span>
              <span className="finding-title">{f.title}</span>
              <code className="loc">{f.path}:{f.line}</code>
            </button>
            {open === f.id && (
              <div className="finding-body">
                {f.evidence && <pre className="evidence">{f.evidence}</pre>}
                <p>{f.details}</p>
                {f.next_step && <p><strong>Next step:</strong> {f.next_step}</p>}
                <p className="provenance">
                  <Tag kind={f.source === "ast" ? "static" : "static"} /> {f.source} · {f.rule_id}
                  {f.confirmed && <span className="confirmed">confirmed</span>}
                  {f.ml_severity && <span className="mlsev">ML severity: {f.ml_severity}</span>}
                </p>
                {f.llm_verdict && (
                  <p className="provenance"><Tag kind="llm" /> {VERDICT[f.llm_verdict]}{f.llm_explanation ? `: ${f.llm_explanation}` : ""}</p>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
