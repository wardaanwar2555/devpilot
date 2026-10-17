import { useEffect, useState } from "react";
import Dashboard from "./pages/Dashboard.jsx";
import TaskPage from "./pages/TaskPage.jsx";
import { api } from "./services/api.js";

function useHashRoute() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const match = hash.match(/^#\/task\/([\w-]+)/);
  return match ? { page: "task", id: match[1] } : { page: "home" };
}

export default function App() {
  const route = useHashRoute();
  const [health, setHealth] = useState(null);
  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: "down" }));
  }, []);

  return (
    <>
      <header className="topbar">
        <a href="#/" className="brand">DevPilot</a>
        <span className="topbar-note">Proposes fixes. Shows what was actually tested.</span>
        <div className="env">
          <span className={`pill ${health?.status === "ok" ? "ok" : "bad"}`}>API {health?.status === "ok" ? "online" : "offline"}</span>
          <span className={`pill ${health?.llm_configured ? "ok" : "muted"}`}>{health?.llm_configured ? "Model on" : "No model"}</span>
          <span className={`pill ${health?.sandbox_ready ? "ok" : "warn"}`} title={health?.sandbox_note || ""}>
            {health?.sandbox_ready ? "Sandbox ready" : "Sandbox missing"}
          </span>
        </div>
      </header>
      <main className="page">{route.page === "task" ? <TaskPage id={route.id} /> : <Dashboard />}</main>
    </>
  );
}
