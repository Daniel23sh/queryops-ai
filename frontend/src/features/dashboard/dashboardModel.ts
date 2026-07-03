import { hasPermission } from "../../auth/permissions";
import type { AuthUser } from "../../auth/types";
import { formatRole } from "../../lib/format";
import type { NavItem } from "../../app/navigation";

export type DashboardTone = "blue" | "green" | "warning" | "muted";

export type DashboardKpiCard = {
  label: string;
  value: string;
  detail: string;
  tone: DashboardTone;
};

export type DashboardAction = {
  label: string;
  description: string;
  navId: string | null;
  disabled: boolean;
  isPrimary: boolean;
};

export type DashboardStatusCard = {
  title: string;
  status: string;
  detail: string;
  tone: DashboardTone;
};

export type DashboardActivityRow = {
  title: string;
  meta: string;
  status: string;
};

export type DashboardRoleSummary = {
  title: string;
  description: string;
};

export type DashboardModel = {
  activityRows: DashboardActivityRow[];
  currentScopeLabel: string;
  departmentLabel: string;
  governanceCards: DashboardStatusCard[];
  kpiCards: DashboardKpiCard[];
  quickActions: DashboardAction[];
  roleLabel: string;
  roleSummary: DashboardRoleSummary;
};

export function buildDashboardModel(
  user: AuthUser,
  visibleNavItems: NavItem[]
): DashboardModel {
  const roleLabel = formatRole(user.role);
  const departmentLabel = user.department?.name ?? "No department assigned";
  const hasTemplateAccess = hasPermission(user, "can_use_query_templates");
  const hasFreeQueryAccess = hasPermission(user, "can_run_free_query");
  const hasTechnicalVisibility = hasPermission(user, "can_view_sql");
  const hasGlobalScope = hasPermission(user, "can_query_global_data");
  const queryAccessLabel = hasFreeQueryAccess
    ? "Free-query access"
    : "Template-only access";
  const sqlVisibilityLabel = hasTechnicalVisibility
    ? "SQL visible in Ask Data"
    : "SQL hidden";
  const diagnosticsVisibilityLabel = hasTechnicalVisibility
    ? "Diagnostics visible in Ask Data"
    : "Diagnostics hidden";
  const currentScopeLabel =
    user.role === "admin" && hasGlobalScope ? "Global scope" : departmentLabel;
  const technicalSummary = hasTechnicalVisibility
    ? "Technical tabs visible"
    : "Business view";
  const roleSummary = getDashboardRoleSummary(
    user.role,
    hasFreeQueryAccess,
    hasTechnicalVisibility
  );

  function canNavigateTo(navId: string): boolean {
    return visibleNavItems.some((item) => item.id === navId);
  }

  return {
    activityRows: [
      {
        title: "Demo workspace loaded",
        meta: `${roleLabel} profile / ${departmentLabel}`,
        status: "Preview"
      },
      {
        title: "Ask Data entry point",
        meta: hasTemplateAccess
          ? "Approved template access is visible in navigation."
          : "Ask Data is hidden for this role.",
        status: hasTemplateAccess ? "Ready" : "Hidden"
      },
      {
        title: "Technical controls",
        meta: hasTechnicalVisibility
          ? "Technical visibility is summarized here, with details kept in Ask Data."
          : "Technical views are not exposed to this role.",
        status: hasTechnicalVisibility ? "Role-gated" : "Restricted"
      }
    ],
    currentScopeLabel,
    departmentLabel,
    governanceCards: [
      {
        title: "Template governance",
        status: hasTemplateAccess ? "Approved catalog enabled" : "Catalog hidden",
        detail: hasTemplateAccess
          ? "Approved templates remain the safest entry point for repeat questions."
          : "This role does not have template catalog visibility.",
        tone: "blue"
      },
      {
        title: "Free-question access",
        status: hasFreeQueryAccess ? "Free questions enabled" : "Templates required",
        detail: hasFreeQueryAccess
          ? "Free questions still run through backend validation and authorization."
          : "Approved templates are the safe starting point for this role.",
        tone: hasFreeQueryAccess ? "green" : "muted"
      },
      {
        title: "SQL visibility",
        status: sqlVisibilityLabel,
        detail: hasTechnicalVisibility
          ? "SQL is available only inside the Ask Data technical tab."
          : "SQL tabs and SQL content remain hidden for this role.",
        tone: hasTechnicalVisibility ? "green" : "muted"
      },
      {
        title: "Diagnostics visibility",
        status: diagnosticsVisibilityLabel,
        detail: hasTechnicalVisibility
          ? "Safe technical diagnostics stay inside Ask Data."
          : "Technical diagnostics remain hidden for this role.",
        tone: hasTechnicalVisibility ? "green" : "muted"
      },
      {
        title: "Scope enforcement",
        status: "Backend enforced",
        detail: "Frontend status mirrors permissions; backend authorization remains the source of truth.",
        tone: "blue"
      }
    ],
    kpiCards: [
      {
        label: "Approved templates",
        value: hasTemplateAccess ? "Available" : "Hidden",
        detail: hasTemplateAccess
          ? "The template catalog is available from Ask Data."
          : "The template catalog is not visible for this role.",
        tone: "blue"
      },
      {
        label: "Query access mode",
        value: queryAccessLabel,
        detail: hasFreeQueryAccess
          ? "This role can ask permitted free-form questions."
          : "This role runs approved templates only.",
        tone: hasFreeQueryAccess ? "green" : "blue"
      },
      {
        label: "Technical visibility",
        value: technicalSummary,
        detail: hasTechnicalVisibility
          ? "Technical tabs stay contained in Ask Data."
          : "Technical views remain hidden for this role.",
        tone: hasTechnicalVisibility ? "green" : "muted"
      },
      {
        label: "Current scope",
        value: currentScopeLabel,
        detail: hasGlobalScope
          ? "Admin demo permissions include global query scope."
          : "Workspace context follows the signed-in department.",
        tone: hasGlobalScope ? "warning" : "blue"
      }
    ],
    quickActions: [
      {
        label: "Open Ask Data",
        description: "Start with approved templates or a permitted governed question.",
        navId: "ask-data",
        disabled: !canNavigateTo("ask-data"),
        isPrimary: true
      },
      {
        label: "Review query history",
        description: canNavigateTo("query-history")
          ? "Open the planned query history workspace."
          : "Available only to roles with query history visibility.",
        navId: "query-history",
        disabled: !canNavigateTo("query-history"),
        isPrimary: false
      },
      {
        label: "Request role upgrade",
        description: "Use the existing role request workflow when more access is needed.",
        navId: "role-upgrade",
        disabled: !canNavigateTo("role-upgrade"),
        isPrimary: false
      },
      {
        label: "Save dashboard card",
        description: "Future saved-card behavior is intentionally disabled in this PR.",
        navId: null,
        disabled: true,
        isPrimary: false
      }
    ],
    roleLabel,
    roleSummary
  };
}

function getDashboardRoleSummary(
  role: AuthUser["role"],
  hasFreeQueryAccess: boolean,
  hasTechnicalVisibility: boolean
): DashboardRoleSummary {
  if (role === "admin") {
    return {
      title: "Admin governance view",
      description:
        "Admins can move into Ask Data, review technical tabs there, and use the existing admin navigation without any dashboard-side execution controls."
    };
  }

  if (hasTechnicalVisibility) {
    return {
      title: "Analyst technical view",
      description:
        "Analysts can ask governed questions and review technical tabs inside Ask Data while this dashboard stays focused on safe status and navigation."
    };
  }

  if (hasFreeQueryAccess) {
    return {
      title: "Manager analytics view",
      description:
        "Managers can open Ask Data for approved templates or permitted free questions. SQL and diagnostics remain hidden from this dashboard and from manager views."
    };
  }

  return {
    title: "Template-only workspace",
    description:
      "Use approved templates as the safe starting point for this role. Free questions, SQL visibility, and diagnostics stay unavailable unless a role upgrade is approved."
  };
}
