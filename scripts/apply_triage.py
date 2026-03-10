"""Apply human triage results from triage_125_done.csv to the SQLite DB.

Reads the CSV produced by human review of top-300 Google Places re-fetch,
and applies three categories of changes:
  1. Canonical name renames (21 entries where human corrected the name)
  2. Confirmed matches (91 Y entries → human_verified = 1)
  3. Rejected matches (34 N entries → closed-kept / wrong-match-removed / merges)
Plus: patches 3 review anomaly cases with correct high-review-count locations,
and marks 1,213 previously trusted HIGH+OPERATIONAL entries as human_verified.

Usage:
    python scripts/apply_triage.py            # dry-run (default)
    python scripts/apply_triage.py --apply    # write changes to DB
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "aeo.db"
TRIAGE_CSV = PROJECT_ROOT / "data" / "raw" / "google_places" / "triage_125_done.csv"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "google_places"


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------


def _normalize_quotes(s: str) -> str:
    """Replace Unicode smart quotes with ASCII equivalents."""
    return (
        s.replace("\u2018", "'")   # left single
         .replace("\u2019", "'")   # right single (curly apostrophe)
         .replace("\u201C", '"')   # left double
         .replace("\u201D", '"')   # right double
    )


def parse_triage_csv(path: Path) -> list[dict]:
    """Parse the triage CSV, handling Numbers export quirks.

    Row 1 is an artifact header ("triage_125") — skip it.
    Row 2 is the real header row.
    """
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    # Skip the Numbers artifact on row 1
    if lines[0].strip().startswith("triage_125"):
        lines = lines[1:]

    reader = csv.DictReader(lines)
    rows = []
    for row in reader:
        # Clean up "Change name to this" — strip trailing commas, whitespace,
        # and normalize Unicode smart quotes to ASCII
        rename_col = row.get("Change name to this", "").strip().rstrip(",").strip()
        rename_col = _normalize_quotes(rename_col)
        row["_rename_to"] = rename_col if rename_col else None

        # Parse canonical_id as int
        row["canonical_id"] = int(row["canonical_id"])

        # Normalize ok field
        row["ok"] = row.get("ok", "").strip().upper()

        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Categorization
# ---------------------------------------------------------------------------

# Wrong-match canonical IDs (identified during human review)
WRONG_MATCH_IDS = {
    3100,  # White Rabbit → matched to "The Rabbit Hole" (different restaurant)
    3292,  # Stellar at 1-Altitude → "Stellar | Singapore" not credible, 1-Altitude closed
}
# Note: 3148 (Potato Head Folk), 3212 (The Lokal), 3237 (Potato Head Singapore)
# are UNMATCHED, so no google_places entry to remove.

# Merge pairs: (loser_id → winner_id)
MERGE_PAIRS = {
    3316: 3219,  # Bincho at Hua Bee → Bincho (Bincho has more mentions: 7 vs 5)
    3263: 3264,  # Euphoria → Restaurant Euphoria (tied mentions but 3264 has 3 models vs 1)
}


def categorize_rows(rows: list[dict]) -> dict:
    """Split rows into action categories."""
    renames = []        # Rows where _rename_to is set
    confirmed = []      # Y entries with a Google match
    confirmed_unmatched = []  # Y entries that are UNMATCHED
    closed_keep = []    # N entries with CLOSED status → keep match
    wrong_match = []    # N entries that are wrong matches → remove
    merges = []         # N entries that are merge targets
    closed_unmatched = []  # N entries that are UNMATCHED and closed

    for row in rows:
        cid = row["canonical_id"]

        # Collect renames (can overlap with other categories)
        if row["_rename_to"]:
            renames.append(row)

        if row["ok"] == "Y":
            if row.get("confidence", "").upper() == "UNMATCHED" or not row.get("google_match", "").strip():
                confirmed_unmatched.append(row)
            else:
                confirmed.append(row)
        elif row["ok"] == "N":
            if cid in MERGE_PAIRS:
                merges.append(row)
            elif cid in WRONG_MATCH_IDS:
                wrong_match.append(row)
            elif not row.get("google_match", "").strip() or row.get("confidence", "").upper() == "UNMATCHED":
                closed_unmatched.append(row)
            else:
                closed_keep.append(row)

    return {
        "renames": renames,
        "confirmed": confirmed,
        "confirmed_unmatched": confirmed_unmatched,
        "closed_keep": closed_keep,
        "wrong_match": wrong_match,
        "merges": merges,
        "closed_unmatched": closed_unmatched,
    }


# ---------------------------------------------------------------------------
# Review anomaly patches (manual corrections from raw JSON inspection)
# ---------------------------------------------------------------------------

ANOMALY_PATCHES = [
    {
        "canonical_id": 3074,
        "description": "Swee Choon: replace Express/AMK Hub (369 reviews) with Jalan Besar flagship (11,448 reviews)",
        "place_id": "ChIJv1DkBMgZ2jERft-n2ibNvh0",
        "google_name": "Swee Choon Jalan Besar",
        "formatted_address": "183/185/187/189, 191 Jln Besar, 191/193, Singapore 208882",
        "lat": 1.3081642,
        "lng": 103.8569394,
        "rating": 4.3,
        "user_ratings_total": 11448,
        "price_level": 2,
        "types": ["restaurant", "food", "point_of_interest", "establishment"],
        "business_status": "OPERATIONAL",
    },
    {
        "canonical_id": 3153,
        "description": "Zaffron Kitchen: replace closed East Coast (2,183 reviews) with operational RELC Hotel (21 reviews)",
        "place_id": "ChIJhwOq3fkZ2jERhRJB00b9SOA",
        "google_name": "Zaffron Kitchen RELC Hotel",
        "formatted_address": "30 Orange Grove Rd, #04-02 RELC International Hotel, Singapore 258352",
        "lat": 1.3130374,
        "lng": 103.8260855,
        "rating": 4.8,
        "user_ratings_total": 21,
        "price_level": None,
        "types": ["restaurant", "food", "point_of_interest", "establishment"],
        "business_status": "OPERATIONAL",
    },
    {
        "canonical_id": 3235,
        "description": "Plain Vanilla: insert Tiong Bahru flagship (1,145 reviews) — was not in DB",
        "place_id": "ChIJQ8QhrXsZ2jERQlp3QVnlFz4",
        "google_name": "Plain Vanilla Tiong Bahru",
        "formatted_address": "1D Yong Siak St, Singapore 168641",
        "lat": 1.2823481,
        "lng": 103.8305203,
        "rating": 4.2,
        "user_ratings_total": 1145,
        "price_level": 2,
        "types": ["cafe", "bakery", "meal_takeaway", "restaurant", "food", "point_of_interest", "store", "establishment"],
        "business_status": "OPERATIONAL",
    },
]


# ---------------------------------------------------------------------------
# Dry-run summary
# ---------------------------------------------------------------------------


def print_summary(cats: dict, conn: sqlite3.Connection) -> None:
    """Print a detailed dry-run summary of all planned changes."""
    print("=" * 70)
    print("TRIAGE APPLICATION — DRY RUN SUMMARY")
    print("=" * 70)

    # 1. Renames
    renames = cats["renames"]
    print(f"\n{'─' * 70}")
    print(f"1. CANONICAL NAME RENAMES: {len(renames)}")
    print(f"{'─' * 70}")
    collision_count = 0
    for r in renames:
        cid = r["canonical_id"]
        # Get current DB name
        db_row = conn.execute(
            "SELECT canonical_name FROM canonical_restaurants WHERE id = ?", (cid,)
        ).fetchone()
        old_name = db_row["canonical_name"] if db_row else "(NOT FOUND)"
        new_name = r["_rename_to"]
        if old_name == new_name:
            print(f"  [{cid}] {old_name!r} (already correct)")
            continue

        # Check for collision
        existing = conn.execute(
            "SELECT id, total_mentions, model_count FROM canonical_restaurants "
            "WHERE canonical_name = ? AND id != ?",
            (new_name, cid),
        ).fetchone()
        if existing:
            print(f"  [{cid}] {old_name!r} → {new_name!r}  ⚠ MERGE with [{existing['id']}] "
                  f"({existing['total_mentions']} mentions, {existing['model_count']} models)")
            collision_count += 1
        else:
            print(f"  [{cid}] {old_name!r} → {new_name!r}")

    if collision_count:
        print(f"  ({collision_count} renames will trigger merges with existing entries)")

    # 2. Confirmed matches
    confirmed = cats["confirmed"]
    print(f"\n{'─' * 70}")
    print(f"2. CONFIRMED MATCHES (Y + has Google match): {len(confirmed)}")
    print(f"   → Will set human_verified = 1 on google_places for these canonical_ids")
    print(f"{'─' * 70}")
    for r in confirmed:
        print(f"  [{r['canonical_id']}] {r['canonical_name']} ← {r.get('google_match', 'N/A')}")

    # 2b. Confirmed unmatched
    unmatched_y = cats["confirmed_unmatched"]
    print(f"\n  Confirmed but UNMATCHED (Y, no Google match): {len(unmatched_y)}")
    for r in unmatched_y:
        print(f"    [{r['canonical_id']}] {r['canonical_name']} (no google_places action)")

    # 3. Previously trusted
    trusted_count = conn.execute(
        "SELECT COUNT(*) FROM google_places WHERE match_confidence = 'high' AND business_status = 'OPERATIONAL'"
    ).fetchone()[0]
    print(f"\n{'─' * 70}")
    print(f"3. PREVIOUSLY TRUSTED (HIGH + OPERATIONAL): {trusted_count}")
    print(f"   → Will set human_verified = 1 on all {trusted_count} rows")
    print(f"{'─' * 70}")

    # 4. Closed-keep
    closed = cats["closed_keep"]
    print(f"\n{'─' * 70}")
    print(f"4. CLOSED RESTAURANTS (N, valid match to closed restaurant): {len(closed)}")
    print(f"   → Will set human_verified = 1 (match is correct, restaurant is just closed)")
    print(f"{'─' * 70}")
    for r in closed:
        status = r.get("status", "?")
        print(f"  [{r['canonical_id']}] {r['canonical_name']} ({status})")

    # 5. Wrong matches
    wrong = cats["wrong_match"]
    print(f"\n{'─' * 70}")
    print(f"5. WRONG MATCHES (N, incorrect Google match): {len(wrong)}")
    print(f"   → Will DELETE google_places row for these")
    print(f"{'─' * 70}")
    for r in wrong:
        gp = conn.execute(
            "SELECT google_name, place_id FROM google_places WHERE canonical_id = ?",
            (r["canonical_id"],)
        ).fetchone()
        if gp:
            print(f"  [{r['canonical_id']}] {r['canonical_name']} — removing match to {gp['google_name']!r}")
        else:
            print(f"  [{r['canonical_id']}] {r['canonical_name']} — no google_places entry to remove")

    # 6. Merges
    print(f"\n{'─' * 70}")
    print(f"6. DUPLICATE MERGES: {len(MERGE_PAIRS)} pairs")
    print(f"{'─' * 70}")
    for loser_id, winner_id in MERGE_PAIRS.items():
        loser = conn.execute(
            "SELECT canonical_name, total_mentions, model_count FROM canonical_restaurants WHERE id = ?",
            (loser_id,)
        ).fetchone()
        winner = conn.execute(
            "SELECT canonical_name, total_mentions, model_count FROM canonical_restaurants WHERE id = ?",
            (winner_id,)
        ).fetchone()
        loser_mentions = conn.execute(
            "SELECT COUNT(*) FROM restaurant_mentions WHERE canonical_id = ?", (loser_id,)
        ).fetchone()[0]
        winner_mentions = conn.execute(
            "SELECT COUNT(*) FROM restaurant_mentions WHERE canonical_id = ?", (winner_id,)
        ).fetchone()[0]
        print(f"  MERGE [{loser_id}] {loser['canonical_name']!r} ({loser_mentions} mentions)")
        print(f"    INTO [{winner_id}] {winner['canonical_name']!r} ({winner_mentions} mentions)")
        print(f"    → Combined: {loser_mentions + winner_mentions} mentions")

    # 7. Anomaly patches
    print(f"\n{'─' * 70}")
    print(f"7. REVIEW ANOMALY PATCHES: {len(ANOMALY_PATCHES)}")
    print(f"{'─' * 70}")
    for patch in ANOMALY_PATCHES:
        cid = patch["canonical_id"]
        existing = conn.execute(
            "SELECT google_name, user_ratings_total, place_id FROM google_places WHERE canonical_id = ?",
            (cid,)
        ).fetchone()
        if existing:
            print(f"  [{cid}] REPLACE {existing['google_name']!r} ({existing['user_ratings_total']} reviews)")
            print(f"     WITH {patch['google_name']!r} ({patch['user_ratings_total']} reviews)")
        else:
            print(f"  [{cid}] INSERT {patch['google_name']!r} ({patch['user_ratings_total']} reviews)")
        print(f"    {patch['description']}")

    # 8. Closed unmatched
    closed_unmatched = cats["closed_unmatched"]
    print(f"\n{'─' * 70}")
    print(f"8. CLOSED + UNMATCHED (N, no Google match): {len(closed_unmatched)}")
    print(f"   → No google_places action (restaurants are closed, no match exists)")
    print(f"{'─' * 70}")
    for r in closed_unmatched:
        print(f"  [{r['canonical_id']}] {r['canonical_name']}")

    # Grand total
    total_n = len(cats["closed_keep"]) + len(cats["wrong_match"]) + len(cats["merges"]) + len(closed_unmatched)
    total_y = len(cats["confirmed"]) + len(cats["confirmed_unmatched"])
    print(f"\n{'=' * 70}")
    print(f"TOTALS: {len(renames)} renames, {total_y} confirmed (Y), {total_n} rejected (N)")
    print(f"  Y breakdown: {len(cats['confirmed'])} with match + {len(cats['confirmed_unmatched'])} unmatched")
    print(f"  N breakdown: {len(cats['closed_keep'])} closed-kept + {len(cats['wrong_match'])} wrong-match"
          f" + {len(MERGE_PAIRS)} merge-pairs + {len(closed_unmatched)} closed-unmatched")
    print(f"  Anomaly patches: {len(ANOMALY_PATCHES)}")
    print(f"  Previously trusted: {trusted_count}")
    print(f"{'=' * 70}")


# ---------------------------------------------------------------------------
# Apply operations
# ---------------------------------------------------------------------------


def add_human_verified_column(conn: sqlite3.Connection) -> None:
    """Add human_verified column to google_places if it doesn't exist."""
    try:
        conn.execute(
            "ALTER TABLE google_places ADD COLUMN human_verified BOOLEAN NOT NULL DEFAULT 0"
        )
        print("  Added human_verified column to google_places")
    except sqlite3.OperationalError:
        pass  # Column already exists


