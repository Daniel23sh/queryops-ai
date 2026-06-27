import { useEffect, useState } from "react";

type HealthState =
  | { status: "loading"; message: "Checking backend..." }
  | { status: "success"; message: string }
  | { status: "error"; message: "Backend is not reachable yet." };

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export default function App() {
  const [health, setHealth] = useState<HealthState>({
    status: "loading",
    message: "Checking backend..."
  });

  useEffect(() => {
    let isMounted = true;

    fetch(`${API_BASE_URL}/health`)
      .then((response) => {
        if (!response.ok) {
          throw new Error("Health check failed");
        }

        return response.json() as Promise<{ status?: string; service?: string }>;
      })
      .then((data) => {
        if (!isMounted) {
          return;
        }

        setHealth({
          status: "success",
          message: `${data.service ?? "Backend"} is ${data.status ?? "available"}`
        });
      })
      .catch(() => {
        if (!isMounted) {
          return;
        }

        setHealth({
          status: "error",
          message: "Backend is not reachable yet."
        });
      });

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__inner">
          <div className="brand" aria-label="QueryOps AI">
            <span className="brand__name">QueryOps AI</span>
            <span className="brand__phase">Milestone 0 foundation</span>
          </div>
        </div>
      </header>

      <main className="app-main">
        <section className="hero" aria-labelledby="project-title">
          <p className="eyebrow">Project setup</p>
          <h1 id="project-title">QueryOps AI</h1>
          <p className="subtitle">
            A governed conversational data workspace for safe SQL-backed insights,
            dashboards, controlled actions, approvals, and audit trails.
          </p>

          <div className="status-panel" aria-live="polite">
            <p className="status-panel__label">Backend status</p>
            <p className="status-panel__value" data-state={health.status}>
              {health.message}
            </p>
          </div>
        </section>
      </main>
    </div>
  );
}
