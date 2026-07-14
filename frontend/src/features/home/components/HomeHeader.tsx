import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

import { APP_ROUTES } from "../../../app/routeConfig";
import type { AuthUser } from "../../../auth/types";
import { formatRole } from "../../../lib/format";
import type { HomeScope } from "../types";

export function HomeHeader({
  canUseAskData,
  scope,
  user
}: {
  canUseAskData: boolean;
  scope: HomeScope | null;
  user: AuthUser;
}) {
  const fallbackScope =
    user.scopes.find((item) => item.isDefault)?.displayName ??
    user.scopes[0]?.displayName ??
    "Personal";
  const scopeName = scope?.display_name ?? fallbackScope;

  return (
    <header className="home-header">
      <div>
        <p className="eyebrow">Workspace</p>
        <h1 id="home-title">My Dashboard</h1>
        <p className="home-header__context">
          {formatRole(user.role)} <span aria-hidden="true">·</span> Scope: {scopeName}
        </p>
        <p className="home-header__subtitle">
          Your governed operational workspace and saved dashboards.
        </p>
      </div>
      {canUseAskData ? (
        <Link
          aria-label="Open Ask Data"
          className="home-header__ask qops-focus-ring"
          to={APP_ROUTES.ask}
        >
          Ask Data
          <ArrowRight aria-hidden="true" size={18} />
        </Link>
      ) : null}
    </header>
  );
}