def merge_canonical_pair(
    conn: sqlite3.Connection, winner_id: int, loser_id: int, target_name: str
) -> None:
    """Merge two canonical entries under target_name. Winner absorbs loser."""
    loser = conn.execute(
        "SELECT canonical_name, variant_names, total_mentions FROM canonical_restaurants WHERE id = ?",
        (loser_id,),
    ).fetchone()
    winner = conn.execute(
        "SELECT canonical_name, variant_names FROM canonical_restaurants WHERE id = ?",
        (winner_id,),
    ).fetchone()

    # Reassign mentions from loser to winner
    mentions_moved = conn.execute(
        "UPDATE restaurant_mentions SET canonical_id = ? WHERE canonical_id = ?",
        (winner_id, loser_id),
    ).rowcount

    # Reassign google_places from loser to winner (skip if place_id conflicts)
    gp_moved = conn.execute(
        "UPDATE google_places SET canonical_id = ? WHERE canonical_id = ?",
        (winner_id, loser_id),
    ).rowcount

    # Merge variant_names: collect all names from both sides
    winner_variants = json.loads(winner["variant_names"])
    loser_variants = json.loads(loser["variant_names"])
    all_names = set(winner_variants + loser_variants + [loser["canonical_name"], winner["canonical_name"]])
    all_names.discard(target_name)  # Don't include the new canonical name as a variant
    all_variants = sorted(all_names)

    # Recalculate stats from actual DB data
    new_total = conn.execute(
        "SELECT COUNT(*) FROM restaurant_mentions WHERE canonical_id = ?", (winner_id,)
    ).fetchone()[0]
    model_rows = conn.execute(
        """SELECT DISTINCT qr.model_name
           FROM restaurant_mentions rm
           JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
           JOIN query_results qr ON pr.query_result_id = qr.id
           WHERE rm.canonical_id = ?""",
        (winner_id,),
    ).fetchall()
    new_models = sorted(set(r["model_name"] for r in model_rows))

    # Delete loser FIRST to avoid UNIQUE constraint on canonical_name
    conn.execute("DELETE FROM canonical_restaurants WHERE id = ?", (loser_id,))

    # Then update winner with target name and merged stats
    conn.execute(
        "UPDATE canonical_restaurants SET canonical_name = ?, variant_names = ?, "
        "total_mentions = ?, model_count = ?, models_mentioning = ? WHERE id = ?",
        (target_name, json.dumps(all_variants), new_total, len(new_models), json.dumps(new_models), winner_id),
    )

    print(f"    MERGE+RENAME [{loser_id}] {loser['canonical_name']!r} → [{winner_id}] {target_name!r}")
    print(f"      {mentions_moved} mentions moved, {gp_moved} google_places moved, new total: {new_total}")


