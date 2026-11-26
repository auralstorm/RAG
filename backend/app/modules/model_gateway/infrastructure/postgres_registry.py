"""PostgreSQL implementation of Provider registry facts and secret references."""

from uuid import UUID

from app.adapters.rbac import PostgresRbacRepository
from app.modules.model_gateway.domain.contracts import RegistryStatus, SecretReference
from app.modules.model_gateway.domain.registry import EncryptedSecretValue, ProviderPage, RegisteredProvider
from psycopg.types.json import Jsonb

PROVIDER_JSON = """
jsonb_build_object(
    'schema_version', '1.0',
    'id', p.id,
    'name', p.name,
    'provider_type', p.provider_type,
    'config_version', p.config_version,
    'status', p.status,
    'has_credential', p.credential_secret_id IS NOT NULL,
    'created_at', p.created_at,
    'updated_at', p.updated_at,
    'base_url', p.base_url,
    'credential_ref', CASE WHEN p.credential_secret_id IS NULL THEN NULL ELSE
        jsonb_build_object('secret_id', p.credential_secret_id, 'version', p.credential_version, 'environment', p.credential_environment) END,
    'proxy_ref', p.proxy_ref,
    'timeout_seconds', p.timeout_seconds,
    'remarks', p.remarks
)
"""


class PostgresProviderRepository(PostgresRbacRepository):
    async def providers(
        self,
        *,
        page: int,
        page_size: int,
        name: str | None,
        provider_type: str | None,
        status: RegistryStatus | None,
    ) -> ProviderPage:
        filters = "WHERE deleted_at IS NULL AND (%s::text IS NULL OR position(lower(%s) in lower(name)) > 0) "
        filters += "AND (%s::text IS NULL OR provider_type=%s) AND (%s::text IS NULL OR status=%s)"
        arguments = (
            name,
            name,
            provider_type,
            provider_type,
            status.value if status else None,
            status.value if status else None,
        )
        cursor = await self.connection.execute(
            f"""WITH filtered AS MATERIALIZED (SELECT p.* FROM providers p {filters}),
            page AS (
                SELECT {PROVIDER_JSON} AS item, p.created_at, p.id FROM filtered p
                ORDER BY p.created_at DESC,p.id LIMIT %s OFFSET %s
            )
            SELECT (SELECT count(*) FROM filtered),
                COALESCE((SELECT jsonb_agg(item ORDER BY created_at DESC,id) FROM page), '[]'::jsonb)
            """,
            (*arguments, page_size, (page - 1) * page_size),
        )
        row = await cursor.fetchone()
        assert row is not None
        return ProviderPage(tuple(RegisteredProvider.model_validate(item) for item in row[1]), int(row[0]))

    async def provider(self, provider_id: UUID, *, lock: bool = False) -> RegisteredProvider | None:
        cursor = await self.connection.execute(
            f"SELECT {PROVIDER_JSON} FROM providers p WHERE p.id=%s AND p.deleted_at IS NULL"
            + (" FOR UPDATE OF p" if lock else ""),
            (provider_id,),
        )
        row = await cursor.fetchone()
        return RegisteredProvider.model_validate(row[0]) if row else None

    async def create_provider(
        self,
        provider: RegisteredProvider,
        credential: EncryptedSecretValue | None,
        proxy: tuple[UUID, SecretReference, EncryptedSecretValue] | None,
    ) -> None:
        if provider.credential_ref is not None and credential is not None:
            await self._insert_secret(provider.credential_ref, credential)
        if proxy is not None:
            proxy_id, reference, value = proxy
            await self._insert_secret(reference, value)
            await self.connection.execute(
                "INSERT INTO provider_proxy_configs(proxy_id,secret_id,secret_version,secret_environment) "
                "VALUES(%s,%s,%s,%s)",
                (proxy_id, reference.secret_id, reference.version, reference.environment),
            )
        await self._insert_provider(provider)

    async def update_provider(
        self,
        provider: RegisteredProvider,
        *,
        credential: EncryptedSecretValue | None,
        proxy: tuple[UUID, SecretReference, EncryptedSecretValue] | None,
    ) -> None:
        if provider.credential_ref is not None and credential is not None:
            await self._insert_secret(provider.credential_ref, credential)
        if proxy is not None:
            proxy_id, reference, value = proxy
            await self._insert_secret(reference, value)
            await self.connection.execute(
                "INSERT INTO provider_proxy_configs(proxy_id,secret_id,secret_version,secret_environment) "
                "VALUES(%s,%s,%s,%s)",
                (proxy_id, reference.secret_id, reference.version, reference.environment),
            )
        await self._insert_provider(provider, update=True)

    async def archive_provider(self, provider: RegisteredProvider) -> None:
        # Preserve version and secret references. Future models can retain their FK to this tombstone.
        await self._insert_provider(provider, update=True)
        await self.connection.execute("UPDATE providers SET deleted_at=clock_timestamp() WHERE id=%s", (provider.id,))

    async def _insert_secret(self, reference: SecretReference, value: EncryptedSecretValue) -> None:
        await self.connection.execute(
            "INSERT INTO provider_secrets(secret_id,version,environment,key_version,ciphertext) VALUES(%s,%s,%s,%s,%s)",
            (
                reference.secret_id,
                reference.version,
                reference.environment,
                value.key_version,
                value.ciphertext,
            ),
        )

    async def _insert_provider(self, provider: RegisteredProvider, *, update: bool = False) -> None:
        if update:
            await self.connection.execute(
                "UPDATE providers SET name=%s,provider_type=%s,base_url=%s,proxy_ref=%s,timeout_seconds=%s,"
                "status=%s,config_version=%s,credential_secret_id=%s,credential_version=%s,"
                "credential_environment=%s,remarks=%s,updated_at=%s WHERE id=%s",
                self._provider_values(provider, include_id=False),
            )
        else:
            await self.connection.execute(
                "INSERT INTO providers(id,name,provider_type,base_url,proxy_ref,timeout_seconds,status,config_version,"
                "credential_secret_id,credential_version,credential_environment,remarks,created_at,updated_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                self._provider_values(provider, include_id=True),
            )

        await self.connection.execute(
            "INSERT INTO provider_config_versions(provider_id,config_version,configuration) VALUES(%s,%s,%s)",
            (provider.id, provider.config_version, Jsonb(provider.model_dump(mode="json"))),
        )

    @staticmethod
    def _provider_values(provider: RegisteredProvider, *, include_id: bool) -> tuple[object, ...]:
        reference = provider.credential_ref
        if include_id:
            return (
                provider.id,
                provider.name,
                provider.provider_type,
                str(provider.base_url),
                provider.proxy_ref,
                provider.timeout_seconds,
                provider.status.value,
                provider.config_version,
                reference.secret_id if reference is not None else None,
                reference.version if reference is not None else None,
                reference.environment if reference is not None else None,
                provider.remarks,
                provider.created_at,
                provider.updated_at,
            )
        return (
            provider.name,
            provider.provider_type,
            str(provider.base_url),
            provider.proxy_ref,
            provider.timeout_seconds,
            provider.status.value,
            provider.config_version,
            reference.secret_id if reference is not None else None,
            reference.version if reference is not None else None,
            reference.environment if reference is not None else None,
            provider.remarks,
            provider.updated_at,
            provider.id,
        )
