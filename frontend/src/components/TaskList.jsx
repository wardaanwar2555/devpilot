const STATUS = {
  queued: "Queued", running: "Running", awaiting_approval: "Needs your review",
  testing: "Testing", completed: "Done", failed: "Failed",
};
const VERDICT = { verified: "Verified", weak: "Weak evidence", failed: "Tests failed", inconclusive: "Inconclusive", not_run: "Not verified", no_patch: "No patch" };

export default function TaskList({ tasks }) {
  if (!tasks.length) return <p className="empty">No analyses yet. Paste a repository URL above to start one.</p>;
  return (
    <ul className="tasklist">
      {tasks.map((t) => (
        <li key={t.id}>
          <a href={`#/task/${t.id}`}>
            <span className="repo">{t.repository_url.replace("https://github.com/", "")}</span>
            <span className={`status s-${t.status}`}>{STATUS[t.status] || t.status}</span>
            <span className="meta">{t.finding_count} findings</span>
            {t.verdict && <span className={`verdict v-${t.verdict}`}>{VERDICT[t.verdict]}</span>}
            <span className="meta when">{new Date(t.created_at).toLocaleString()}</span>
          </a>
        </li>
      ))}
    </ul>
  );
}
