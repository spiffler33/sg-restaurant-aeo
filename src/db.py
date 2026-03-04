"""SQLite database operations for the SG Restaurant AEO project.

Uses a single data/aeo.db file. All structured data flows through here:
discovery prompts, raw query results, and parsed restaurant mentions.

Design: We store JSON-serialized lists (cuisine_tags, vibe_tags, etc.)
as TEXT columns in SQLite. This keeps the schema simple while preserving
the full structure. For analysis, we deserialize back to Pydantic models.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import (
    CanonicalRestaurant,
    DiscoveryPrompt,
    ModelName,
    ParsedResponse,
    PriceIndicator,
    QueryResult,
    RestaurantMention,
    Sentiment,
)

DB_PATH = Path(__file__).parent.parent / "data" / "aeo.db"


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Get a SQLite connection with row factory enabled."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't exist."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS discovery_prompts (
            id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            dimension TEXT NOT NULL,
            category TEXT NOT NULL,
            specificity TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS query_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_id TEXT NOT NULL REFERENCES discovery_prompts(id),
            model_name TEXT NOT NULL,
            search_enabled BOOLEAN NOT NULL,
            raw_response TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            latency_ms INTEGER,
            token_usage INTEGER
        );

        CREATE TABLE IF NOT EXISTS parsed_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_result_id INTEGER NOT NULL REFERENCES query_results(id),
            parse_model TEXT NOT NULL,
            parsed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS restaurant_mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parsed_response_id INTEGER NOT NULL REFERENCES parsed_responses(id),
            restaurant_name TEXT NOT NULL,
            rank_position INTEGER NOT NULL,
            neighbourhood TEXT,
            cuisine_tags TEXT NOT NULL DEFAULT '[]',
            vibe_tags TEXT NOT NULL DEFAULT '[]',
            price_indicator TEXT NOT NULL DEFAULT 'unknown',
            descriptors TEXT NOT NULL DEFAULT '[]',
            sentiment TEXT NOT NULL DEFAULT 'positive',
            is_primary_recommendation BOOLEAN NOT NULL DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_query_results_prompt
            ON query_results(prompt_id);
        CREATE INDEX IF NOT EXISTS idx_query_results_model
            ON query_results(model_name);
        CREATE INDEX IF NOT EXISTS idx_restaurant_mentions_name
            ON restaurant_mentions(restaurant_name);
        CREATE INDEX IF NOT EXISTS idx_restaurant_mentions_parsed
            ON restaurant_mentions(parsed_response_id);

        CREATE TABLE IF NOT EXISTS canonical_restaurants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT NOT NULL UNIQUE,
            variant_names TEXT NOT NULL DEFAULT '[]',
            total_mentions INTEGER NOT NULL DEFAULT 0,
            model_count INTEGER NOT NULL DEFAULT 0,
            models_mentioning TEXT NOT NULL DEFAULT '[]'
        );

        CREATE INDEX IF NOT EXISTS idx_canonical_restaurants_name
            ON canonical_restaurants(canonical_name);
        """
    )
    # Add canonical_id column to restaurant_mentions if it doesn't exist
    try:
        conn.execute(
            "ALTER TABLE restaurant_mentions ADD COLUMN canonical_id INTEGER REFERENCES canonical_restaurants(id)"
        )
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add stability test columns to query_results if they don't exist
    for col_sql in [
        "ALTER TABLE query_results ADD COLUMN is_stability_test BOOLEAN NOT NULL DEFAULT 0",
        "ALTER TABLE query_results ADD COLUMN run_number INTEGER",
    ]:
        try:
            conn.execute(col_sql)
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.commit()


def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Initialize the database: create connection and tables."""
    conn = get_connection(db_path)
    create_tables(conn)
    return conn


# ---------------------------------------------------------------------------
# Insert operations
# ---------------------------------------------------------------------------


def insert_prompt(conn: sqlite3.Connection, prompt: DiscoveryPrompt) -> None:
    """Insert a discovery prompt (upsert on conflict)."""
    conn.execute(
        """
        INSERT OR REPLACE INTO discovery_prompts (id, text, dimension, category, specificity)
        VALUES (?, ?, ?, ?, ?)
        """,
        (prompt.id, prompt.text, prompt.dimension.value, prompt.category, prompt.specificity.value),
    )
    conn.commit()


def insert_prompts_bulk(conn: sqlite3.Connection, prompts: list[DiscoveryPrompt]) -> int:
    """Insert multiple prompts at once. Returns count inserted."""
    conn.executemany(
        """
        INSERT OR REPLACE INTO discovery_prompts (id, text, dimension, category, specificity)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (p.id, p.text, p.dimension.value, p.category, p.specificity.value)
            for p in prompts
        ],
    )
    conn.commit()
    return len(prompts)