def apply_renames(conn: sqlite3.Connection, renames: list[dict]) -> int:
    """Apply canonical name renames. Handles collisions as merges. Returns count."""
    count = 0
    merge_count = 0
    for r in renames:
        cid = r["canonical_id"]
        new_name = r["_rename_to"]

        # Get current name
        db_row = conn.execute(
            "SELECT canonical_name FROM canonical_restaurants WHERE id = ?", (cid,)
        ).fetchone()
        if not db_row:
            print(f"  WARNING: canonical_id {cid} not found in DB, skipping")
            continue

        old_name = db_row["canonical_name"]
        if old_name == new_name:
            continue

        # Check if target name already exists as a different canonical entry
        existing = conn.execute(
            "SELECT id, canonical_name, total_mentions, model_count FROM canonical_restaurants "
            "WHERE canonical_name = ? AND id != ?",
            (new_name, cid),
        ).fetchone()

        if existing:
            # Collision: merge the two entries under the target name
            source_mentions = conn.execute(
                "SELECT COUNT(*) FROM restaurant_mentions WHERE canonical_id = ?", (cid,)
            ).fetchone()[0]
            existing_mentions = conn.execute(
                "SELECT COUNT(*) FROM restaurant_mentions WHERE canonical_id = ?", (existing["id"],)
            ).fetchone()[0]

            # Winner = more actual mentions; if tied, more models
            if source_mentions > existing_mentions:
                winner_id, loser_id = cid, existing["id"]
            elif source_mentions < existing_mentions:
                winner_id, loser_id = existing["id"], cid
            else:
                # Tie on mentions — pick by model_count
                source_models = db_row.keys()  # need to re-fetch
                source_row = conn.execute(
                    "SELECT model_count FROM canonical_restaurants WHERE id = ?", (cid,)
                ).fetchone()
                if source_row["model_count"] >= existing["model_count"]:
                    winner_id, loser_id = cid, existing["id"]
                else:
                    winner_id, loser_id = existing["id"], cid

            print(f"  [{cid}] {old_name!r} → {new_name!r} (COLLISION with [{existing['id']}])")
            merge_canonical_pair(conn, winner_id, loser_id, new_name)
            merge_count += 1
            count += 1
            continue

        # Simple rename (no collision)
        conn.execute(
            "UPDATE canonical_restaurants SET canonical_name = ? WHERE id = ?",
            (new_name, cid),
        )

        # Update restaurant_mentions where name matches old canonical name
        updated = conn.execute(
            "UPDATE restaurant_mentions SET restaurant_name = ? WHERE restaurant_name = ? AND canonical_id = ?",
            (new_name, old_name, cid),
        ).rowcount

        # Add old name to variant_names if not already there
        variant_row = conn.execute(
            "SELECT variant_names FROM canonical_restaurants WHERE id = ?", (cid,)
        ).fetchone()
        variants = json.loads(variant_row["variant_names"])
        if old_name not in variants:
            variants.append(old_name)
            conn.execute(
                "UPDATE canonical_restaurants SET variant_names = ? WHERE id = ?",
                (json.dumps(variants), cid),
            )

        print(f"  [{cid}] {old_name!r} → {new_name!r} ({updated} mentions updated)")
        count += 1

    if merge_count:
        print(f"  ({merge_count} renames required merges with existing entries)")

    return count


