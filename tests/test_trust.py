"""Trust score edge cases — exercises the pure scoring layer directly."""
from __future__ import annotations

import time

import pytest

from db import queries
from tools.trust import compute_trust_score, get_tier, score_breakdown, recompute_and_persist


# ---------- tier mapping ----------

@pytest.mark.parametrize(
    "score,expected",
    [
        (0, "NEW"),
        (50, "NEW"),
        (99, "NEW"),
        (100, "BRONZE"),
        (299, "BRONZE"),
        (300, "SILVER"),
        (549, "SILVER"),
        (550, "GOLD"),
        (799, "GOLD"),
        (800, "PLATINUM"),
        (1000, "PLATINUM"),
    ],
)
def test_get_tier_thresholds(score, expected):
    assert get_tier(score) == expected


# ---------- edge: brand-new agent ----------

def test_zero_transactions_scores_only_age_component(fresh_db, conn):
    # Register fresh; no tx, no endorsements, not verified.
    queries.insert_agent(
        conn,
        agent_id="brand-new",
        name="BN",
        description="",
        capabilities=[],
        operator_url="",
        agent_token="tok-bn",
    )
    score = compute_trust_score("brand-new", conn)
    # log10(0+1)*40=0, 0 success rate, age ~0 days, 0 endorsements, 0 disputes, no verify
    assert score == 0
    assert get_tier(score) == "NEW"


# ---------- edge: 100% dispute rate ----------

def test_high_dispute_count_floors_at_zero(fresh_db, conn):
    queries.insert_agent(
        conn,
        agent_id="bad-actor",
        name="Bad",
        description="",
        capabilities=[],
        operator_url="",
        agent_token="tok-bad",
    )
    # Simulate many disputes — each is -30, max(0, ...) clamps.
    conn.execute(
        "UPDATE agents SET dispute_count=50 WHERE agent_id='bad-actor'"
    )
    conn.commit()
    score = compute_trust_score("bad-actor", conn)
    assert score == 0


# ---------- edge: max endorsements caps at 200 ----------

def test_endorsements_cap_at_two_hundred_points(fresh_db, conn):
    # Two agents — endorsee + endorser per row (foreign keys aren't enforced).
    queries.insert_agent(conn, agent_id="endo-target", name="T", description="", capabilities=[], operator_url="", agent_token="tk1")
    queries.insert_agent(conn, agent_id="endorser", name="E", description="", capabilities=[], operator_url="", agent_token="tk2")

    # 30 endorsements → would be 300 pts uncapped, must cap at 200
    for i in range(30):
        queries.insert_endorsement(
            conn,
            endorser_id="endorser",
            endorsed_id="endo-target",
            endorsement_type="quality",
            notes=f"e{i}",
        )

    breakdown = score_breakdown("endo-target", conn)
    assert breakdown["endorsements"] == 200


# ---------- edge: perfect record ----------

def test_perfect_record_climbs_to_platinum(fresh_db, conn):
    # Insert an agent with 1000 successful tx, verified, and lots of endorsements.
    now = time.time()
    conn.execute(
        """
        INSERT INTO agents (
            agent_id, name, description, capabilities, operator_url, agent_token,
            created_at, last_active, total_transactions, successful_transactions,
            total_volume_usd, dispute_count, verified
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ace",
            "Ace",
            "perfect",
            "[]",
            "",
            "tok-ace",
            now - 86400 * 400,  # >1 year old
            now,
            1000,
            1000,
            500_000.0,
            0,
            1,
        ),
    )
    conn.commit()

    queries.insert_agent(conn, agent_id="ace-endorser", name="E", description="", capabilities=[], operator_url="", agent_token="tok-eA")
    for _ in range(25):
        queries.insert_endorsement(conn, endorser_id="ace-endorser", endorsed_id="ace", endorsement_type="quality", notes="")

    score = compute_trust_score("ace", conn)
    # ≈ 200 (volume) + 400 (success) + 100 (age) + 200 (endorsements) + 100 (verified) = 1000
    assert score >= 800
    assert get_tier(score) == "PLATINUM"


# ---------- edge: failure rate erodes score ----------

def test_failure_rate_drops_score(fresh_db, conn):
    now = time.time()
    conn.execute(
        """INSERT INTO agents (agent_id, name, capabilities, agent_token, created_at, last_active,
                               total_transactions, successful_transactions, dispute_count, verified)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("flaky", "Flaky", "[]", "tk-fl", now - 86400 * 100, now, 100, 20, 0, 0),
    )
    conn.commit()
    score = compute_trust_score("flaky", conn)
    breakdown = score_breakdown("flaky", conn)
    # Success rate = 20% → 80 pts (vs. 400 pts at 100%)
    assert breakdown["success_rate"] == 80
    assert score < 300  # well under SILVER


# ---------- recompute persists the score ----------

def test_recompute_persists_score_and_tier(fresh_db, conn):
    queries.insert_agent(conn, agent_id="persist", name="P", description="", capabilities=[], operator_url="", agent_token="tk-p")
    new = recompute_and_persist("persist", conn)
    row = conn.execute("SELECT trust_score, tier FROM agents WHERE agent_id='persist'").fetchone()
    assert int(row["trust_score"]) == new
    assert row["tier"] == get_tier(new)


# ---------- score is strictly bounded ----------

def test_score_bounded_zero_to_thousand(fresh_db, conn):
    # Synthesize an absurd combination: huge success volume + endorsements + verified.
    now = time.time()
    conn.execute(
        """INSERT INTO agents (agent_id, name, capabilities, agent_token, created_at, last_active,
                               total_transactions, successful_transactions, dispute_count, verified)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("max-out", "Max", "[]", "tk-max", now - 86400 * 999, now, 999_999, 999_999, 0, 1),
    )
    conn.commit()
    queries.insert_agent(conn, agent_id="endorser-max", name="E", description="", capabilities=[], operator_url="", agent_token="tk-em")
    for _ in range(100):
        queries.insert_endorsement(conn, endorser_id="endorser-max", endorsed_id="max-out", endorsement_type="quality", notes="")

    score = compute_trust_score("max-out", conn)
    assert 0 <= score <= 1000
