import { useEffect, useState } from "react";

import { ApiError } from "../../api/client";
import {
  approveRoleRequest,
  getAdminRoleRequests,
  rejectRoleRequest,
  type RoleRequest
} from "../../api/roleRequests";
import { formatRequestStatus, formatRole } from "../../lib/format";

type AdminDecisionAction = "approve" | "reject";

export function RoleRequestsPage({ csrfToken }: { csrfToken: string | null }) {
  const [roleRequests, setRoleRequests] = useState<RoleRequest[]>([]);
  const [decisionReasons, setDecisionReasons] = useState<Record<string, string>>({});
  const [isLoadingRequests, setIsLoadingRequests] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [processingDecision, setProcessingDecision] = useState<{
    requestId: string;
    action: AdminDecisionAction;
  } | null>(null);

  useEffect(() => {
    let isCurrent = true;
    setIsLoadingRequests(true);
    setLoadError(null);

    getAdminRoleRequests()
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
        setLoadError(formatRoleRequestError(error, "Admin role requests could not be loaded."));
        setIsLoadingRequests(false);
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  async function handleDecision(request: RoleRequest, action: AdminDecisionAction) {
    const decisionReason = (decisionReasons[request.id] ?? "").trim();
    setDecisionError(null);
    setSuccessMessage(null);

    if (!decisionReason) {
      setDecisionError("Enter a decision reason before approving or rejecting.");
      return;
    }

    if (!csrfToken) {
      setDecisionError("Refresh your session before reviewing role requests.");
      return;
    }

    setProcessingDecision({ requestId: request.id, action });

    try {
      const updatedRequest =
        action === "approve"
          ? await approveRoleRequest(request.id, decisionReason, csrfToken)
          : await rejectRoleRequest(request.id, decisionReason, csrfToken);

      setRoleRequests((requests) =>
        requests.map((existingRequest) =>
          existingRequest.id === updatedRequest.id ? updatedRequest : existingRequest
        )
      );
      setDecisionReasons((currentReasons) => ({
        ...currentReasons,
        [request.id]: ""
      }));
      setSuccessMessage(
        action === "approve" ? "Role request approved." : "Role request rejected."
      );
    } catch (error) {
      setDecisionError(
        formatRoleRequestError(error, `Role request ${action} failed.`)
      );
    } finally {
      setProcessingDecision(null);
    }
  }

  return (
    <article className="role-upgrade-panel admin-role-requests-panel">
      <div className="role-upgrade-panel__header">
        <p className="eyebrow">Role upgrade review</p>
        <h1 id="workspace-title">Admin Role Requests</h1>
        <p className="subtitle">
          Review role upgrade requests only. Approving a request changes the
          requester's role after their next auth refresh.
        </p>
        <div className="role-upgrade-panel__chips" aria-label="Admin review safeguards">
          <span>Existing approval flow</span>
          <span>Role-only decision</span>
          <span>No policy changes</span>
        </div>
      </div>

      {isLoadingRequests ? (
        <p className="status-copy">Loading admin role requests...</p>
      ) : null}

      {loadError ? (
        <p className="form-message form-message--error" role="alert">
          {loadError}
        </p>
      ) : null}

      {decisionError ? (
        <p className="form-message form-message--error" role="alert">
          {decisionError}
        </p>
      ) : null}

      {successMessage ? (
        <p className="form-message form-message--success" role="status">
          {successMessage}
        </p>
      ) : null}

      {!isLoadingRequests && !loadError && roleRequests.length === 0 ? (
        <p className="status-copy">No role upgrade requests to review.</p>
      ) : null}

      {!isLoadingRequests && !loadError && roleRequests.length > 0 ? (
        <ul className="role-request-list admin-role-request-list">
          {roleRequests.map((request) => {
            const requesterName = request.requester?.fullName ?? "Unknown requester";
            const requesterEmail = request.requester?.email ?? "No requester email";
            const decisionReasonId = `decision-reason-${request.id}`;
            const isPending = request.status === "pending";
            const isApproving =
              processingDecision?.requestId === request.id &&
              processingDecision.action === "approve";
            const isRejecting =
              processingDecision?.requestId === request.id &&
              processingDecision.action === "reject";
            const isProcessing = processingDecision !== null;

            return (
              <li key={request.id} className="admin-role-request-list__item">
                <div className="admin-role-request-card__summary">
                  <div>
                    <h2>{requesterName}</h2>
                    <p>{requesterEmail}</p>
                  </div>
                  <span
                    className="role-request-status-badge"
                    data-status={request.status}
                  >
                    {formatRequestStatus(request.status)}
                  </span>
                </div>

                <dl className="admin-role-request-details">
                  <div>
                    <dt>Requested role</dt>
                    <dd>{formatRole(request.requestedRole)}</dd>
                  </div>
                  <div>
                    <dt>Reason</dt>
                    <dd>{request.reason ?? "No reason provided."}</dd>
                  </div>
                  {request.decisionReason ? (
                    <div>
                      <dt>Decision reason</dt>
                      <dd>{request.decisionReason}</dd>
                    </div>
                  ) : null}
                </dl>

                {isPending ? (
                  <div className="admin-role-request-decision">
                    <div className="form-field">
                      <label htmlFor={decisionReasonId}>
                        Decision reason for {requesterName}
                      </label>
                      <textarea
                        id={decisionReasonId}
                        rows={3}
                        value={decisionReasons[request.id] ?? ""}
                        onChange={(event) =>
                          setDecisionReasons((currentReasons) => ({
                            ...currentReasons,
                            [request.id]: event.target.value
                          }))
                        }
                      />
                    </div>

                    <div className="admin-role-request-actions">
                      <button
                        type="button"
                        className="primary-action-button"
                        aria-label={`Approve role request from ${requesterName}`}
                        disabled={isProcessing}
                        onClick={() => void handleDecision(request, "approve")}
                      >
                        {isApproving ? "Approving..." : "Approve request"}
                      </button>
                      <button
                        type="button"
                        className="secondary-danger-button"
                        aria-label={`Reject role request from ${requesterName}`}
                        disabled={isProcessing}
                        onClick={() => void handleDecision(request, "reject")}
                      >
                        {isRejecting ? "Rejecting..." : "Reject request"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="status-copy">
                    This role request has already been {request.status}.
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      ) : null}
    </article>
  );
}

function formatRoleRequestError(error: unknown, fallbackMessage: string): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  return fallbackMessage;
}