def insert_query_result(conn: sqlite3.Connection, result: QueryResult) -> int:
    """Insert a query result. Returns the new row ID."""
    cursor = conn.execute(
        """
        INSERT INTO query_results
            (prompt_id, model_name, search_enabled, raw_response, timestamp, latency_ms, token_usage)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result.prompt_id,
            result.model_name.value,
            result.search_enabled,
            result.raw_response,
            result.timestamp.isoformat(),
            result.latency_ms,
            result.token_usage,
        ),
    )
    conn.commit()
    return cursor.lastrowid  # type: ignore[return-value]


def insert_stability_result(
    conn: sqlite3.Connection, result: QueryResult, run_number: int
) -> int:
    """Insert a stability test query result with run metadata. Returns the new row ID."""
    cursor = conn.execute(
        """
        INSERT INTO query_results
            (prompt_id, model_name, search_enabled, raw_response, timestamp,
             latency_ms, token_usage, is_stability_test, run_number)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            result.prompt_id,
            result.model_name.value,
            result.search_enabled,
            result.raw_response,
            result.timestamp.isoformat(),
            result.latency_ms,
            result.token_usage,
            run_number,
        ),
    )
    conn.commit()
    return cursor.lastrowid  # type: ignore[return-value]


def get_stability_results(conn: sqlite3.Connection) -> list[dict]:
    """Get all stability test query results as dicts."""
    rows = conn.execute(
        """
        SELECT id, prompt_id, model_name, search_enabled, raw_response,
               timestamp, latency_ms, token_usage, run_number
        FROM query_results
        WHERE is_stability_test = 1
        ORDER BY prompt_id, model_name, search_enabled, run_number
        """
    ).fetchall()
    return [dict(r) for r in rows]


