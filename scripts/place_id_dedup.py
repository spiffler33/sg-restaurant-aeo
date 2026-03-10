#!/usr/bin/env python3
"""Place ID dedup pass — merge canonical restaurants sharing the same Google place_id.

Scans raw Google Places JSON files to find canonical restaurants whose best
match resolves to the same Google place_id. Since the google_places table has
a UNIQUE constraint on place_id, these collisions are invisible in the DB
(the "best match wins" logic keeps only one). This script recovers the lost
signal and merges the duplicates.

Usage:
    python scripts/place_id_dedup.py              # Dry run (report only)
    python scripts/place_id_dedup.py --apply       # Execute merges
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from rapidfuzz import fuzz

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.entity_resolution import normalize_name
from src.google_places import select_best_match


def find_place_id_collisions(
    raw_dir: Path, conn: sqlite3.Connection
) -> list[dict]:
    """Find canonical restaurants that resolve to the same Google place_id.

    Scans raw JSON files, applies select_best_match, and cross-references
    with the google_places table to find collisions.

    Returns a list of merge actions: {keep_id, keep_name, merge_id, merge_name,
    google_name, place_id, similarity}.
    """
    json_files = sorted(raw_dir.glob("*.json"))
    if not json_files:
        print(f"No raw JSON files found in {raw_dir}")
        return []

    # Step 1: For each raw file, find the best match place_id
    raw_matches: dict[int, tuple[str, str]] = {}  # canonical_id -> (place_id, canonical_name)
    for f in json_files:
        data = json.loads(f.read_text())
        cid = data["canonical_id"]
        cname = data["canonical_name"]
        results = data.get("results", [])

        match = select_best_match(cname, results)
        if match:
            result, confidence, score = match
            raw_matches[cid] = (result["place_id"], cname)

    # Step 2: Find collisions within raw files
    place_to_raw: dict[str, list[int]] = defaultdict(list)
    for cid, (pid, _) in raw_matches.items():
        place_to_raw[pid].append(cid)

    # Step 3: Find cross-collisions with DB
    merge_actions: list[dict] = []
    seen_pairs: set[tuple[int, int]] = set()

    for cid, (pid, cname) in raw_matches.items():
        # Check if this place_id belongs to a different canonical in the DB
        row = conn.execute(
            "SELECT canonical_id FROM google_places WHERE place_id = ?",
            (pid,),
        ).fetchone()

        if row and row["canonical_id"] and row["canonical_id"] != cid:
            db_cid = row["canonical_id"]
            pair = (min(cid, db_cid), max(cid, db_cid))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            _add_merge_if_valid(conn, cid, db_cid, pid, merge_actions)

    # Step 4: Find collisions within raw files (both canonical_ids in raw set)
    for pid, cids in place_to_raw.items():
        if len(cids) < 2:
            continue
        for i in range(len(cids)):
            for j in range(i + 1, len(cids)):
                pair = (min(cids[i], cids[j]), max(cids[i], cids[j]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                _add_merge_if_valid(conn, cids[i], cids[j], pid, merge_actions)

    return merge_actions


def _add_merge_if_valid(
    conn: sqlite3.Connection,
    cid_a: int,
    cid_b: int,
    place_id: str,
    merge_actions: list[dict],
) -> None:
    """Check if two canonical restaurants should be merged based on name similarity."""
    row_a = conn.execute(
        "SELECT canonical_name, total_mentions, variant_names FROM canonical_restaurants WHERE id = ?",
        (cid_a,),
    ).fetchone()
    row_b = conn.execute(
        "SELECT canonical_name, total_mentions, variant_names FROM canonical_restaurants WHERE id = ?",
        (cid_b,),
    ).fetchone()

    if not row_a or not row_b:
        return

    name_a, mentions_a = row_a["canonical_name"], row_a["total_mentions"]
    name_b, mentions_b = row_b["canonical_name"], row_b["total_mentions"]

    # Name similarity check — filter out false positives
    norm_a = normalize_name(name_a)
    norm_b = normalize_name(name_b)
    sort_score = fuzz.token_sort_ratio(norm_a, norm_b)
    set_score = fuzz.token_set_ratio(norm_a, norm_b)
    similarity = max(sort_score, set_score)

    if similarity < 65:
        return  # False positive — different restaurants matched to same Google place

    # Keep the one with more mentions
    if mentions_a >= mentions_b:
        keep_id, keep_name, keep_mentions = cid_a, name_a, mentions_a
        merge_id, merge_name, merge_mentions = cid_b, name_b, mentions_b
        keep_variants = json.loads(row_a["variant_names"])
        merge_variants = json.loads(row_b["variant_names"])
    else:
        keep_id, keep_name, keep_mentions = cid_b, name_b, mentions_b
        merge_id, merge_name, merge_mentions = cid_a, name_a, mentions_a
        keep_variants = json.loads(row_b["variant_names"])
        merge_variants = json.loads(row_a["variant_names"])

    # Get google_name for display
    gp_row = conn.execute(
        "SELECT google_name FROM google_places WHERE place_id = ?", (place_id,)
    ).fetchone()
    google_name = gp_row["google_name"] if gp_row else "?"

    merge_actions.append({
        "keep_id": keep_id,
        "keep_name": keep_name,
        "keep_mentions": keep_mentions,
        "keep_variants": keep_variants,
        "merge_id": merge_id,
        "merge_name": merge_name,
        "merge_mentions": merge_mentions,
        "merge_variants": merge_variants,
        "google_name": google_name,
        "place_id": place_id,
        "similarity": similarity,
    })


def execute_merges(
    conn: sqlite3.Connection, merge_actions: list[dict]
) -> int:
    """Execute the merge actions: reassign mentions and delete duplicates.

    For each merge:
    1. Reassign restaurant_mentions from merge_id → keep_id
    2. Add merge_name's variants to keep's variant list
    3. Update keep's total_mentions and model stats
    4. Reassign or delete google_places entry for merge_id
    5. Delete the merge canonical_restaurants entry
    """
    merged = 0
    for action in merge_actions:
        keep_id = action["keep_id"]
        merge_id = action["merge_id"]

        # 1. Reassign mentions
        conn.execute(
            "UPDATE restaurant_mentions SET canonical_id = ? WHERE canonical_id = ?",
            (keep_id, merge_id),
        )

        # 2. Merge variant lists
        combined_variants = list(set(action["keep_variants"] + action["merge_variants"]))
        combined_variants.sort()

        # 3. Recalculate stats from actual mentions
        stats = conn.execute(
            """
            SELECT COUNT(*) as total_mentions,
                   COUNT(DISTINCT qr.model_name) as model_count,
                   GROUP_CONCAT(DISTINCT qr.model_name) as models
            FROM restaurant_mentions rm
            JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
            JOIN query_results qr ON pr.query_result_id = qr.id
            WHERE rm.canonical_id = ?
            """,
            (keep_id,),
        ).fetchone()

        models_list = sorted(stats["models"].split(",")) if stats["models"] else []

        conn.execute(
            """
            UPDATE canonical_restaurants
            SET variant_names = ?, total_mentions = ?, model_count = ?, models_mentioning = ?
            WHERE id = ?
            """,
            (
                json.dumps(combined_variants),
                stats["total_mentions"],
                stats["model_count"],
                json.dumps(models_list),
                keep_id,
            ),
        )

        # 4. Delete or reassign google_places for merge_id
        conn.execute(
            "DELETE FROM google_places WHERE canonical_id = ?",
            (merge_id,),
        )

        # 5. Delete the merged canonical entry
        conn.execute(
            "DELETE FROM canonical_restaurants WHERE id = ?",
            (merge_id,),
        )

        merged += 1

    conn.commit()
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Place ID dedup pass")
    parser.add_argument("--apply", action="store_true", help="Execute merges (default: dry run)")
    args = parser.parse_args()

    db_path = Path("data/aeo.db")
    raw_dir = Path("data/raw/google_places")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    # Pre-merge stats
    pre_canonical = conn.execute("SELECT COUNT(*) FROM canonical_restaurants").fetchone()[0]

    merge_actions = find_place_id_collisions(raw_dir, conn)

    if not merge_actions:
        print("No place_id duplicates found — nothing to merge.")
        return

    # Print report
    print(f"\n{'='*70}")
    print(f"PLACE ID DEDUP REPORT — {len(merge_actions)} merges found")
    print(f"{'='*70}\n")

    for i, action in enumerate(merge_actions, 1):
        print(f"{i:2d}. Google: \"{action['google_name']}\"")
        print(f"    KEEP:  id={action['keep_id']:4d}  \"{action['keep_name']}\" ({action['keep_mentions']} mentions)")
        print(f"    MERGE: id={action['merge_id']:4d}  \"{action['merge_name']}\" ({action['merge_mentions']} mentions)")
        print(f"    Similarity: {action['similarity']:.0f}%")
        print()

    if not args.apply:
        print(f"DRY RUN — pass --apply to execute {len(merge_actions)} merges")
        print(f"Canonical restaurants: {pre_canonical} → {pre_canonical - len(merge_actions)} (projected)")
        return

    # Execute
    merged = execute_merges(conn, merge_actions)
    post_canonical = conn.execute("SELECT COUNT(*) FROM canonical_restaurants").fetchone()[0]

    print(f"APPLIED {merged} merges")
    print(f"Canonical restaurants: {pre_canonical} → {post_canonical}")

    conn.close()


if __name__ == "__main__":
    main()
