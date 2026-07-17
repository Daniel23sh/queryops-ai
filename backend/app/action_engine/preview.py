from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.domains.it_operations.actions.reclaim_unused_license import (
    GLOBAL_SCOPE_REQUEST,
    OVER_THRESHOLD,
    OVERRIDE_CROSS_SCOPE,
    ReclaimActionPreview,
    ReclaimAdminOverrideRecord,
    ReclaimEligibleRecord,
    ReclaimSkippedRecord,
)
from app.models.product import ActionRequest, SupportedActionType


PREVIEW_SCHEMA_VERSION = 1


class InvalidPreviewSnapshotError(ValueError):
    pass


@dataclass(frozen=True, kw_only=True)
class PreviewStorage:
    preview_json: dict[str, Any]
    policy_flags_json: dict[str, Any]
    skipped_records_json: dict[str, Any]
    access_context_snapshot_json: dict[str, Any]
    access_decision_snapshot_json: dict[str, Any]
    record_count: int
    skipped_count: int


def build_reclaim_preview_storage(preview: ReclaimActionPreview) -> PreviewStorage:
    preview_json = {
        "schema_version": PREVIEW_SCHEMA_VERSION,
        "action_type": preview.action_type.value,
        "summary": {
            "affected_license_assignment_count": (
                preview.affected_license_assignment_count
            ),
            "affected_user_count": preview.affected_user_count,
            "normal_eligible_count": preview.normal_eligible_count,
            "skipped_count": preview.skipped_count,
            "override_required_count": preview.override_required_count,
            "high_confidence_count": preview.high_confidence_count,
            "estimated_monthly_savings": _money_string(
                preview.estimated_monthly_savings
            ),
            "override_estimated_monthly_savings": _money_string(
                preview.override_estimated_monthly_savings
            ),
        },
        "eligible_records": [
            _serialize_eligible_record(record)
            for record in preview.eligible_records
            if isinstance(record, ReclaimEligibleRecord)
        ],
        "override_required_records": [
            _serialize_override_record(record)
            for record in preview.admin_override_records
            if isinstance(record, ReclaimAdminOverrideRecord)
        ],
        "generated_at": _timestamp(preview.timestamps.generated_at),
        "expires_at": _timestamp(preview.timestamps.expires_at),
        "requester_scope_ids": [str(scope_id) for scope_id in preview.requester_scope_ids],
        "target_scope_ids": [str(scope_id) for scope_id in preview.target_scope_ids],
        "resources": [
            {
                "table_name": resource.table_name,
                "display_name": resource.display_name,
                "sensitivity_level": resource.sensitivity_level,
            }
            for resource in preview.resource_descriptors
        ],
    }
    skipped_records_json = {
        "records": [
            _serialize_skipped_record(record)
            for record in preview.skipped_records
            if isinstance(record, ReclaimSkippedRecord)
        ],
        "exclusions_by_reason": [
            {"reason_code": item.reason_code, "count": item.count}
            for item in preview.exclusions_by_reason
        ],
    }
    policy_flags_json = {
        "flags": [
            {
                "code": flag.code,
                "reason": flag.reason,
                "requires_admin": flag.requires_admin,
                "admin_overridable": flag.admin_overridable,
            }
            for flag in preview.policy_flags
        ],
        "requires_admin": preview.requires_admin,
        "crosses_scopes": preview.crosses_scopes,
        "requires_policy_override": preview.requires_policy_override,
    }
    access_context = preview.access_context_snapshot
    access_context_snapshot_json = {
        "app_user_id": str(access_context.app_user_id),
        "effective_action_permissions": list(access_context.permissions),
        "assigned_scopes": list(access_context.assigned_scopes),
        "assigned_scope_ids": [
            str(scope_id) for scope_id in access_context.assigned_scope_ids
        ],
        "has_global_scope": access_context.has_global_scope,
    }
    access_decision = preview.access_decision_snapshot
    access_decision_snapshot_json = {
        "allowed": access_decision.allowed,
        "reason_code": access_decision.reason,
        "required_permission": access_decision.required_permission,
        "matched_scopes": list(access_decision.matched_scopes),
        "resource_decisions": [
            {
                "table_name": decision.table_name,
                "allowed": decision.allowed,
                "required_permission": decision.required_permission,
                "matched_scopes": list(decision.matched_scopes),
            }
            for decision in access_decision.resource_decisions
        ],
        "read_boundary": {
            "runtime_role": access_decision.runtime_role,
            "transaction_read_only": access_decision.transaction_read_only,
            "row_security_enabled": access_decision.row_security_enabled,
        },
    }
    return PreviewStorage(
        preview_json=preview_json,
        policy_flags_json=policy_flags_json,
        skipped_records_json=skipped_records_json,
        access_context_snapshot_json=access_context_snapshot_json,
        access_decision_snapshot_json=access_decision_snapshot_json,
        record_count=preview.affected_license_assignment_count,
        skipped_count=preview.skipped_count,
    )