def apply_confirmed(conn: sqlite3.Connection, confirmed: list[dict]) -> int:
    """Mark confirmed Y matches as human_verified = 1. Returns count."""
    count = 0
    for r in confirmed:
        cid = r["canonical_id"]
        updated = conn.execute(
            "UPDATE google_places SET human_verified = 1 WHERE canonical_id = ?",
            (cid,),
        ).rowcount
        if updated:
            count += updated
    return count


def apply_previously_trusted(conn: sqlite3.Connection) -> int:
    """Mark all HIGH + OPERATIONAL entries as human_verified = 1."""
    cursor = conn.execute(
        "UPDATE google_places SET human_verified = 1 "
        "WHERE match_confidence = 'high' AND business_status = 'OPERATIONAL'"
    )
    return cursor.rowcount


def apply_closed_keep(conn: sqlite3.Connection, closed: list[dict]) -> int:
    """Mark closed-but-correct matches as human_verified = 1."""
    count = 0
    for r in closed:
        cid = r["canonical_id"]
        updated = conn.execute(
            "UPDATE google_places SET human_verified = 1 WHERE canonical_id = ?",
            (cid,),
        ).rowcount
        if updated:
            count += updated
    return count


def apply_wrong_matches(conn: sqlite3.Connection, wrong: list[dict]) -> int:
    """Delete wrong Google match entries. Returns count deleted."""
    count = 0
    for r in wrong:
        cid = r["canonical_id"]
        deleted = conn.execute(
            "DELETE FROM google_places WHERE canonical_id = ?", (cid,),
        ).rowcount
        if deleted:
            print(f"  [{cid}] {r['canonical_name']}: deleted {deleted} google_places row(s)")
            count += deleted
        else:
            print(f"  [{cid}] {r['canonical_name']}: no google_places entry found")
    return count