def insert_parsed_response(conn: sqlite3.Connection, parsed: ParsedResponse) -> int:
    """Insert a parsed response and all its restaurant mentions. Returns the parsed_response ID."""
    cursor = conn.execute(
        """
        INSERT INTO parsed_responses (query_result_id, parse_model, parsed_at)
        VALUES (?, ?, ?)
        """,
        (parsed.query_result_id, parsed.parse_model, parsed.parsed_at.isoformat()),
    )
    parsed_id = cursor.lastrowid

    for mention in parsed.restaurants:
        conn.execute(
            """
            INSERT INTO restaurant_mentions
                (parsed_response_id, restaurant_name, rank_position, neighbourhood,
                 cuisine_tags, vibe_tags, price_indicator, descriptors,
                 sentiment, is_primary_recommendation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parsed_id,
                mention.restaurant_name,
                mention.rank_position,
                mention.neighbourhood,
                json.dumps(mention.cuisine_tags),
                json.dumps(mention.vibe_tags),
                mention.price_indicator.value,
                json.dumps(mention.descriptors),
                mention.sentiment.value,
                mention.is_primary_recommendation,
            ),
        )

    conn.commit()
    return parsed_id  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Query operations
# ---------------------------------------------------------------------------


def get_all_prompts(conn: sqlite3.Connection) -> list[DiscoveryPrompt]:
    """Retrieve all discovery prompts."""
    rows = conn.execute("SELECT * FROM discovery_prompts ORDER BY id").fetchall()
    return [
        DiscoveryPrompt(
            id=r["id"],
            text=r["text"],
            dimension=r["dimension"],
            category=r["category"],
            specificity=r["specificity"],
        )
        for r in rows
    ]


def get_query_results(
    conn: sqlite3.Connection,
    prompt_id: Optional[str] = None,
    model_name: Optional[str] = None,
) -> list[QueryResult]:
    """Retrieve query results with optional filters."""
    query = "SELECT * FROM query_results WHERE 1=1"
    params: list = []

    if prompt_id:
        query += " AND prompt_id = ?"
        params.append(prompt_id)
    if model_name:
        query += " AND model_name = ?"
        params.append(model_name)

    query += " ORDER BY timestamp DESC"
    rows = conn.execute(query, params).fetchall()

    return [
        QueryResult(
            id=r["id"],
            prompt_id=r["prompt_id"],
            model_name=ModelName(r["model_name"]),
            search_enabled=bool(r["search_enabled"]),
            raw_response=r["raw_response"],
            timestamp=datetime.fromisoformat(r["timestamp"]),
            latency_ms=r["latency_ms"],
            token_usage=r["token_usage"],
        )
        for r in rows
    ]


def get_restaurant_mentions(
    conn: sqlite3.Connection,
    restaurant_name: Optional[str] = None,
) -> list[dict]:
    """Retrieve restaurant mentions with parsed response and query metadata joined.

    Returns dicts with mention data plus model_name and prompt_id for analysis.
    """
    query = """
        SELECT
            rm.*,
            pr.query_result_id,
            qr.prompt_id,
            qr.model_name,
            qr.search_enabled
        FROM restaurant_mentions rm
        JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
        JOIN query_results qr ON pr.query_result_id = qr.id
    """
    params: list = []

    if restaurant_name:
        query += " WHERE rm.restaurant_name LIKE ?"
        params.append(f"%{restaurant_name}%")

    query += " ORDER BY rm.restaurant_name, rm.rank_position"
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_mention_counts(conn: sqlite3.Connection) -> list[dict]:
    """Get restaurant mention counts across all models. Core analysis query."""
    rows = conn.execute(
        """
        SELECT
            rm.restaurant_name,
            COUNT(*) as total_mentions,
            COUNT(DISTINCT qr.model_name) as model_count,
            AVG(rm.rank_position) as avg_rank,
            SUM(rm.is_primary_recommendation) as primary_count
        FROM restaurant_mentions rm
        JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
        JOIN query_results qr ON pr.query_result_id = qr.id
        GROUP BY rm.restaurant_name
        ORDER BY total_mentions DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Canonical restaurant operations
# ---------------------------------------------------------------------------


def reset_canonical_data(conn: sqlite3.Connection) -> None:
    """Clear all canonical data for a clean re-run (idempotent)."""
    conn.execute("UPDATE restaurant_mentions SET canonical_id = NULL")
    conn.execute("DELETE FROM canonical_restaurants")
    conn.commit()


def insert_canonical_restaurant(
    conn: sqlite3.Connection,
    canonical_name: str,
    variant_names: list[str],
    total_mentions: int,
    model_count: int,
    models_mentioning: list[str],
) -> int:
    """Insert a canonical restaurant entry. Returns the new row ID."""
    cursor = conn.execute(
        """
        INSERT INTO canonical_restaurants
            (canonical_name, variant_names, total_mentions, model_count, models_mentioning)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            canonical_name,
            json.dumps(variant_names),
            total_mentions,
            model_count,
            json.dumps(models_mentioning),
        ),
    )
    return cursor.lastrowid  # type: ignore[return-value]


def link_mentions_to_canonical(
    conn: sqlite3.Connection,
    canonical_id: int,
    variant_names: list[str],
) -> int:
    """Set canonical_id on all restaurant_mentions matching any variant name.

    Returns the number of rows updated.
    """
    placeholders = ",".join("?" for _ in variant_names)
    cursor = conn.execute(
        f"""
        UPDATE restaurant_mentions
        SET canonical_id = ?
        WHERE restaurant_name IN ({placeholders})
        """,
        [canonical_id] + variant_names,
    )
    return cursor.rowcount


def get_canonical_mention_counts(conn: sqlite3.Connection) -> list[dict]:
    """Get mention counts grouped by canonical restaurant — the post-resolution analysis query."""
    rows = conn.execute(
        """
        SELECT
            cr.canonical_name,
            cr.total_mentions,
            cr.model_count,
            cr.models_mentioning,
            cr.variant_names,
            AVG(rm.rank_position) as avg_rank,
            SUM(rm.is_primary_recommendation) as primary_count
        FROM canonical_restaurants cr
        JOIN restaurant_mentions rm ON rm.canonical_id = cr.id
        GROUP BY cr.id
        ORDER BY cr.total_mentions DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]
