import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
import AgentActivity from "../components/AgentActivity.jsx";
import FindingsPanel from "../components/FindingsPanel.jsx";
import PatchReview from "../components/PatchReview.jsx";
import ReportView from "../components/ReportView.jsx";
import VerificationPanel from "../components/VerificationPanel.jsx";
import { api } from "../services/api.js";

const LIVE = new Set(["queued", "running", "testing"]);
const TABS = [["findings", "Findings"], ["patch", "Patch review"], ["verification", "Verification"], ["report", "Report"]];

export default function TaskPage({ id }) {
  const [task, setTask] = useState(null);
  const [findings, setFindings] = useState([]);
  const [patch, setPatch] = useState(null);
  const [report, setReport] = useState(null);
  const [tab, setTab] = useState("findings");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const autoTab = useRef(null);

  const load = useCallback(async () => {
    try {
      const t = await api.getTask(id);
      setTask(t);
      if (!LIVE.has(t.status)) {
        setFindings(await api.getFindings(id));
        setPatch(t.has_patch ? await api.getPatch(id) : null);
        setReport(await api.getReport(id).catch(() => null));
        if (autoTab.current !== t.status) {
          autoTab.current = t.status;
          setTab(t.status === "awaiting_approval" ? "patch" : t.status === "completed" ? "report" : "findings");
        }
      }
      return t;
    } catch (e) {
      setError(e.message);
      return null;
    }
  }, [id]);

  useEffect(() => {
    let stop = false;
    (async function poll() {
      const t = await load();
      if (!stop && (!t || LIVE.has(t.status))) setTimeout(poll, 1500);
    })();
    return () => { stop = true; };
  }, [load]);

  async function decide(approved, note) {
    setBusy(true);
    try {
      await api.decide(id, approved, note);
      await load();
      (async function poll() {
        const t = await load();
        if (t && LIVE.has(t.status)) setTimeout(poll, 1500);
      })();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (error && !task) return <><a href="#/" className="back"><ArrowLeft size={14} /> All analyses</a><p className="error">{error}</p></>;
  if (!task) return <p className="empty">Loading…</p>;
  const name = task.repository_url.replace("https://github.com/", "");

  return (
    <>
      <a href="#/" className="back"><ArrowLeft size={14} /> All analyses</a>
      <h1 className="task-title">{name}</h1>
      <hr className="task-rule" />
      <p className="lede">{task.task}</p>
      {task.repo_meta && (
        <p className="meta">
          {task.repo_meta.branch} @ <code>{task.repo_meta.commit?.slice(0, 10)}</code> · {task.repo_meta.files_analyzed} files analyzed
          {task.repo_meta.files_skipped > 0 && `, ${task.repo_meta.files_skipped} skipped`}
          {task.repo_meta.tree_truncated && " · GitHub truncated the file tree"}
          {task.secrets_flagged > 0 && ` · ${task.secrets_flagged} possible secret(s) redacted before any model call`}
        </p>
      )}
      {task.error && <p className="error" role="alert">{task.error}</p>}

      <section className="panel">
        <h2>Agent activity</h2>
        <AgentActivity events={task.events} />
      </section>

      {!LIVE.has(task.status) && (
        <section className="panel">
          <div className="tabs" role="tablist">
            {TABS.map(([k, label]) => (
              <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "tab on" : "tab"} onClick={() => setTab(k)}>{label}</button>
            ))}
          </div>
          {tab === "findings" && <FindingsPanel findings={findings} />}
          {tab === "patch" && (patch ? <PatchReview data={patch} status={task.status} onDecide={decide} busy={busy} /> :
            <p className="empty">No patch was proposed. {task.plan?.length ? "The validator rejected every attempt or no safe fix was found." : "There was no actionable finding to fix."}</p>)}
          {tab === "verification" && <VerificationPanel results={patch?.test_results} review={patch?.review} />}
          {tab === "report" && (report ? <ReportView report={report} name={name} /> :
            <p className="empty">The report is written after you approve or reject the patch.</p>)}
        </section>
      )}
    </>
  );
}
