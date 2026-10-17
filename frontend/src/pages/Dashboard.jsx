import { useCallback, useEffect, useState } from "react";
import RepoForm from "../components/RepoForm.jsx";
import TaskList from "../components/TaskList.jsx";
import { api } from "../services/api.js";

export default function Dashboard() {
  const [tasks, setTasks] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(() => api.listTasks().then(setTasks).catch(() => {}), []);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 4000);
    return () => clearInterval(timer);
  }, [refresh]);

  async function start(url, task) {
    setBusy(true);
    setError("");
    try {
      const { task_id } = await api.startAnalysis(url, task);
      window.location.hash = `#/task/${task_id}`;
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="hero">
        <h1>Review a repository</h1>
        <p className="hero-kicker">DevPilot</p>
        <hr className="hero-rule" />
        <p className="lede">
          DevPilot finds candidate bugs, proposes one patch, and writes a test. Nothing is applied or tested in a sandbox until you approve.
        </p>
      </header>

      <RepoForm onSubmit={start} busy={busy} error={error} />

      <h2>Previous analyses</h2>
      <TaskList tasks={tasks} />
    </>
  );
}
