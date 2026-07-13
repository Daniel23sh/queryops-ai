import { useEffect, useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import {
  createRoleRequest,
  getMyRoleRequests,
  type RoleRequest,
  type RoleUpgradeTarget
} from "../../api/roleRequests";
import type { AuthUser } from "../../auth/types";
import { formatRequestStatus, formatRole } from "../../lib/format";

const ROLE_UPGRADE_OPTIONS: Array<{ value: RoleUpgradeTarget; label: string }> = [
  { value: "manager", label: "Manager" },
  { value: "analyst", label: "Analyst" },
  { value: "admin", label: "Admin" }
];

const ROLE_UPGRADE_ORDER: RoleUpgradeTarget[] = ["manager", "analyst", "admin"];

export function RoleUpgradeSection({
  userRole,
  csrfToken
}: {
  userRole: AuthUser["role"];
  csrfToken: string | null;
}) {
  const roleUpgradeOptions = getRoleUpgradeOptions(userRole);
  const hasRoleUpgradeOptions = roleUpgradeOptions.length > 0;
  const [requestedRole, setRequestedRole] =
    useState<RoleUpgradeTarget>(roleUpgradeOptions[0]?.value ?? "manager");
  const [reason, setReason] = useState("");
  const [roleRequests, setRoleRequests] = useState<RoleRequest[]>([]);
  const [isLoadingRequests, setIsLoadingRequests] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    let isCurrent = true;

    if (!hasRoleUpgradeOptions) {
      setIsLoadingRequests(false);
      return () => {
        isCurrent = false;
      };
    }

    setIsLoadingRequests(true);
    setLoadError(null);

    getMyRoleRequests()
      .then((requests) => {
        if (!isCurrent) {
          return;
        }
        setRoleRequests(requests);
        setIsLoadingRequests(false);
      })
      .catch((error) => {
        if (!isCurrent) {
          return;
        }
        setLoadError(formatRoleRequestError(error, "Role requests could not be loaded."));
        setIsLoadingRequests(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [hasRoleUpgradeOptions]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError(null);
    setSuccessMessage(null);

    const trimmedReason = reason.trim();
    if (!trimmedReason) {
      setSubmitError("Enter a reason for the role upgrade request.");
      return;
    }

    if (!csrfToken) {
      setSubmitError("Refresh your session before submitting a role upgrade request.");
      return;
    }

    if (!hasRoleUpgradeOptions) {
      setSubmitError("No role upgrade target is available for your current role.");
      return;
    }

    setIsSubmitting(true);
    try {
      const createdRequest = await createRoleRequest(
        requestedRole,
        trimmedReason,
        csrfToken
      );
      setRoleRequests((requests) => [
        createdRequest,
        ...requests.filter((request) => request.id !== createdRequest.id)
      ]);
      setReason("");
      setSuccessMessage("Role upgrade request submitted.");
    } catch (error) {
      setSubmitError(formatRoleRequestError(error, "Role upgrade request failed."));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (!hasRoleUpgradeOptions) {
    return null;
  }

  return (
    <section className="profile-section profile-role-upgrade" aria-labelledby="role-upgrade-title">
      <div className="profile-section__header">
        <h2 id="role-upgrade-title">Role Upgrade</h2>
        <p>Request a higher role. An administrator must review the request.</p>
      </div>

      <form className="role-request-form" onSubmit={(event) => void handleSubmit(event)}>
        <div className="form-field">
          <label htmlFor="requested-role">Requested role</label>
          <select
            id="requested-role"
            value={requestedRole}
            onChange={(event) =>
              setRequestedRole(event.target.value as RoleUpgradeTarget)
            }
          >
            {roleUpgradeOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="form-field">
          <label htmlFor="role-request-reason">Reason</label>
          <textarea
            id="role-request-reason"
            rows={4}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </div>

        {submitError ? (
          <p className="form-message form-message--error" role="alert">
            {submitError}
          </p>
        ) : null}

        {successMessage ? (
          <p className="form-message form-message--success" role="status">
            {successMessage}
          </p>
        ) : null}

        <button
          type="submit"
          className="primary-action-button"
          disabled={isSubmitting}
        >
          {isSubmitting ? "Submitting..." : "Submit request"}
        </button>
      </form>

      <section className="role-request-status" aria-labelledby="role-request-status-title">
        <div className="role-request-status__header">
          <h3 id="role-request-status-title">Existing requests</h3>
        </div>

        {isLoadingRequests ? (
          <p className="status-copy">Loading role requests...</p>
        ) : null}

        {loadError ? (
          <p className="form-message form-message--error" role="alert">
            {loadError}
          </p>
        ) : null}

        {!isLoadingRequests && !loadError && roleRequests.length === 0 ? (
          <p className="status-copy">No role upgrade requests yet.</p>
        ) : null}

        {!isLoadingRequests && !loadError && roleRequests.length > 0 ? (
          <ul className="role-request-list">
            {roleRequests.map((request) => (
              <li key={request.id} className="role-request-list__item">
                <div>
                  <h3>{formatRole(request.requestedRole)}</h3>
                  <p>{request.reason ?? "No reason provided."}</p>
                </div>
                <span
                  className="role-request-status-badge"
                  data-status={request.status}
                >
                  {formatRequestStatus(request.status)}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </section>
  );
}

function getRoleUpgradeOptions(
  currentRole: AuthUser["role"]
): Array<{ value: RoleUpgradeTarget; label: string }> {
  if (currentRole === null || currentRole === "user") {
    return ROLE_UPGRADE_OPTIONS;
  }

  const currentRoleIndex = ROLE_UPGRADE_ORDER.indexOf(currentRole);
  if (currentRoleIndex === -1) {
    return ROLE_UPGRADE_OPTIONS;
  }

  return ROLE_UPGRADE_OPTIONS.filter(
    (option) => ROLE_UPGRADE_ORDER.indexOf(option.value) > currentRoleIndex
  );
}

function formatRoleRequestError(error: unknown, fallbackMessage: string): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  return fallbackMessage;
}
