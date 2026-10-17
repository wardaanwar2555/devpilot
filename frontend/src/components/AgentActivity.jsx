import { Check, Circle, Loader2, Pause, X } from "lucide-react";
import Tag from "./Tag.jsx";

const STEPS = [
  ["analyze_repository", "Read repository and run analyzers"],
  ["detect_issues", "Rank findings"],
  ["create_plan", "Plan the repair"],
  ["propose_patch", "Propose a patch"],
  ["validate_patch", "Validate the patch"],
  ["generate_tests", "Write a test"],
  ["await_approval", "Your approval"],
  ["run_tests", "Run tests in sandbox"],
  ["review", "Weigh the evidence"],
  ["report", "Write the report"],
];

function icon(status) {
  if (status === "done") return <Check size={14} />;
  if (status === "running") return <Loader2 size={14} className="spin" />;
  if (status === "failed") return <X size={14} />;
  if (status === "waiting") return <Pause size={14} />;
  return <Circle size={10} />;
}

export default function AgentActivity({ events }) {
  const latest = {};
  const attempts = {};
  for (const e of events) {
    latest[e.step] = e;
    if (e.status === "running") attempts[e.step] = (attempts[e.step] || 0) + 1;
  }
  return (
    <ol className="steps" aria-label="Agent activity">
      {STEPS.map(([key, label]) => {
        const e = latest[key];
        const status = e?.status || "idle";
        return (
          <li key={key} className={`step st-${status}`}>
            <span className="dot">{icon(status)}</span>
            <div>
              <div className="step-title">
                {label}
                {attempts[key] > 1 && <span className="retries">attempt {attempts[key]}</span>}
                {e && status !== "waiting" && <Tag kind={key === "run_tests" ? "sandbox" : e.kind} />}
              </div>
              {e && <div className="step-msg">{e.message}</div>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
