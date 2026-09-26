"""Single source of truth for the PostgreSQL Row-Level-Security DDL.

Both the Alembic migration (``migrations/versions/..._enforce_rls_app_role.py``)
and the real-PostgreSQL integration test
(``tests/test_postgres_rls_enforcement.py``) build their DDL from the helpers
here, so the policies the test verifies are *byte-for-byte* the policies the
migration ships to production. There is no second, hand-copied definition that
could silently drift from the real one.

Model
-----
* ``bookmarks`` / ``searches`` / ``reports`` are **user-owned**: every row
  carries a nullable ``user_id`` (NULL == anonymous scope). They are protected
  by a per-command policy keyed on ``COALESCE(user_id, 0)`` matching the
  transaction-local ``app.current_user_id`` (see :mod:`app.database.rls`).
* ``search_results`` is **user-linked**: it has no ``user_id`` of its own, it is
  the searches<->articles junction. It is protected through its owning search
  (an ``EXISTS`` back into ``searches``), so a user can only ever touch result
  rows for searches they own.
* ``articles`` and ``users`` are **global/shared** and deliberately NOT under
  RLS: articles are shared read/write content for every user, and the ``users``
  table is the identity table the auth flow itself needs to read/insert before a
  subject is even established. Isolating those would break legitimate access
  (see Phase-11 report section E).

The owner of these tables is the migration/admin role. The runtime application
connects as a *non-owner* role with ``NOBYPASSRLS`` and, because we also set
``FORCE ROW LEVEL SECURITY``, that identity is constrained even if a deployment
were to (mis)connect as the owner.
"""
from __future__ import annotations

from typing import List

# User-owned tables whose rows carry a nullable ``user_id``.
OWNED_TABLES = ("bookmarks", "searches", "reports")
# Junction table protected through its owning ``searches`` row.
LINKED_TABLES = ("search_results",)
# Every table the RLS DDL is applied to.
PROTECTED_TABLES = OWNED_TABLES + LINKED_TABLES

# Reads the acting user id that app.database.rls sets transaction-local per
# request. An unset/empty value falls back to 0 == the anonymous scope, which
# matches rows whose user_id IS NULL (COALESCE(user_id, 0) == 0).
_CURRENT_UID = (
    "COALESCE(NULLIF(current_setting('app.current_user_id', true), ''), '0')::int"
)


def _owner_predicate(quoted_table: str) -> str:
    """RLS predicate matching a user-owned row to the acting user.

    ``quoted_table`` is only used to qualify the junction-table variant, where
    the ownership lives on the parent ``searches`` row rather than the row
    itself.
    """
    if quoted_table == '"search_results"':
        return (
            f"EXISTS (SELECT 1 FROM searches s WHERE s.id = {quoted_table}.search_id "
            f"AND {_CURRENT_UID} = COALESCE(s.user_id, 0))"
        )
    return f"{_CURRENT_UID} = COALESCE(user_id, 0)"


def enable_and_force(table: str) -> List[str]:
    """Statements that turn RLS on *and* bind the table owner too."""
    q = f'"{table}"'
    return [
        f'ALTER TABLE {q} ENABLE ROW LEVEL SECURITY;',
        f'ALTER TABLE {q} FORCE ROW LEVEL SECURITY;',
    ]


def create_policies(table: str) -> List[str]:
    """Explicit, per-command tenant-isolation policies for ``table``.

    SELECT/DELETE filter which rows are visible (``USING``); INSERT/UPDATE add
    ``WITH CHECK`` so a row cannot be created or moved to belong to someone
    else. All four share the same owner predicate, so write and read scopes can
    never disagree.
    """
    q = f'"{table}"'
    pred = _owner_predicate(q)
    return [
        f'DROP POLICY IF EXISTS "tenant_isolation" ON {q};',
        f'DROP POLICY IF EXISTS "rls_select_own" ON {q};',
        f'CREATE POLICY "rls_select_own" ON {q} FOR SELECT USING ({pred});',
        f'DROP POLICY IF EXISTS "rls_insert_own" ON {q};',
        f'CREATE POLICY "rls_insert_own" ON {q} FOR INSERT WITH CHECK ({pred});',
        f'DROP POLICY IF EXISTS "rls_update_own" ON {q};',
        f'CREATE POLICY "rls_update_own" ON {q} '
        f'FOR UPDATE USING ({pred}) WITH CHECK ({pred});',
        f'DROP POLICY IF EXISTS "rls_delete_own" ON {q};',
        f'CREATE POLICY "rls_delete_own" ON {q} FOR DELETE USING ({pred});',
    ]


def apply_rls() -> List[str]:
    """Full forward DDL: enable + force + explicit policies, every table."""
    stmts: List[str] = []
    for table in PROTECTED_TABLES:
        stmts.extend(enable_and_force(table))
        stmts.extend(create_policies(table))
    return stmts


def revert_rls() -> List[str]:
    """Roll back to the pre-enforcement state the earlier migration left.

    Drops the per-command policies and re-adds the original single
    ``tenant_isolation`` ``FOR ALL`` policy, then removes ``FORCE`` so the table
    owner is once again unconstrained - i.e. exactly revision ``c3d4e5f6a7b8``.
    """
    stmts: List[str] = []
    for table in PROTECTED_TABLES:
        q = f'"{table}"'
        for name in ("rls_select_own", "rls_insert_own", "rls_update_own", "rls_delete_own"):
            stmts.append(f'DROP POLICY IF EXISTS "{name}" ON {q};')
        # Restore the legacy catch-all policy from revision c3d4e5f6a7b8.
        pred = _owner_predicate(q)
        stmts.append(f'DROP POLICY IF EXISTS "tenant_isolation" ON {q};')
        stmts.append(
            f'CREATE POLICY "tenant_isolation" ON {q} FOR ALL USING ({pred}) WITH CHECK ({pred});'
        )
        stmts.append(f'ALTER TABLE {q} NO FORCE ROW LEVEL SECURITY;')
    return stmts


def grant_statements(app_role: str) -> List[str]:
    """Minimal runtime privileges for the non-owner application role."""
    role = _quote_ident(app_role)
    writable = ", ".join(f'"{t}"' for t in PROTECTED_TABLES)
    return [
        f'GRANT USAGE ON SCHEMA public TO {role};',
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON {writable} TO {role};',
        # Content + identity tables the app legitimately reads/writes for every
        # user (global, not tenant-isolated). ``users`` also needs DELETE so the
        # account-deletion (right-to-erasure) flow can remove the identity row;
        # it stays global/not-RLS-bound because auth must read it before any
        # subject exists.
        f'GRANT SELECT, INSERT, UPDATE ON "articles" TO {role};',
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON "users" TO {role};',
        # id sequences for the tables above (they are BIGSERIAL/SERIAL).
        f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role};',
    ]


def _quote_ident(ident: str) -> str:
    """Safely double-quote an SQL identifier (defends against injection)."""
    if any(c in ident for c in ('"', "\x00")):
        raise ValueError(f"invalid SQL identifier: {ident!r}")
    return '"' + ident.replace('"', '""') + '"'
