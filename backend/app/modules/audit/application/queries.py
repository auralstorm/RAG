"""Authorize audit reads against current Admin facts in the same database transaction."""

from app.modules.audit.domain.queries import AuditCriteria, AuditPage, AuditTransaction
from app.modules.policy.application.enforcement import PolicyEnforcer


class AuditService:
    def __init__(self, transactions: AuditTransaction, enforcer: PolicyEnforcer) -> None:
        self.transactions = transactions
        self.enforcer = enforcer

    async def search(self, token: str, criteria: AuditCriteria, *, page: int, page_size: int) -> AuditPage:
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("Audit search requires bounded pagination")
        async with self.transactions() as repository:
            authority = await self.enforcer.load(
                repository, "admin", token, await repository.policy_version(write=False)
            )
            self.enforcer.require(authority, "audit.read")
            result = await repository.search_audit(criteria, limit=page_size, offset=(page - 1) * page_size)
            # A slow query must not return sensitive audit facts after the access deadline.
            self.enforcer.require(authority, "audit.read")
            return result
