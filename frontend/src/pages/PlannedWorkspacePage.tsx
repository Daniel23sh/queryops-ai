import type { AuthUser } from "../auth/types";
import { formatRole } from "../lib/format";
import type { NavItem } from "../app/navigation";

type PlannedWorkspaceCard = {
  title: string;
  status: string;
  description: string;
  tone?: "blue" | "green" | "warning" | "muted";
};

type PlannedWorkspaceAction = {
  label: string;
  description: string;
};

type PlannedWorkspaceContent = {
  summary: string;
  cards: PlannedWorkspaceCard[];
  actions: PlannedWorkspaceAction[];
};

const PLACEHOLDER_SCOPE_NOTICE =
  "Visual preview only. This page does not run queries, create dashboards, export files, execute actions, approve requests, or call any additional backend APIs.";

const PLANNED_WORKSPACE_CONTENT: Record<string, PlannedWorkspaceContent> = {
  templates: {
    summary:
      "Approved query templates are available from Ask Data while standalone template management waits for a later milestone.",
    cards: [
      {
        title: "Catalog source",
        status: "Ask Data",
        description: "The approved template catalog is already reachable from Ask Data.",
        tone: "blue"
      },
      {
        title: "Template defaults",
        status: "Backend-owned",
        description: "Template runs continue to use existing backend defaults and validation.",
        tone: "green"
      },
      {
        title: "Management UI",
        status: "Future milestone",
        description: "Creating or editing templates is intentionally outside this PR.",
        tone: "muted"
      }
    ],
    actions: [
      {
        label: "Create template",
        description: "Template authoring is not implemented in this checkpoint."
      },
      {
        label: "Manage catalog",
        description: "Catalog administration remains future work."
      }
    ]
  },
  "query-history": {
    summary:
      "Query history navigation is reserved for roles with history visibility; this screen remains a safe visual preview until the history UI is wired.",
    cards: [
      {
        title: "History access",
        status: "Role-gated",
        description: "Only permitted roles can reach this workspace entry.",
        tone: "blue"
      },
      {
        title: "Scope history",
        status: "Future view",
        description: "Dedicated own, department, and scope history screens are not added here.",
        tone: "muted"
      },
      {
        title: "Exports",
        status: "Disabled",
        description: "CSV and report export behavior remains outside Milestone 5 PR6.",
        tone: "warning"
      }
    ],
    actions: [
      {
        label: "Open history timeline",
        description: "History timelines are not wired in this visual checkpoint."
      },
      {
        label: "Export query history",
        description: "Export behavior is intentionally disabled."
      }
    ]
  },
  "sql-technical": {
    summary:
      "Technical details remain role-gated and contained inside Ask Data result tabs for Analyst and Admin users.",
    cards: [
      {
        title: "Technical tab policy",
        status: "Ask Data only",
        description: "Technical labels stay tied to Ask Data result tabs instead of a standalone console.",
        tone: "blue"
      },
      {
        title: "Diagnostics posture",
        status: "Structured and safe",
        description: "Diagnostics views remain filtered by the existing Ask Data presentation.",
        tone: "green"
      },
      {
        title: "Standalone tooling",
        status: "Not implemented",
        description: "This page does not run SQL tools, previews, exports, or debug actions.",
        tone: "muted"
      }
    ],
    actions: [
      {
        label: "Open technical console",
        description: "Standalone technical tooling is not part of this milestone."
      },
      {
        label: "Export technical report",
        description: "Technical export behavior remains future work."
      }
    ]
  },
  "department-dashboards": {
    summary:
      "Department dashboard management is planned for a later milestone. This preview shows the governance shape without saved-card behavior.",
    cards: [
      {
        title: "Department cards",
        status: "Future persistence",
        description: "Saving cards to department dashboards is intentionally disabled.",
        tone: "blue"
      },
      {
        title: "Sharing model",
        status: "Governed",
        description: "Dashboard visibility will follow role and scope policy when implemented.",
        tone: "green"
      },
      {
        title: "Layout controls",
        status: "Not wired",
        description: "Drag, pin, and layout persistence are reserved for later milestones.",
        tone: "muted"
      }
    ],
    actions: [
      {
        label: "Create dashboard",
        description: "Dashboard creation is not implemented in this PR."
      },
      {
        label: "Save dashboard card",
        description: "Saved-card behavior remains future work."
      }
    ]
  },
  "admin-console": {
    summary:
      "Administrative controls are staged intentionally. Role Requests remains the active admin workflow in this milestone.",
    cards: [
      {
        title: "Role requests",
        status: "Live workflow",
        description: "Use the existing Role Requests page for role-only admin decisions.",
        tone: "green"
      },
      {
        title: "Permission controls",
        status: "Planned",
        description: "Policy editing and permission management are not added here.",
        tone: "muted"
      },
      {
        title: "Admin actions",
        status: "Disabled",
        description: "No operational action preview or execution controls are introduced.",
        tone: "warning"
      }
    ],
    actions: [
      {
        label: "Edit permissions",
        description: "Permission editing remains future work."
      },
      {
        label: "Run admin action",
        description: "Admin actions are not implemented in this checkpoint."
      }
    ]
  },
  users: {
    summary:
      "User management is planned for a later milestone. Demo identity context remains read-only from this page.",
    cards: [
      {
        title: "Demo identities",
        status: "Read-only context",
        description: "Current user identity is shown in the workspace header only.",
        tone: "blue"
      },
      {
        title: "Role changes",
        status: "Request workflow",
        description: "Role changes continue through the existing request and review flow.",
        tone: "green"
      },
      {
        title: "Account controls",
        status: "Not implemented",
        description: "Invites, disables, and user edits are outside this PR.",
        tone: "muted"
      }
    ],
    actions: [
      {
        label: "Invite user",
        description: "User invitations are not wired in demo auth."
      },
      {
        label: "Disable user",
        description: "Account mutation controls remain future work."
      }
    ]
  },
  audit: {
    summary:
      "Audit review is planned for later milestones. Backend governance remains the source of truth while this screen stays inert.",
    cards: [
      {
        title: "Audit timeline",
        status: "Future view",
        description: "A dedicated audit timeline is not added in this visual checkpoint.",
        tone: "blue"
      },
      {
        title: "Security posture",
        status: "Backend governed",
        description: "This page does not change audit, auth, role, or query behavior.",
        tone: "green"
      },
      {
        title: "Audit exports",
        status: "Disabled",
        description: "Audit export behavior remains outside the approved scope.",
        tone: "warning"
      }
    ],
    actions: [
      {
        label: "Open audit timeline",
        description: "Audit timelines are not wired in this PR."
      },
      {
        label: "Export audit",
        description: "Audit export remains future work."
      }
    ]
  }
};

