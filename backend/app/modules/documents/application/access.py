"""KB permission and current document restrictions intersect; publication status is not ACL."""

from datetime import datetime

from app.modules.documents.domain.contracts import (
    DocumentAccessPolicy,
    DocumentStatus,
    DocumentVersionRef,
    DocumentVersionStatus,
)
from app.modules.knowledge_base.domain.contracts import KnowledgeBaseStatus
from app.modules.policy.application.authorization import authorize
from app.modules.policy.domain.contracts import AccessContext, AuthorizationRequest, AuthorizationSnapshot
from app.modules.search.domain.contracts import IndexVersionStatus, PublishedDocumentSnapshot


def require_published_document(
    snapshot: PublishedDocumentSnapshot,
    document_policy: DocumentAccessPolicy,
    context: AccessContext | None,
    authorization: AuthorizationSnapshot,
    *,
    now: datetime,
) -> DocumentVersionRef:
    """Return a current readable version reference; caller owns fresh facts and private IO.

    This is for online retrieval/citation/source access. Administrative prepublication
    inspection is a separate authorized use case; an INDEXED version is not online.
    """
    kb, document, version, index = snapshot.kb, snapshot.document, snapshot.version, snapshot.index
    decision = authorize(
        AuthorizationRequest(permission_code="kb.read", purpose=authorization.purpose, kb_id=kb.id),
        context,
        authorization,
        now=now,
    )
    if not decision.allowed or decision.subject_id is None:
        raise PermissionError("Published document access requires current KB permission")
    if now < max(kb.updated_at, document.updated_at, version.updated_at, index.updated_at):
        raise PermissionError("Published document facts cannot come from the future")
    if (
        kb.status is not KnowledgeBaseStatus.ACTIVE
        or document.status is not DocumentStatus.ACTIVE
        or document.kb_id != kb.id
        or version.kb_id != kb.id
        or version.document_id != document.id
        or version.document_version > document.current_version
        or version.status is not DocumentVersionStatus.PUBLISHED
        or version.pipeline_version != index.pipeline_version
        or version.chunking_config_version != index.chunking_config_version
    ):
        raise PermissionError("Document/version is not a current readable resource")
    alias, manifest = snapshot.alias, snapshot.manifest
    if (
        index.status is not IndexVersionStatus.ACTIVE
        or index.id != kb.active_index_version_id
        or index.kb_id != kb.id
        or alias.kb_id != kb.id
        or alias.active_index_version_id != index.id
        or alias.alias_name != index.alias_name
        or alias.physical_index_name != index.physical_index_name
        or manifest.kb_id != kb.id
        or manifest.index_version_id != index.id
        or manifest.content_hash != index.manifest_sha256
        or index.validation is None
        or index.validation.actual_document_count != len(manifest.documents)
    ):
        raise PermissionError("Active index/alias/manifest facts do not agree")
    reference = DocumentVersionRef(
        document_version_id=version.document_version_id,
        document_id=document.id,
        kb_id=kb.id,
        document_version=version.document_version,
    )
    if reference not in manifest.documents:
        raise PermissionError("Document version is not a member of the active index")
    if (
        document_policy.document_id != document.id
        or document_policy.kb_id != kb.id
        or document_policy.acl_policy_id != document.acl_policy_id
        or document_policy.policy_version != authorization.policy_version
    ):
        raise PermissionError("Current document policy is missing or inconsistent")
    if (
        document_policy.allowed_subject_ids is not None
        and decision.subject_id not in document_policy.allowed_subject_ids
    ):
        raise PermissionError("Document restriction does not authorize this subject")
    return reference