def validate_reclaim_snapshot(action_request: ActionRequest) -> None:
    preview = action_request.preview_json
    policy = action_request.policy_flags_json
    skipped = action_request.skipped_records_json
    if not isinstance(preview, dict) or not isinstance(policy, dict):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if not isinstance(skipped, dict):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if preview.get("schema_version") != PREVIEW_SCHEMA_VERSION:
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if preview.get("action_type") != SupportedActionType.RECLAIM_UNUSED_LICENSE.value:
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if action_request.action_type != SupportedActionType.RECLAIM_UNUSED_LICENSE.value:
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")

    summary = preview.get("summary")
    eligible = preview.get("eligible_records")
    overrides = preview.get("override_required_records")
    skipped_records = skipped.get("records")
    flags = policy.get("flags")
    if not isinstance(summary, dict):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if not all(isinstance(records, list) for records in (eligible, overrides, skipped_records)):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if not isinstance(flags, list):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")

    for record in eligible:
        _validate_record(record, require_actionable_fields=True, require_override=False)
    for record in overrides:
        _validate_record(record, require_actionable_fields=True, require_override=True)
    for record in skipped_records:
        _validate_record(record, require_actionable_fields=False, require_override=False)

    expected_counts = {
        "normal_eligible_count": len(eligible),
        "override_required_count": len(overrides),
        "skipped_count": len(skipped_records),
        "affected_license_assignment_count": len(eligible) + len(overrides),
    }
    for key, expected in expected_counts.items():
        if summary.get(key) != expected:
            raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if action_request.record_count != expected_counts["affected_license_assignment_count"]:
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if action_request.skipped_count != expected_counts["skipped_count"]:
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    _validate_summary(summary, expected_counts)
    if summary["high_confidence_count"] != sum(
        record["high_confidence"] for record in (*eligible, *overrides)
    ):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if Decimal(summary["estimated_monthly_savings"]) != sum(
        (Decimal(record["monthly_cost_usd"]) for record in eligible),
        Decimal("0"),
    ):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if Decimal(summary["override_estimated_monthly_savings"]) != sum(
        (Decimal(record["monthly_cost_usd"]) for record in overrides),
        Decimal("0"),
    ):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    _validate_exclusions(skipped.get("exclusions_by_reason"))

    override_codes = {
        code
        for record in overrides
        for code in record["override_reason_codes"]
    }
    expected_flag_codes = set(override_codes)
    if expected_counts["affected_license_assignment_count"] > 20:
        expected_flag_codes.add(OVER_THRESHOLD)
    if action_request.scope_type == "global":
        expected_flag_codes.add(GLOBAL_SCOPE_REQUEST)
    actual_flag_codes = _validate_policy_flags(flags)
    if actual_flag_codes != expected_flag_codes:
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if policy.get("requires_admin") is not bool(expected_flag_codes):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    revalidation_requires_admin = policy.get("revalidation_requires_admin") is True
    if action_request.requires_admin is not (
        bool(expected_flag_codes) or revalidation_requires_admin
    ):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if policy.get("requires_policy_override") is not bool(overrides):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if policy.get("crosses_scopes") is not (OVERRIDE_CROSS_SCOPE in override_codes):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")