export function PlannedWorkspacePage({
  item,
  user
}: {
  item: NavItem;
  user: AuthUser;
}) {
  const content =
    PLANNED_WORKSPACE_CONTENT[item.id] ??
    ({
      summary: item.summary,
      cards: [
        {
          title: "Workspace status",
          status: "Planned",
          description: "This workspace is intentionally visual-only for this PR.",
          tone: "muted"
        }
      ],
      actions: [
        {
          label: "Open workspace",
          description: "This control is disabled until the feature is implemented."
        }
      ]
    } satisfies PlannedWorkspaceContent);
  const roleLabel = formatRole(user.role);
  const departmentLabel = user.department?.name ?? "No department assigned";

  return (
    <article
      className="placeholder-panel"
      role="region"
      aria-label={`${item.label} planned workspace`}
    >
      <section className="placeholder-panel__hero" aria-labelledby="workspace-title">
        <div className="placeholder-panel__copy">
          <p className="placeholder-panel__badge">Planned workspace</p>
          <h1 id="workspace-title">{item.title}</h1>
          <p className="subtitle">{content.summary}</p>
        </div>
        <div className="placeholder-panel__chips" aria-label="Workspace context">
          <span>Role: {roleLabel}</span>
          <span>Scope: {departmentLabel}</span>
          <span>Demo environment</span>
        </div>
      </section>

      <section className="placeholder-panel__card-grid" aria-label={`${item.label} status`}>
        {content.cards.map((card) => (
          <article
            key={card.title}
            className="placeholder-status-card"
            data-tone={card.tone ?? "blue"}
          >
            <p className="placeholder-status-card__label">{card.title}</p>
            <h2>{card.status}</h2>
            <p>{card.description}</p>
          </article>
        ))}
      </section>

      <div className="placeholder-panel__work-grid">
        <section
          className="placeholder-panel__notice"
          aria-labelledby={`${item.id}-guardrail-title`}
        >
          <p className="eyebrow">Scope guardrail</p>
          <h2 id={`${item.id}-guardrail-title`}>Visual preview only</h2>
          <p>{PLACEHOLDER_SCOPE_NOTICE}</p>
        </section>

        <section
          className="placeholder-panel__actions"
          aria-labelledby={`${item.id}-actions-title`}
        >
          <div>
            <p className="eyebrow">Future controls</p>
            <h2 id={`${item.id}-actions-title`}>Intentionally disabled</h2>
          </div>
          <div className="placeholder-action-list">
            {content.actions.map((action) => (
              <button
                key={action.label}
                type="button"
                className="placeholder-action-button"
                aria-label={action.label}
                disabled
              >
                <span>{action.label}</span>
                <small>{action.description}</small>
              </button>
            ))}
          </div>
        </section>
      </div>
    </article>
  );
}
