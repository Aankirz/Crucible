"""Registry of the bundled text-to-SQL databases the UI can pick from.

This is the single source of truth behind ``GET /databases`` and ``GET /schema``.
It wraps the self-contained dataset modules (each exposing SCHEMA / TRAIN / TEST /
``build_db``) behind three small functions the server calls:

  * :func:`build_db`    -> materialize the SQLite file, return its path.
  * :func:`get_items`   -> the ``(train, test)`` EvalItem splits.
  * :func:`get_schema`  -> the CREATE TABLE DDL string.

``world`` is the deterministic instant demo (mode="demo"); the three Spider-style
databases run the real Gemini loop (mode="live").
"""
from __future__ import annotations

from dataclasses import dataclass, field

from crucible.datasets import concert_singer, ecommerce, university, world_bundle
from crucible.types import EvalItem


@dataclass(frozen=True)
class DatabaseDescriptor:
    """One catalog entry, surfaced verbatim by ``GET /databases``."""

    id: str
    name: str
    domain: str
    tables: tuple[str, ...]
    num_questions: int
    mode: str           # "demo" = deterministic instant; "live" = real Gemini
    blurb: str

    def to_dict(self) -> dict:
        """Serialize to the exact JSON shape the frontend contract expects."""
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "tables": list(self.tables),
            "num_questions": self.num_questions,
            "mode": self.mode,
            "blurb": self.blurb,
        }


@dataclass(frozen=True)
class _DatasetEntry:
    """Internal binding of a descriptor to its dataset module callables."""

    descriptor: DatabaseDescriptor
    schema: str
    train: tuple[EvalItem, ...]
    test: tuple[EvalItem, ...]
    build: object       # Callable[[str | None], str]


def _entry(*, db_id: str, name: str, domain: str, tables: tuple[str, ...],
           mode: str, blurb: str, schema: str, build,
           train, test) -> _DatasetEntry:
    """Assemble a registry entry, computing num_questions from the splits."""
    train_t = tuple(train)
    test_t = tuple(test)
    descriptor = DatabaseDescriptor(
        id=db_id,
        name=name,
        domain=domain,
        tables=tables,
        num_questions=len(train_t) + len(test_t),
        mode=mode,
        blurb=blurb,
    )
    return _DatasetEntry(descriptor=descriptor, schema=schema,
                         train=train_t, test=test_t, build=build)


# Order here is the order the UI shows in the dropdown: demo first, then live.
_REGISTRY: dict[str, _DatasetEntry] = {}


def _register(entry: _DatasetEntry) -> None:
    _REGISTRY[entry.descriptor.id] = entry


_register(_entry(
    db_id=world_bundle.WORLD_DB_ID,
    name="World — countries, cities, languages",
    domain="geography",
    tables=("country", "city", "countrylanguage"),
    mode="demo",
    blurb="A compact geography database. Instant deterministic demo (no LLM).",
    schema=world_bundle.WORLD_SCHEMA,
    build=world_bundle.build_world_db,
    train=world_bundle.WORLD_TRAIN,
    test=world_bundle.WORLD_TEST,
))

_register(_entry(
    db_id=concert_singer.DB_ID,
    name="Concert Singer — singers, concerts, stadiums",
    domain="entertainment",
    tables=("stadium", "singer", "concert", "singer_in_concert"),
    mode="live",
    blurb="Singers performing in concerts across stadiums. Real Gemini loop.",
    schema=concert_singer.SCHEMA,
    build=concert_singer.build_db,
    train=concert_singer.TRAIN,
    test=concert_singer.TEST,
))

_register(_entry(
    db_id=university.DB_ID,
    name="University — students, courses, enrollments",
    domain="education",
    tables=("department", "student", "course", "enrollment"),
    mode="live",
    blurb="A student-records database with departments and enrollments. Real Gemini loop.",
    schema=university.SCHEMA,
    build=university.build_db,
    train=university.TRAIN,
    test=university.TEST,
))

_register(_entry(
    db_id=ecommerce.DB_ID,
    name="E-commerce — customers, orders, products",
    domain="retail",
    tables=("customer", "product", "orders", "order_item"),
    mode="live",
    blurb="An online store with customers, products and orders. Real Gemini loop.",
    schema=ecommerce.SCHEMA,
    build=ecommerce.build_db,
    train=ecommerce.TRAIN,
    test=ecommerce.TEST,
))


def list_databases() -> list[DatabaseDescriptor]:
    """Return all catalog descriptors in dropdown order (demo first)."""
    return [entry.descriptor for entry in _REGISTRY.values()]


def catalog_payload() -> dict:
    """Return the exact JSON body for ``GET /databases``."""
    return {"databases": [d.to_dict() for d in list_databases()]}


def is_known(db_id: str) -> bool:
    """True when ``db_id`` is a bundled database."""
    return db_id in _REGISTRY


def get_descriptor(db_id: str) -> DatabaseDescriptor:
    """Return the descriptor for ``db_id`` (raises KeyError if unknown)."""
    return _REGISTRY[db_id].descriptor


def get_mode(db_id: str) -> str:
    """Return "demo" or "live" for ``db_id`` (raises KeyError if unknown)."""
    return _REGISTRY[db_id].descriptor.mode


def build_db(db_id: str, target_dir: str | None = None) -> str:
    """Materialize the SQLite file for ``db_id`` and return its path."""
    return _REGISTRY[db_id].build(target_dir)


def get_items(db_id: str) -> tuple[list[EvalItem], list[EvalItem]]:
    """Return the ``(train, test)`` EvalItem splits for ``db_id``."""
    entry = _REGISTRY[db_id]
    return list(entry.train), list(entry.test)


def get_schema(db_id: str) -> str:
    """Return the CREATE TABLE DDL string for ``db_id``."""
    return _REGISTRY[db_id].schema.strip()