def safe_reclaim_preview(action_request: ActionRequest) -> dict[str, Any]:
    validate_reclaim_snapshot(action_request)
    preview = action_request.preview_json
    skipped = action_request.skipped_records_json
    policy = action_request.policy_flags_json
    return {
        "summary": _safe_summary(preview["summary"]),
        "eligible_records": [
            _safe_record(record) for record in preview["eligible_records"]
        ],
        "skipped_records": [
            _safe_record(record) for record in skipped["records"]
        ],
        "override_required_records": [
            _safe_record(record)
            for record in preview["override_required_records"]
        ],
        "exclusions_by_reason": [
            {
                "reason_code": str(item.get("reason_code", "unknown")),
                "count": int(item.get("count", 0)),
            }
            for item in skipped.get("exclusions_by_reason", [])
            if isinstance(item, dict)
        ],
        "policy_flags": [
            {
                "code": str(flag.get("code", "unknown")),
                "reason": str(flag.get("reason", "Review is required.")),
            }
            for flag in [
                *policy.get("flags", []),
                *policy.get("revalidation_flags", []),
            ]
            if isinstance(flag, dict)
        ],
    }


def safe_policy_details(action_request: ActionRequest) -> dict[str, Any]:
    validate_reclaim_snapshot(action_request)
    policy = action_request.policy_flags_json
    return {
        "crosses_scopes": (
            policy.get("crosses_scopes") is True
            or policy.get("revalidation_crosses_scopes") is True
        ),
        "requires_policy_override": (
            policy.get("requires_policy_override") is True
            or policy.get("revalidation_requires_policy_override") is True
        ),
        "record_count_over_analyst_threshold": any(
            isinstance(flag, dict)
            and flag.get("code") == "record_count_over_analyst_threshold"
            for flag in policy.get("flags", [])
        ),
    }


def _serialize_eligible_record(record: ReclaimEligibleRecord) -> dict[str, Any]:
    return _record_payload(
        record_type=record.record_type,
        record_id=record.record_id,
        scope_id=record.scope_id,
        scope_type=record.scope_type,
        scope_key=record.scope_key,
        user_display_label=record.user_display_label,
        license_product=record.license_product,
        license_vendor=record.license_vendor,
        last_used_at=record.last_used_at,
        monthly_cost_usd=record.monthly_cost_usd,
        reason_code=record.reason_code,
        reason=(
            "No license usage is recorded."
            if record.reason_code == "no_recorded_usage"
            else "The license has not been used for more than 60 days."
        ),
        high_confidence=record.high_confidence,
    )


def _serialize_skipped_record(record: ReclaimSkippedRecord) -> dict[str, Any]:
    return _record_payload(
        record_type=record.record_type,
        record_id=record.record_id,
        scope_id=record.scope_id,
        scope_type=record.scope_type,
        scope_key=record.scope_key,
        user_display_label=record.user_display_label,
        license_product=record.license_product,
        license_vendor=record.license_vendor,
        last_used_at=record.last_used_at,
        monthly_cost_usd=record.monthly_cost_usd,
        reason_code=record.reason_code,
        reason=record.reason,
        high_confidence=record.high_confidence,
    )


def _serialize_override_record(
    record: ReclaimAdminOverrideRecord,
) -> dict[str, Any]:
    payload = _record_payload(
        record_type=record.record_type,
        record_id=record.record_id,
        scope_id=record.scope_id,
        scope_type=record.scope_type,
        scope_key=record.scope_key,
        user_display_label=record.user_display_label,
        license_product=record.license_product,
        license_vendor=record.license_vendor,
        last_used_at=record.last_used_at,
        monthly_cost_usd=record.monthly_cost_usd,
        reason_code=record.reason_code,
        reason=record.reason,
        high_confidence=record.high_confidence,
    )
    payload["override_reason_codes"] = list(record.override_reason_codes)
    return payload


