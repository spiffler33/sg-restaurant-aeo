"""Tests for Google Places matching logic.

Focuses on the review anomaly bug fix: select_best_match should prefer
high-review flagship locations over franchise/express outlets that get
a better fuzzy name match score.
"""

from src.google_places import select_best_match, _review_count_override
from src.models import MatchConfidence


def _make_result(
    name: str,
    reviews: int,
    lat: float = 1.31,
    lng: float = 103.85,
    status: str = "OPERATIONAL",
    place_id: str = "test",
) -> dict:
    """Build a minimal Google Places result dict for testing."""
    return {
        "name": name,
        "place_id": place_id,
        "geometry": {"location": {"lat": lat, "lng": lng}},
        "types": ["restaurant", "food", "point_of_interest", "establishment"],
        "business_status": status,
        "user_ratings_total": reviews,
        "rating": 4.2,
    }


class TestReviewCountOverride:
    """Tests for the _review_count_override heuristic."""

    def test_override_triggers_at_5x_reviews(self):
        """≥5x review count + ≥55% similarity → override."""
        best = (_make_result("Swee Choon Express AMK Hub", 369), MatchConfidence.HIGH, 95.0)
        candidate = (_make_result("Swee Choon Tim Sum Restaurant", 11448), MatchConfidence.HIGH, 72.0)
        assert _review_count_override(best, candidate) is True

    def test_no_override_below_5x(self):
        """4x review count → no override."""
        best = (_make_result("Place A", 1000), MatchConfidence.HIGH, 90.0)
        candidate = (_make_result("Place B", 4000), MatchConfidence.HIGH, 60.0)
        assert _review_count_override(best, candidate) is False

    def test_no_override_low_similarity(self):
        """Even with 10x reviews, <55% similarity → no override."""
        best = (_make_result("Totally Different", 100), MatchConfidence.HIGH, 90.0)
        candidate = (_make_result("Something Else", 5000), MatchConfidence.MEDIUM, 40.0)
        assert _review_count_override(best, candidate) is False

    def test_no_override_zero_best_reviews(self):
        """If best has 0 reviews, don't divide by zero."""
        best = (_make_result("Place A", 0), MatchConfidence.HIGH, 90.0)
        candidate = (_make_result("Place B", 5000), MatchConfidence.HIGH, 60.0)
        assert _review_count_override(best, candidate) is False


class TestSelectBestMatchSweeChoon:
    """Test the Swee Choon example: flagship vs franchise selection.

    Canonical name: "Swee Choon Tim Sum Restaurant"
    Should match: Jalan Besar original (11,448 reviews)
    Should NOT match: AMK Hub express outlet (369 reviews)

    The express outlet gets a HIGHER fuzzy score because its name contains
    "Swee Choon" more prominently, but the original has 30x more reviews.
    """

    def test_prefers_flagship_over_franchise(self):
        """The Jalan Besar original should win over AMK Hub express."""
        results = [
            _make_result(
                "Swee Choon Express AMK Hub",
                369,
                place_id="express",
            ),
            _make_result(
                "Swee Choon Tim Sum Restaurant",
                11448,
                lat=1.3088,
                lng=103.8563,
                place_id="flagship",
            ),
        ]
        match = select_best_match("Swee Choon Tim Sum Restaurant", results)
        assert match is not None
        result, confidence, score = match
        assert result["place_id"] == "flagship"
        assert result["user_ratings_total"] == 11448

    def test_flagship_wins_even_when_listed_first(self):
        """Order shouldn't matter — flagship should still win."""
        results = [
            _make_result(
                "Swee Choon Tim Sum Restaurant",
                11448,
                lat=1.3088,
                lng=103.8563,
                place_id="flagship",
            ),
            _make_result(
                "Swee Choon Express AMK Hub",
                369,
                place_id="express",
            ),
        ]
        match = select_best_match("Swee Choon Tim Sum Restaurant", results)
        assert match is not None
        result, confidence, score = match
        assert result["place_id"] == "flagship"

    def test_similar_review_counts_no_override(self):
        """When review counts are similar, normal scoring wins."""
        results = [
            _make_result("Zaffron Kitchen", 1200, place_id="a"),
            _make_result("Zaffron Kitchen RELC Hotel", 900, place_id="b"),
        ]
        match = select_best_match("Zaffron Kitchen", results)
        assert match is not None
        # With similar review counts (<5x), the better name match should win
        result, _, _ = match
        assert result["place_id"] == "a"