def apply_merges(conn: sqlite3.Connection) -> int:
    """Merge duplicate canonical entries. Returns count of merges performed."""
    count = 0
    for loser_id, winner_id in MERGE_PAIRS.items():
        loser = conn.execute(
            "SELECT canonical_name, variant_names, total_mentions, model_count, models_mentioning "
            "FROM canonical_restaurants WHERE id = ?",
            (loser_id,),
        ).fetchone()
        winner = conn.execute(
            "SELECT canonical_name, variant_names, total_mentions, model_count, models_mentioning "
            "FROM canonical_restaurants WHERE id = ?",
            (winner_id,),
        ).fetchone()

        if not loser or not winner:
            print(f"  WARNING: merge pair {loser_id}→{winner_id} — one side not found, skipping")
            continue

        # Reassign mentions from loser to winner
        mentions_moved = conn.execute(
            "UPDATE restaurant_mentions SET canonical_id = ? WHERE canonical_id = ?",
            (winner_id, loser_id),
        ).rowcount

        # Reassign google_places from loser to winner
        gp_moved = conn.execute(
            "UPDATE google_places SET canonical_id = ? WHERE canonical_id = ?",
            (winner_id, loser_id),
        ).rowcount

        # Merge variant_names
        winner_variants = json.loads(winner["variant_names"])
        loser_variants = json.loads(loser["variant_names"])
        # Add loser's canonical name and all its variants
        all_variants = list(set(winner_variants + loser_variants + [loser["canonical_name"]]))
        # Remove winner's canonical name from variants (it's the canonical, not a variant)
        if winner["canonical_name"] in all_variants:
            all_variants.remove(winner["canonical_name"])

        # Recalculate total_mentions from actual DB data
        new_total = conn.execute(
            "SELECT COUNT(*) FROM restaurant_mentions WHERE canonical_id = ?",
            (winner_id,),
        ).fetchone()[0]

        # Recalculate model_count from actual DB data
        model_rows = conn.execute(
            """SELECT DISTINCT qr.model_name
               FROM restaurant_mentions rm
               JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
               JOIN query_results qr ON pr.query_result_id = qr.id
               WHERE rm.canonical_id = ?""",
            (winner_id,),
        ).fetchall()
        new_models = sorted(set(r["model_name"] for r in model_rows))
        new_model_count = len(new_models)

        # Update winner
        conn.execute(
            "UPDATE canonical_restaurants SET variant_names = ?, total_mentions = ?, "
            "model_count = ?, models_mentioning = ? WHERE id = ?",
            (json.dumps(all_variants), new_total, new_model_count, json.dumps(new_models), winner_id),
        )

        # Delete loser
        conn.execute("DELETE FROM canonical_restaurants WHERE id = ?", (loser_id,))

        print(f"  MERGED [{loser_id}] {loser['canonical_name']!r} → [{winner_id}] {winner['canonical_name']!r}")
        print(f"    {mentions_moved} mentions moved, {gp_moved} google_places moved")
        print(f"    New total: {new_total} mentions, {new_model_count} models")
        count += 1

    return count