def _record_payload(
    *,
    record_type: str,
    record_id,
    scope_id,
    scope_type: str,
    scope_key: str,
    user_display_label: str | None,
    license_product: str | None,
    license_vendor: str | None,
    last_used_at: datetime | None,
    monthly_cost_usd: Decimal | None,
    reason_code: str,
    reason: str,
    high_confidence: bool,
) -> dict[str, Any]:
    return {
        "record_type": record_type,
        "record_id": str(record_id),
        "license_assignment_id": (
            str(record_id) if record_type == "license_assignment" else None
        ),
        "scope": (
            {
                "id": str(scope_id),
                "type": scope_type,
                "key": scope_key,
            }
            if scope_id is not None
            else {"id": None, "type": scope_type, "key": scope_key}
        ),
        "user_display_label": user_display_label,
        "license_product": license_product,
        "license_vendor": license_vendor,
        "last_used_at": _timestamp(last_used_at) if last_used_at else None,
        "monthly_cost_usd": (
            _money_string(monthly_cost_usd) if monthly_cost_usd is not None else None
        ),
        "reason_code": reason_code,
        "reason": reason,
        "high_confidence": high_confidence,
    }


def _safe_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    scope = record.get("scope")
    if not isinstance(scope, dict):
        scope = {"id": None, "type": None, "key": None}
    safe = {
        "record_type": _optional_string(record.get("record_type")),
        "record_id": _optional_string(record.get("record_id")),
        "license_assignment_id": _optional_string(
            record.get("license_assignment_id")
        ),
        "scope": {
            "id": _optional_string(scope.get("id")),
            "type": _optional_string(scope.get("type")),
            "key": _optional_string(scope.get("key")),
        },
        "user_display_label": _optional_string(record.get("user_display_label")),
        "license_product": _optional_string(record.get("license_product")),
        "license_vendor": _optional_string(record.get("license_vendor")),
        "last_used_at": _optional_string(record.get("last_used_at")),
        "monthly_cost_usd": _optional_string(record.get("monthly_cost_usd")),
        "reason_code": _optional_string(record.get("reason_code")),
        "reason": _optional_string(record.get("reason")),
        "high_confidence": record.get("high_confidence") is True,
    }
    override_codes = record.get("override_reason_codes")
    if isinstance(override_codes, list):
        safe["override_reason_codes"] = [
            code for code in override_codes if isinstance(code, str)
        ]
    return safe


def _safe_summary(summary: dict[str, Any]) -> dict[str, Any]:
    count_keys = (
        "affected_license_assignment_count",
        "affected_user_count",
        "normal_eligible_count",
        "skipped_count",
        "override_required_count",
        "high_confidence_count",
    )
    safe = {
        key: int(summary[key])
        for key in count_keys
        if isinstance(summary.get(key), int) and not isinstance(summary.get(key), bool)
    }
    safe["estimated_monthly_savings"] = _optional_string(
        summary.get("estimated_monthly_savings")
    )
    safe["override_estimated_monthly_savings"] = _optional_string(
        summary.get("override_estimated_monthly_savings")
    )
    return safe


