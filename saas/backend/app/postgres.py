"""Read and update OpenMU game parameters in tenant PostgreSQL.

Tables live in schema `config` (GameConfiguration, DropItemGroup,
MonsterSpawnArea, MiniGameDefinition). When no DSN is configured the API
still returns the payload shape with `source=defaults`.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from app.cluster import Cluster
from app.errors import DatabaseUnavailable
from app.models import (
    DropGroup,
    DropGroupUpdate,
    DropListResponse,
    EventListResponse,
    EventUpdate,
    GameEvent,
    GameRates,
    SpawnArea,
    SpawnListResponse,
    SpawnUpdate,
)
from app.settings import Settings, get_settings

LOGGER = logging.getLogger(__name__)


def required_env_message() -> str:
    return (
        "Tenant PostgreSQL is not configured. Set SAAS_PG_HOST, SAAS_PG_DATABASE, "
        "SAAS_PG_USER, SAAS_PG_PASSWORD (and optional SAAS_PG_PORT / SAAS_PG_DSN), "
        "or provide a postgres Service in the tenant namespace."
    )


class GameStore:
    def __init__(self, cluster: Cluster, settings: Settings | None = None) -> None:
        self.cluster = cluster
        self.settings = settings or get_settings()

    def dsn(self, namespace: str) -> str | None:
        discovered = self.cluster.discover_postgres(namespace) if self.cluster.connected else None
        if discovered and discovered.get("host") and discovered.get("password"):
            user = discovered.get("user") or self.settings.pg_user
            password = discovered["password"]
            host = discovered["host"]
            port = discovered.get("port") or str(self.settings.pg_port)
            database = discovered.get("database") or self.settings.pg_database
            return (
                f"host={host} port={port} dbname={database} user={user} "
                f"password={password} sslmode={self.settings.pg_sslmode} connect_timeout=5"
            )
        override = self.settings.pg_dsn_for_namespace(namespace)
        if override:
            return override
        if self.settings.pg_host:
            password = self.settings.pg_password or ""
            return (
                f"host={self.settings.pg_host} port={self.settings.pg_port} "
                f"dbname={self.settings.pg_database} user={self.settings.pg_user} "
                f"password={password} sslmode={self.settings.pg_sslmode} connect_timeout=5"
            )
        return None

    @contextmanager
    def _connect(self, namespace: str) -> Iterator[psycopg.Connection]:
        dsn = self.dsn(namespace)
        if not dsn:
            raise DatabaseUnavailable(required_env_message())
        try:
            conn = psycopg.connect(dsn, row_factory=dict_row)
        except psycopg.Error as exc:
            raise DatabaseUnavailable(f"Could not connect to tenant PostgreSQL: {exc}") from exc
        try:
            yield conn
            conn.commit()
        except DatabaseUnavailable:
            conn.rollback()
            raise
        except psycopg.Error as exc:
            conn.rollback()
            raise DatabaseUnavailable(f"PostgreSQL query failed: {exc}") from exc
        finally:
            conn.close()

    def get_rates(self, namespace: str) -> GameRates:
        dsn = self.dsn(namespace)
        if not dsn:
            return GameRates(database_error=required_env_message())
        try:
            with self._connect(namespace) as conn:
                row = conn.execute(
                    """
                    SELECT "ExperienceRate", "MasterExperienceRate",
                           "MaximumItemOptionLevelDrop", "ExcellentItemDropLevelDelta",
                           "ShouldDropMoney",
                           EXTRACT(EPOCH FROM "ItemDropDuration") AS drop_secs
                    FROM config."GameConfiguration"
                    LIMIT 1
                    """
                ).fetchone()
        except DatabaseUnavailable as exc:
            return GameRates(database_error=_error_text(exc))
        if not row:
            return GameRates(source="postgresql", persisted=False, database_error="GameConfiguration is empty.")
        return GameRates(
            experience_rate=row["ExperienceRate"] or 1.0,
            master_experience_rate=row["MasterExperienceRate"] or 1.0,
            maximum_item_option_level_drop=int(row["MaximumItemOptionLevelDrop"] or 0),
            excellent_item_drop_level_delta=int(row["ExcellentItemDropLevelDelta"] or 0),
            should_drop_money=bool(row["ShouldDropMoney"]),
            item_drop_duration_seconds=int(row["drop_secs"] or 60),
            source="postgresql",
            persisted=True,
        )

    def put_rates(self, namespace: str, rates: GameRates) -> GameRates:
        with self._connect(namespace) as conn:
            row = conn.execute(
                """
                UPDATE config."GameConfiguration"
                SET "ExperienceRate" = %(experience_rate)s,
                    "MasterExperienceRate" = %(master_experience_rate)s,
                    "MaximumItemOptionLevelDrop" = %(maximum_item_option_level_drop)s,
                    "ExcellentItemDropLevelDelta" = %(excellent_item_drop_level_delta)s,
                    "ShouldDropMoney" = %(should_drop_money)s,
                    "ItemDropDuration" = make_interval(secs => %(item_drop_duration_seconds)s)
                RETURNING "ExperienceRate", "MasterExperienceRate",
                          "MaximumItemOptionLevelDrop", "ExcellentItemDropLevelDelta",
                          "ShouldDropMoney",
                          EXTRACT(EPOCH FROM "ItemDropDuration") AS drop_secs
                """,
                rates.model_dump(),
            ).fetchone()
        if not row:
            raise DatabaseUnavailable("UPDATE hit 0 GameConfiguration rows.")
        return GameRates(
            experience_rate=row["ExperienceRate"],
            master_experience_rate=row["MasterExperienceRate"],
            maximum_item_option_level_drop=int(row["MaximumItemOptionLevelDrop"]),
            excellent_item_drop_level_delta=int(row["ExcellentItemDropLevelDelta"]),
            should_drop_money=bool(row["ShouldDropMoney"]),
            item_drop_duration_seconds=int(row["drop_secs"] or 60),
            source="postgresql",
            persisted=True,
        )

    def list_drops(self, namespace: str) -> DropListResponse:
        if not self.dsn(namespace):
            return DropListResponse(database_error=required_env_message())
        try:
            with self._connect(namespace) as conn:
                rows = conn.execute(
                    """
                    SELECT "Id"::text AS id, "Description" AS description, "Chance" AS chance,
                           "MinimumMonsterLevel" AS minimum_monster_level,
                           "MaximumMonsterLevel" AS maximum_monster_level,
                           "ItemType" AS item_type
                    FROM config."DropItemGroup"
                    ORDER BY "Chance" DESC
                    LIMIT 200
                    """
                ).fetchall()
        except DatabaseUnavailable as exc:
            return DropListResponse(database_error=_error_text(exc))
        return DropListResponse(items=[DropGroup(**_stringify(row)) for row in rows], source="postgresql")

    def update_drop(self, namespace: str, drop_id: str, update: DropGroupUpdate) -> DropGroup:
        with self._connect(namespace) as conn:
            row = conn.execute(
                """
                UPDATE config."DropItemGroup"
                SET "Chance" = %(chance)s,
                    "MinimumMonsterLevel" = %(minimum_monster_level)s,
                    "MaximumMonsterLevel" = %(maximum_monster_level)s
                WHERE "Id" = %(id)s::uuid
                RETURNING "Id"::text AS id, "Description" AS description, "Chance" AS chance,
                          "MinimumMonsterLevel" AS minimum_monster_level,
                          "MaximumMonsterLevel" AS maximum_monster_level,
                          "ItemType" AS item_type
                """,
                {"id": drop_id, **update.model_dump()},
            ).fetchone()
        if not row:
            raise DatabaseUnavailable(f"DropItemGroup {drop_id} was not found.")
        return DropGroup(**_stringify(row))

    def list_spawns(self, namespace: str) -> SpawnListResponse:
        if not self.dsn(namespace):
            return SpawnListResponse(database_error=required_env_message())
        try:
            with self._connect(namespace) as conn:
                rows = conn.execute(
                    """
                    SELECT s."Id"::text AS id,
                           m."Designation" AS monster,
                           map."Name" AS map,
                           s."Quantity" AS quantity,
                           s."X1" AS x1, s."Y1" AS y1, s."X2" AS x2, s."Y2" AS y2
                    FROM config."MonsterSpawnArea" s
                    LEFT JOIN config."MonsterDefinition" m ON m."Id" = s."MonsterDefinitionId"
                    LEFT JOIN config."GameMapDefinition" map ON map."Id" = s."GameMapId"
                    WHERE s."SpawnTrigger" = 0
                    ORDER BY map."Name", m."Designation"
                    LIMIT 300
                    """
                ).fetchall()
        except DatabaseUnavailable as exc:
            return SpawnListResponse(database_error=_error_text(exc))
        return SpawnListResponse(items=[SpawnArea(**row) for row in rows], source="postgresql")

    def update_spawn(self, namespace: str, spawn_id: str, update: SpawnUpdate) -> SpawnArea:
        fields = update.model_dump(exclude_none=True)
        assignments = ["\"Quantity\" = %(quantity)s"]
        params: dict[str, Any] = {"id": spawn_id, "quantity": update.quantity}
        for column in ("x1", "y1", "x2", "y2"):
            if column in fields:
                assignments.append(f'"{column.upper()}" = %({column})s')
                params[column] = fields[column]
        sql = f"""
            UPDATE config."MonsterSpawnArea"
            SET {", ".join(assignments)}
            WHERE "Id" = %(id)s::uuid
            RETURNING "Id"::text AS id, "Quantity" AS quantity,
                      "X1" AS x1, "Y1" AS y1, "X2" AS x2, "Y2" AS y2
        """
        with self._connect(namespace) as conn:
            row = conn.execute(sql, params).fetchone()
            if not row:
                raise DatabaseUnavailable(f"MonsterSpawnArea {spawn_id} was not found.")
            extra = conn.execute(
                """
                SELECT m."Designation" AS monster, map."Name" AS map
                FROM config."MonsterSpawnArea" s
                LEFT JOIN config."MonsterDefinition" m ON m."Id" = s."MonsterDefinitionId"
                LEFT JOIN config."GameMapDefinition" map ON map."Id" = s."GameMapId"
                WHERE s."Id" = %(id)s::uuid
                """,
                {"id": spawn_id},
            ).fetchone()
        payload = dict(row)
        if extra:
            payload.update(extra)
        payload.setdefault("monster", None)
        payload.setdefault("map", None)
        return SpawnArea(**payload)

    def list_events(self, namespace: str) -> EventListResponse:
        if not self.dsn(namespace):
            return EventListResponse(database_error=required_env_message())
        try:
            with self._connect(namespace) as conn:
                rows = conn.execute(
                    """
                    SELECT "Id"::text AS id, "Name" AS name, "GameLevel" AS game_level,
                           "EntranceFee" AS entrance_fee,
                           "MaximumPlayerCount" AS maximum_player_count,
                           "MinimumCharacterLevel" AS minimum_character_level,
                           "MaximumCharacterLevel" AS maximum_character_level,
                           "AllowParty" AS allow_party
                    FROM config."MiniGameDefinition"
                    ORDER BY "Name", "GameLevel"
                    LIMIT 100
                    """
                ).fetchall()
        except DatabaseUnavailable as exc:
            return EventListResponse(database_error=_error_text(exc))
        return EventListResponse(items=[GameEvent(**_stringify(row)) for row in rows], source="postgresql")

    def update_event(self, namespace: str, event_id: str, update: EventUpdate) -> GameEvent:
        fields = update.model_dump(exclude_none=True)
        if not fields:
            raise DatabaseUnavailable("No event fields to update.")
        column_map = {
            "entrance_fee": "EntranceFee",
            "maximum_player_count": "MaximumPlayerCount",
            "minimum_character_level": "MinimumCharacterLevel",
            "maximum_character_level": "MaximumCharacterLevel",
            "allow_party": "AllowParty",
        }
        assignments = [f'"{column_map[k]}" = %({k})s' for k in fields]
        params = {"id": event_id, **fields}
        sql = f"""
            UPDATE config."MiniGameDefinition"
            SET {", ".join(assignments)}
            WHERE "Id" = %(id)s::uuid
            RETURNING "Id"::text AS id, "Name" AS name, "GameLevel" AS game_level,
                      "EntranceFee" AS entrance_fee,
                      "MaximumPlayerCount" AS maximum_player_count,
                      "MinimumCharacterLevel" AS minimum_character_level,
                      "MaximumCharacterLevel" AS maximum_character_level,
                      "AllowParty" AS allow_party
        """
        with self._connect(namespace) as conn:
            row = conn.execute(sql, params).fetchone()
        if not row:
            raise DatabaseUnavailable(f"MiniGameDefinition {event_id} was not found.")
        return GameEvent(**_stringify(row))


def _error_text(exc: DatabaseUnavailable) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        return str(detail.get("error") or detail)
    return str(detail)


def _stringify(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("description", "name"):
        if key in out and out[key] is not None:
            out[key] = str(out[key])
    return out
