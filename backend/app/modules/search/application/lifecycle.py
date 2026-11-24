"""Index build transitions require bound validation before readiness."""

from datetime import UTC, datetime

from app.modules.search.domain.contracts import IndexVersionStatus, StoredIndexVersion


def advance_index_build(index: StoredIndexVersion, target: IndexVersionStatus, *, now: datetime) -> StoredIndexVersion:
    """Change build metadata only; activation/rollback require actual publication confirmation."""
    transitions = {
        IndexVersionStatus.BUILDING: {IndexVersionStatus.VALIDATING, IndexVersionStatus.FAILED},
        IndexVersionStatus.VALIDATING: {IndexVersionStatus.READY, IndexVersionStatus.FAILED},
    }
    if target not in transitions.get(index.status, set()):
        raise ValueError("Illegal index build transition; publication cannot be inferred from build readiness")
    if now.tzinfo is None or now.utcoffset() is None or now < index.updated_at:
        raise ValueError("Index lifecycle requires a nondecreasing timezone-aware clock")
    return StoredIndexVersion.model_validate(
        {**index.model_dump(), "status": target, "updated_at": now.astimezone(UTC)}
    )