def _validate_summary(
    summary: dict[str, Any],
    expected_counts: dict[str, int],
) -> None:
    count_keys = (
        "affected_license_assignment_count",
        "affected_user_count",
        "normal_eligible_count",
        "skipped_count",
        "override_required_count",
        "high_confidence_count",
    )
    for key in count_keys:
        value = summary.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    affected_count = expected_counts["affected_license_assignment_count"]
    if summary["affected_user_count"] > affected_count:
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if summary["high_confidence_count"] > affected_count:
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    for key in (
        "estimated_monthly_savings",
        "override_estimated_monthly_savings",
    ):
        value = summary.get(key)
        if not isinstance(value, str):
            raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
        try:
            amount = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise InvalidPreviewSnapshotError(
                "The stored preview is unavailable."
            ) from exc
        if not amount.is_finite() or amount < 0:
            raise InvalidPreviewSnapshotError("The stored preview is unavailable.")


def _validate_record(
    record: Any,
    *,
    require_actionable_fields: bool,
    require_override: bool,
) -> None:
    if not isinstance(record, dict):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    record_type = record.get("record_type")
    if record_type not in {"directory_user", "license_assignment"}:
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if require_actionable_fields and record_type != "license_assignment":
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    record_id = _validated_uuid_string(record.get("record_id"))
    assignment_id = record.get("license_assignment_id")
    if record_type == "license_assignment":
        if _validated_uuid_string(assignment_id) != record_id:
            raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    elif assignment_id is not None:
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")

    scope = record.get("scope")
    if not isinstance(scope, dict):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if not isinstance(scope.get("type"), str) or not scope["type"] or not isinstance(
        scope.get("key"), str
    ) or not scope["key"]:
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    scope_id = scope.get("id")
    if scope_id is not None:
        _validated_uuid_string(scope_id)

    for key in (
        "user_display_label",
        "license_product",
        "license_vendor",
        "last_used_at",
        "monthly_cost_usd",
    ):
        if record.get(key) is not None and not isinstance(record.get(key), str):
            raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if (
        not isinstance(record.get("reason_code"), str)
        or not record["reason_code"]
        or not isinstance(record.get("reason"), str)
        or not record["reason"]
    ):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if not isinstance(record.get("high_confidence"), bool):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if require_actionable_fields and (
        scope_id is None
        or not all(
            isinstance(record.get(key), str) and bool(record[key])
            for key in (
                "user_display_label",
                "license_product",
                "license_vendor",
                "monthly_cost_usd",
            )
        )
    ):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    if record.get("monthly_cost_usd") is not None:
        try:
            amount = Decimal(record["monthly_cost_usd"])
        except (InvalidOperation, ValueError) as exc:
            raise InvalidPreviewSnapshotError(
                "The stored preview is unavailable."
            ) from exc
        if not amount.is_finite() or amount < 0:
            raise InvalidPreviewSnapshotError("The stored preview is unavailable.")

    override_codes = record.get("override_reason_codes")
    if require_override:
        if (
            not isinstance(override_codes, list)
            or not override_codes
            or not all(isinstance(code, str) and code for code in override_codes)
        ):
            raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
        if record["reason_code"] != override_codes[0]:
            raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    elif override_codes is not None:
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")


def _validate_exclusions(value: Any) -> None:
    if not isinstance(value, list):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("reason_code"), str):
            raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
        count = item.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise InvalidPreviewSnapshotError("The stored preview is unavailable.")


def _validate_policy_flags(flags: list[Any]) -> set[str]:
    codes: list[str] = []
    for flag in flags:
        if not isinstance(flag, dict):
            raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
        code = flag.get("code")
        if (
            not isinstance(code, str)
            or not code
            or not isinstance(flag.get("reason"), str)
            or flag.get("requires_admin") is not True
            or flag.get("admin_overridable") is not True
        ):
            raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
        codes.append(code)
    if len(codes) != len(set(codes)):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    return set(codes)


def _validated_uuid_string(value: Any) -> str:
    if not isinstance(value, str):
        raise InvalidPreviewSnapshotError("The stored preview is unavailable.")
    try:
        return str(uuid.UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise InvalidPreviewSnapshotError(
            "The stored preview is unavailable."
        ) from exc


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _money_string(value: Decimal) -> str:
    return format(
        value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        ".2f",
    )


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
