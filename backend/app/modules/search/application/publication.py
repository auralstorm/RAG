"""Validate safe publication/rollback preconditions without changing current pointers."""

from datetime import UTC, datetime

from app.modules.documents.domain.contracts import DocumentStatus, DocumentVersionStatus
from app.modules.knowledge_base.domain.contracts import KnowledgeBaseStatus
from app.modules.policy.application.authorization import authorize
from app.modules.policy.domain.contracts import (
    AccessContext,
    AccessPurpose,
    AuthorizationRequest,
    AuthorizationSnapshot,
)
from app.modules.search.domain.contracts import (
    IndexVersionStatus,
    PublicationAction,
    PublicationPlan,
    PublicationRequest,
    PublicationSnapshot,
)


class PublicationRefusedError(ValueError):
    """Safe precondition failure; no external operation has been performed."""


def prepare_index_publication(
    request: PublicationRequest,
    snapshot: PublicationSnapshot,
    context: AccessContext | None,
    authorization: AuthorizationSnapshot,
    *,
    now: datetime,
) -> PublicationPlan:
    """Caller owns current reads, key deduplication and real CAS/ES execution/reconciliation."""
    decision = authorize(
        AuthorizationRequest(permission_code="kb.manage", purpose=AccessPurpose.ADMIN, kb_id=request.kb_id),
        context,
        authorization,
        now=now,
    )
    if not decision.allowed or decision.subject_id is None:
        raise PermissionError("Index publication requires current KB management permission")
    kb, target, current = snapshot.kb, snapshot.target, snapshot.current
    if kb.status is not KnowledgeBaseStatus.ACTIVE or request.kb_id != kb.id or target.kb_id != kb.id:
        raise PublicationRefusedError("Publication requires the matching active KB")
    if (
        request.target_index_version_id != target.id
        or request.expected_active_index_version_id != kb.active_index_version_id
    ):
        raise PublicationRefusedError("Publication CAS intent no longer matches current pointers")
    alias = snapshot.alias
    if (
        alias.kb_id != kb.id
        or alias.alias_name != target.alias_name
        or alias.active_index_version_id != kb.active_index_version_id
    ):
        raise PublicationRefusedError("Observed alias and KB pointers do not agree")
    if current is None:
        if kb.active_index_version_id is not None or alias.physical_index_name is not None:
            raise PublicationRefusedError("Current index facts are required for an existing pointer")
    elif (
        current.id != kb.active_index_version_id
        or current.kb_id != kb.id
        or current.status is not IndexVersionStatus.ACTIVE
        or current.alias_name != alias.alias_name
        or current.physical_index_name != alias.physical_index_name
    ):
        raise PublicationRefusedError("Current index and alias facts do not agree")
    if target.id == kb.active_index_version_id:
        raise PublicationRefusedError("An already active target requires the original operation receipt")
    if target.physical_index_name == alias.physical_index_name:
        raise PublicationRefusedError("Target and current index versions must use distinct physical indexes")
    if request.action is PublicationAction.PUBLISH:
        if target.status is not IndexVersionStatus.READY or target.embedding != kb.embedding:
            raise PublicationRefusedError(
                "Publication requires a ready target with the desired embedding configuration"
            )
    elif target.status is not IndexVersionStatus.ROLLED_BACK or target.published_at is None:
        raise PublicationRefusedError("Rollback requires a retained previously published index")
    manifest = snapshot.manifest
    if (
        manifest.kb_id != kb.id
        or manifest.index_version_id != target.id
        or manifest.content_hash != target.manifest_sha256
    ):
        raise PublicationRefusedError("Target manifest does not match the index")
    report = target.validation
    if report is None or report.actual_document_count != len(manifest.documents):
        raise PublicationRefusedError("Validation report and manifest count do not agree")
    observed_times = [kb.updated_at, target.updated_at, report.checked_at]
    if current is not None:
        observed_times.append(current.updated_at)
    observed_times.extend(document.updated_at for document in snapshot.documents)
    observed_times.extend(version.updated_at for version in snapshot.document_versions)
    if now < max(observed_times):
        raise PublicationRefusedError("Publication evidence cannot come from the future")
    documents = {document.id: document for document in snapshot.documents}
    versions = {version.document_version_id: version for version in snapshot.document_versions}
    if len(documents) != len(snapshot.documents) or len(versions) != len(snapshot.document_versions):
        raise PublicationRefusedError("Publication facts contain duplicate document or version IDs")
    for member in manifest.documents:
        document, version = documents.get(member.document_id), versions.get(member.document_version_id)
        if (
            document is None
            or version is None
            or document.kb_id != kb.id
            or document.status is not DocumentStatus.ACTIVE
            or version.kb_id != kb.id
            or version.document_id != document.id
            or version.document_version != member.document_version
            or version.document_version > document.current_version
            or version.pipeline_version != target.pipeline_version
            or version.chunking_config_version != target.chunking_config_version
            or version.status not in {DocumentVersionStatus.INDEXED, DocumentVersionStatus.PUBLISHED}
            or (request.action is PublicationAction.ROLLBACK and version.status is not DocumentVersionStatus.PUBLISHED)
        ):
            raise PublicationRefusedError("Manifest member is missing, mismatched, deleted or not indexed")
    return PublicationPlan(
        request=request,
        actor_subject_id=decision.subject_id,
        alias_name=alias.alias_name,
        remove_physical_index=alias.physical_index_name,
        add_physical_index=target.physical_index_name,
        embedding=target.embedding,
        manifest_sha256=manifest.content_hash,
        prepared_at=now.astimezone(UTC),
    )
