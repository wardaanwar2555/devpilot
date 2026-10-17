import Tag from "./Tag.jsx";

function Run({ title, run }) {
  if (!run) return null;
  return (
    <div className={`run run-${run.status}`}>
      <div className="run-head"><strong>{title}</strong><span className="run-status">{run.status}</span></div>
      <div className="meta">exit {run.exit_code ?? "n/a"} · {run.duration_s}s · {run.passed} passed · {run.failed} failed</div>
      {run.note && <p className="note">{run.note}</p>}
      {(run.stdout || run.stderr) && <pre className="code">{(run.stdout + "\n" + run.stderr).trim().slice(-3000)}</pre>}
    </div>
  );
}

export default function VerificationPanel({ results, review }) {
  if (!results) return <p className="empty">No tests have run. They start only after you approve the patch.</p>;
  return (
    <>
      <p className="provenance"><Tag kind="sandbox" /> Results below come from actually running the test in the sandbox.</p>
      <div className="runs">
        <Run title="Original code" run={results.baseline} />
        <Run title="Patched code" run={results.patched} />
      </div>
      <p className="note">A fix counts as verified only if the test fails on the original and passes on the patched code.</p>
      {review?.notes?.length > 0 && (
        <>
          <h3>Possible regression risks <Tag kind="llm" /></h3>
          <ul>{review.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
          <p className="note">Model opinions, not test results.</p>
        </>
      )}
    </>
  );
}
