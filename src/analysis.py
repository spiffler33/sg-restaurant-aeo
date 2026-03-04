"""Core analysis functions for SG Restaurant AEO.

Reusable analytical queries and computations used by both
Jupyter notebooks and the Streamlit dashboard.

This module will be fully implemented in Phase 4.
"""

from __future__ import annotations

import sqlite3


def model_agreement_matrix(conn: sqlite3.Connection) -> dict:
    """Compute which restaurants each model recommends and their overlap.

    Returns a dict with per-model restaurant sets and pairwise Jaccard similarity.
    """
    # TODO: Phase 4
    raise NotImplementedError


def top_restaurants_by_model(conn: sqlite3.Connection, model_name: str, limit: int = 20) -> list[dict]:
    """Get the most frequently recommended restaurants for a given model."""
    # TODO: Phase 4
    raise NotImplementedError


def signal_importance(conn: sqlite3.Connection) -> dict:
    """Analyze what signals predict restaurant recommendation.

    Examines correlation between mention frequency and:
    - Cuisine type, price level, neighbourhood
    - Position in response (earlier = stronger signal?)
    - Primary vs passing mention ratio
    """
    # TODO: Phase 4
    raise NotImplementedError
