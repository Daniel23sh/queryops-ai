from __future__ import annotations

from dataclasses import dataclass

from app.models.product import SupportedActionType


@dataclass(frozen=True)
class ActionPresentation:
    request_title: str
    pending_body: str
    preview_summary: str
    requested_summary: str
    cancelled_summary: str
    rejected_summary: str
    rejected_body: str
    approved_summary: str
    executed_summary: str
    approved_body: str
    completed_body: str
    approver_completed_body: str
    target_id_field: str
    status_field: str
    before_status: str
    after_status: str
    estimated_impact_keys: tuple[str, ...] = ()


_PRESENTATIONS = {
    SupportedActionType.RECLAIM_UNUSED_LICENSE: ActionPresentation(
        request_title="Reclaim unused licenses",
        pending_body="A reclaim unused license request is ready for review.",
        preview_summary="Reclaim unused license preview created.",
        requested_summary="Reclaim unused license request submitted for approval.",
        cancelled_summary="Reclaim unused license request cancelled by the requester.",
        rejected_summary="Reclaim unused license request rejected.",
        rejected_body="Your reclaim unused license request was rejected.",
        approved_summary="Reclaim unused license request approved for synchronous execution.",
        executed_summary="Reclaim unused license action completed.",
        approved_body="Your reclaim unused license request was approved.",
        completed_body="Your reclaim unused license action completed.",
        approver_completed_body="The reclaim unused license action completed.",
        target_id_field="license_assignment_id",
        status_field="status",
        before_status="active",
        after_status="reclaimed",
        estimated_impact_keys=("estimated_monthly_savings",),
    ),
    SupportedActionType.DISABLE_INACTIVE_USER: ActionPresentation(
        request_title="Disable inactive users",
        pending_body="A disable inactive user request is ready for review.",
        preview_summary="Disable inactive user preview created.",
        requested_summary="Disable inactive user request submitted for approval.",
        cancelled_summary="Disable inactive user request cancelled by the requester.",
        rejected_summary="Disable inactive user request rejected.",
        rejected_body="Your disable inactive user request was rejected.",
        approved_summary="Disable inactive user request approved for synchronous execution.",
        executed_summary="Disable inactive user action completed.",
        approved_body="Your disable inactive user request was approved.",
        completed_body="Your disable inactive user action completed.",
        approver_completed_body="The disable inactive user action completed.",
        target_id_field="directory_user_id",
        status_field="account_status",
        before_status="active",
        after_status="disabled",
    ),
}


def action_presentation(action_type: SupportedActionType | str) -> ActionPresentation:
    try:
        supported_type = SupportedActionType(action_type)
    except (TypeError, ValueError) as exc:
        raise ValueError("Unknown action type.") from exc
    return _PRESENTATIONS[supported_type]
