import { ThemeToggle } from "../components/ui/ThemeToggle";
import { useTheme } from "./useTheme";

export function AppHeader() {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="app-header">
      <div className="app-header__inner">
        <div className="brand" aria-label="QueryOps AI">
          <span className="brand__mark" aria-hidden="true">
            Q
          </span>
          <span className="brand__copy">
            <span className="brand__name">QueryOps AI</span>
            <span className="brand__phase">Governed data workspace</span>
          </span>
        </div>
        <div className="app-header__actions" aria-label="Application controls">
          <span className="app-status-pill">Demo environment</span>
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
        </div>
      </div>
    </header>
  );
}
