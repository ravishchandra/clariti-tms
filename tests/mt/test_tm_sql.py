"""Unit tests for the pgvector raw-SQL literal helpers in ``app.mt.tm``.

These helpers exist because asyncpg + pgvector force literal interpolation
(see ``app/mt/tm.py`` docstring and the project memory entry
``project_pgvector_asyncpg.md``). The helpers encapsulate the inlining behind
a typed "internal-values-only" contract; this module verifies they:

* produce the exact pgvector / Postgres-array string shapes the rest of the
  raw SQL depends on, and
* reject inputs that violate the typed contract — runtime ``TypeError`` so
  a refactor can't accidentally widen the trust boundary.
"""

from __future__ import annotations

import uuid

import pytest

from app.mt.tm import _uuid_array_exclude_clause, _vector_literal

# ---------------------------------------------------------------------------
# _vector_literal
# ---------------------------------------------------------------------------


class TestVectorLiteral:
    def test_single_element(self) -> None:
        assert _vector_literal([0.5]) == "'[0.5]'"

    def test_multiple_floats(self) -> None:
        result = _vector_literal([0.1, 0.2, 0.3])
        assert result == "'[0.1,0.2,0.3]'"

    def test_int_values_coerced_to_float(self) -> None:
        # The SQL accepts integer-shaped floats; we always emit float repr
        # so the literal is unambiguous to pgvector.
        result = _vector_literal([1, 2, 3])
        assert result == "'[1.0,2.0,3.0]'"

    def test_negative_values(self) -> None:
        result = _vector_literal([-0.5, 0.0, 0.5])
        assert result == "'[-0.5,0.0,0.5]'"

    def test_uses_square_brackets_not_curly(self) -> None:
        # pgvector quirk: '{...}' format is for Postgres native arrays and
        # raises InvalidTextRepresentationError on the ``::vector`` cast.
        result = _vector_literal([0.1, 0.2])
        assert result.startswith("'[")
        assert result.endswith("]'")
        assert "{" not in result
        assert "}" not in result

    def test_empty_list_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            _vector_literal([])

    def test_non_list_raises(self) -> None:
        with pytest.raises(TypeError, match="list"):
            _vector_literal("0.1,0.2")  # type: ignore[arg-type]

    def test_non_numeric_element_raises(self) -> None:
        with pytest.raises(TypeError, match="int or float"):
            _vector_literal([0.1, "0.2"])  # type: ignore[list-item]

    def test_none_element_raises(self) -> None:
        with pytest.raises(TypeError, match="int or float"):
            _vector_literal([0.1, None])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# _uuid_array_exclude_clause
# ---------------------------------------------------------------------------


class TestUuidArrayExcludeClause:
    def test_empty_list_returns_empty_string(self) -> None:
        # Sentinel — splices into the SQL as a no-op; the surrounding
        # template must be tolerant of an empty insertion point.
        assert _uuid_array_exclude_clause([]) == ""

    def test_single_uuid(self) -> None:
        u = uuid.UUID("12345678-1234-5678-1234-567812345678")
        result = _uuid_array_exclude_clause([u])
        assert result == (
            "AND source_key_id != ALL(ARRAY['12345678-1234-5678-1234-567812345678']::uuid[])"
        )

    def test_multiple_uuids(self) -> None:
        u1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
        u2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
        result = _uuid_array_exclude_clause([u1, u2])
        assert "ARRAY[" in result
        assert "'11111111-1111-1111-1111-111111111111'" in result
        assert "'22222222-2222-2222-2222-222222222222'" in result
        assert result.endswith("]::uuid[])")
        # Order preserved.
        assert result.index("11111111") < result.index("22222222")

    def test_non_list_raises(self) -> None:
        with pytest.raises(TypeError, match="list"):
            _uuid_array_exclude_clause(uuid.uuid4())  # type: ignore[arg-type]

    def test_string_uuid_rejected(self) -> None:
        # The trust boundary lives at the type level — a stringified UUID
        # from an external source is exactly what we don't want to accept.
        with pytest.raises(TypeError, match="uuid.UUID"):
            _uuid_array_exclude_clause(
                ["12345678-1234-5678-1234-567812345678"]  # type: ignore[list-item]
            )

    def test_mixed_uuid_and_string_rejected(self) -> None:
        u = uuid.uuid4()
        with pytest.raises(TypeError, match="uuid.UUID"):
            _uuid_array_exclude_clause([u, "not-a-uuid"])  # type: ignore[list-item]

    def test_int_element_rejected(self) -> None:
        with pytest.raises(TypeError, match="uuid.UUID"):
            _uuid_array_exclude_clause([42])  # type: ignore[list-item]
