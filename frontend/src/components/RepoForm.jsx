import { useState } from "react";
import { Play } from "lucide-react";

const DEFAULT_TASK = "Find bugs in this repository, fix the most critical issue, and create tests to verify the fix.";

export default function RepoForm({ onSubmit, busy, error }) {
  const [url, setUrl] = useState("");
  const [task, setTask] = useState(DEFAULT_TASK);

  return (
    <div className="panel form">
      <label htmlFor="repo">Public GitHub repository</label>
      <input id="repo" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/owner/repository" autoComplete="off" />
      <label htmlFor="task">What should DevPilot do?</label>
      <textarea id="task" rows={3} value={task} onChange={(e) => setTask(e.target.value)} maxLength={1000} />
      {error && <p className="error" role="alert">{error}</p>}
      <div className="form-actions">
        <button className="primary" disabled={busy || !url.trim()} onClick={() => onSubmit(url.trim(), task.trim() || DEFAULT_TASK)}>
          <Play size={16} /> {busy ? "Starting…" : "Analyze repository"}
        </button>
        <span className="hint">Python files only. The repository is read, never run, outside the sandbox.</span>
      </div>
    </div>
  );
}