def apply_anomaly_patches(conn: sqlite3.Connection) -> int:
    """Patch review anomaly cases with correct Google Places data."""
    count = 0
    now = datetime.now(timezone.utc).isoformat()

    for patch in ANOMALY_PATCHES:
        cid = patch["canonical_id"]

        # Delete any existing google_places entry for this canonical_id
        old_entry = conn.execute(
            "SELECT place_id, google_name FROM google_places WHERE canonical_id = ?", (cid,)
        ).fetchone()
        if old_entry:
            conn.execute("DELETE FROM google_places WHERE canonical_id = ?", (cid,))
            print(f"  [{cid}] Removed old match: {old_entry['google_name']!r}")

        # Check if the target place_id already exists (from another canonical entry)
        existing_place = conn.execute(
            "SELECT id, canonical_id, google_name FROM google_places WHERE place_id = ?",
            (patch["place_id"],),
        ).fetchone()

        if existing_place:
            # Update the existing entry to point to our canonical_id
            conn.execute(
                """UPDATE google_places SET
                    canonical_id = ?, google_name = ?, formatted_address = ?,
                    lat = ?, lng = ?, rating = ?, user_ratings_total = ?,
                    price_level = ?, types = ?, business_status = ?,
                    match_confidence = 'high', match_score = 100.0,
                    human_verified = 1, fetched_at = ?
                WHERE place_id = ?""",
                (
                    cid,
                    patch["google_name"],
                    patch["formatted_address"],
                    patch["lat"],
                    patch["lng"],
                    patch["rating"],
                    patch["user_ratings_total"],
                    patch["price_level"],
                    json.dumps(patch["types"]),
                    patch["business_status"],
                    now,
                    patch["place_id"],
                ),
            )
            print(f"  [{cid}] REASSIGNED from [{existing_place['canonical_id']}]: "
                  f"{patch['google_name']} ({patch['user_ratings_total']} reviews)")
        else:
            # Insert fresh
            conn.execute(
                """INSERT INTO google_places
                    (canonical_id, place_id, google_name, formatted_address,
                     lat, lng, rating, user_ratings_total, price_level, types,
                     business_status, match_confidence, match_score,
                     is_popular_baseline, human_verified, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'high', 100.0, 0, 1, ?)""",
                (
                    cid,
                    patch["place_id"],
                    patch["google_name"],
                    patch["formatted_address"],
                    patch["lat"],
                    patch["lng"],
                    patch["rating"],
                    patch["user_ratings_total"],
                    patch["price_level"],
                    json.dumps(patch["types"]),
                    patch["business_status"],
                    now,
                ),
            )
            print(f"  [{cid}] INSERTED: {patch['google_name']} ({patch['user_ratings_total']} reviews)")

        print(f"    {patch['description']}")
        count += 1

    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    apply_mode = "--apply" in sys.argv

    # Parse CSV
    print(f"Reading triage CSV: {TRIAGE_CSV}")
    rows = parse_triage_csv(TRIAGE_CSV)
    print(f"  Parsed {len(rows)} rows (skipped Numbers header artifact)")

    # Connect to DB
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Categorize
    cats = categorize_rows(rows)

    # Print summary
    print_summary(cats, conn)

    if not apply_mode:
        print("\n⚠  DRY RUN — no changes written. Re-run with --apply to commit changes.")
        conn.close()
        return

    # Confirm
    print("\nReady to apply all changes above to the database.")
    response = input("Type 'yes' to proceed: ").strip().lower()
    if response != "yes":
        print("Aborted.")
        conn.close()
        return

    print("\n" + "=" * 70)
    print("APPLYING CHANGES")
    print("=" * 70)

    # Add human_verified column
    add_human_verified_column(conn)

    # 1. Renames
    print(f"\n--- Renames ---")
    n_renames = apply_renames(conn, cats["renames"])
    print(f"  Total: {n_renames} renames applied")

    # 2. Anomaly patches (before confirmed, so they get human_verified too)
    print(f"\n--- Anomaly Patches ---")
    n_patches = apply_anomaly_patches(conn)
    print(f"  Total: {n_patches} patches applied")

    # 3. Confirmed matches → human_verified = 1
    print(f"\n--- Confirmed Matches (Y) ---")
    n_confirmed = apply_confirmed(conn, cats["confirmed"])
    print(f"  Total: {n_confirmed} google_places rows marked human_verified")

    # 4. Previously trusted → human_verified = 1
    print(f"\n--- Previously Trusted (HIGH + OPERATIONAL) ---")
    n_trusted = apply_previously_trusted(conn)
    print(f"  Total: {n_trusted} rows marked human_verified")

    # 5. Closed-keep → human_verified = 1
    print(f"\n--- Closed Restaurants (keep match) ---")
    n_closed = apply_closed_keep(conn, cats["closed_keep"])
    print(f"  Total: {n_closed} google_places rows marked human_verified")

    # 6. Wrong matches → delete
    print(f"\n--- Wrong Matches (remove) ---")
    n_wrong = apply_wrong_matches(conn, cats["wrong_match"])
    print(f"  Total: {n_wrong} google_places rows deleted")

    # 7. Merges
    print(f"\n--- Duplicate Merges ---")
    n_merges = apply_merges(conn)
    print(f"  Total: {n_merges} merges completed")

    # Commit everything
    conn.commit()

    # Final verification
    print(f"\n{'=' * 70}")
    print("VERIFICATION")
    print(f"{'=' * 70}")
    total_gp = conn.execute("SELECT COUNT(*) FROM google_places").fetchone()[0]
    verified = conn.execute("SELECT COUNT(*) FROM google_places WHERE human_verified = 1").fetchone()[0]
    total_canon = conn.execute("SELECT COUNT(*) FROM canonical_restaurants").fetchone()[0]
    unlinked = conn.execute(
        "SELECT COUNT(*) FROM restaurant_mentions WHERE canonical_id IS NULL"
    ).fetchone()[0]
    print(f"  google_places: {total_gp} total, {verified} human_verified")
    print(f"  canonical_restaurants: {total_canon} total")
    print(f"  unlinked mentions: {unlinked}")

    conn.close()
    print("\nDone! All changes committed.")


if __name__ == "__main__":
    main()
