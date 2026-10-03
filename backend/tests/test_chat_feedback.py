"""Milestone 3.3 - chatbot conversation experience feedback.

Covers the whole feedback loop: the public endpoint, its rating/identity rules,
the Admin Portal audit trail, and the guarantee that nothing else regressed.
"""
import uuid

from app.services import audit_service
from tests.conftest import login

FEEDBACK = "/api/chat/feedback"


def cid():
    """A fresh, canonical conversation id."""
    return str(uuid.uuid4())


def stored(client):
    """Every stored feedback row, newest first, read back as an admin would."""
    admin_h = login(client, "admin@test.com", "AdminPass123!")
    return client.get("/api/admin/chat-feedback", headers=admin_h).json()


# 1. anonymous feedback is accepted
def test_feedback_without_token_succeeds(client):
    r = client.post(FEEDBACK, json={"conversation_id": cid(), "rating": 3})
    assert r.status_code == 200, r.text
    assert r.json() == {"success": True}


# 2. every valid rating is stored
def test_each_valid_rating_is_stored(client):
    conversations = {}
    for rating in (1, 2, 3):
        conversation = cid()
        conversations[conversation] = rating
        r = client.post(FEEDBACK, json={"conversation_id": conversation, "rating": rating})
        assert r.status_code == 200, r.text

    rows = {row["conversation_id"]: row["rating"] for row in stored(client)}
    assert rows == conversations


# 3. authenticated feedback is accepted
def test_feedback_with_token_succeeds(client, user_h):
    r = client.post(FEEDBACK, json={"conversation_id": cid(), "rating": 2}, headers=user_h)
    assert r.status_code == 200, r.text
    assert r.json() == {"success": True}


# 4. missing / invalid fields are rejected
def test_missing_fields_rejected(client):
    assert client.post(FEEDBACK, json={"rating": 3}).status_code == 422
    assert client.post(FEEDBACK, json={"conversation_id": cid()}).status_code == 422
    assert client.post(FEEDBACK, json={}).status_code == 422


# 5. rating outside 1-3 is rejected
def test_out_of_range_rating_rejected(client):
    for bad in (0, 4, -1, 99):
        r = client.post(FEEDBACK, json={"conversation_id": cid(), "rating": bad})
        assert r.status_code == 422, f"rating {bad} should be rejected, got {r.status_code}"


# 6. a non-integer rating is rejected
def test_non_integer_rating_rejected(client):
    assert client.post(FEEDBACK, json={"conversation_id": cid(), "rating": "good"}).status_code == 422
    assert client.post(FEEDBACK, json={"conversation_id": cid(), "rating": 2.5}).status_code == 422


# 7. an invalid conversation_id is rejected
def test_invalid_conversation_id_rejected(client):
    for bad in ("not-a-uuid", "12345", "", "x" * 64, "urn:uuid:" + cid()):
        r = client.post(FEEDBACK, json={"conversation_id": bad, "rating": 3})
        assert r.status_code in (400, 422), f"{bad!r} should be rejected, got {r.status_code}"


# 8. a duplicate conversation_id is rejected
def test_duplicate_conversation_rejected(client):
    conversation = cid()
    assert client.post(FEEDBACK, json={"conversation_id": conversation, "rating": 3}).status_code == 200
    r = client.post(FEEDBACK, json={"conversation_id": conversation, "rating": 1})
    assert r.status_code == 409, r.text


# 9. a duplicate is rejected even with a different rating / different user
def test_duplicate_rejected_across_users_and_ratings(client, user_h, user2_h):
    conversation = cid()
    assert client.post(FEEDBACK, json={"conversation_id": conversation, "rating": 3},
                       headers=user_h).status_code == 200

    other = client.post(FEEDBACK, json={"conversation_id": conversation, "rating": 1},
                        headers=user2_h)
    assert other.status_code == 409, "a second user must not overwrite the first rating"

    anonymous = client.post(FEEDBACK, json={"conversation_id": conversation, "rating": 2})
    assert anonymous.status_code == 409

    # ...and the original rating is untouched.
    matching = [row for row in stored(client) if row["conversation_id"] == conversation]
    assert len(matching) == 1
    assert matching[0]["rating"] == 3


# 10. one authenticated user cannot attribute feedback to another user
def test_user_id_is_derived_from_jwt_never_from_body(client, user_h, user2_h):
    victim = client.get("/api/auth/me", headers=user2_h).json()
    attacker = client.get("/api/auth/me", headers=user_h).json()

    r = client.post(FEEDBACK, json={"conversation_id": cid(), "rating": 3, "user_id": victim["id"]},
                    headers=user_h)
    assert r.status_code == 200

    assert stored(client)[0]["user_id"] == attacker["id"]
    assert stored(client)[0]["user_id"] != victim["id"], "user_id in the body must be ignored"


# 11. an admin can see the feedback event in the audit log
def test_admin_sees_feedback_event_in_audit_log(client, admin_h):
    conversation = cid()
    assert client.post(FEEDBACK, json={"conversation_id": conversation, "rating": 3},
                       headers=admin_h).status_code == 200

    r = client.get("/api/admin/audit-logs?action=CHATBOT_EXPERIENCE_FEEDBACK", headers=admin_h)
    assert r.status_code == 200, r.text
    entries = r.json()
    assert len(entries) == 1, entries
    entry = entries[0]
    assert entry["action"] == "CHATBOT_EXPERIENCE_FEEDBACK"
    assert "Rating: 3 (Excellent)" in entry["details"]
    assert conversation in entry["details"]


# 12. the audit log records anonymous feedback too, with no user attached
def test_audit_event_recorded_for_anonymous_feedback(client, admin_h):
    conversation = cid()
    client.post(FEEDBACK, json={"conversation_id": conversation, "rating": 1})
    entry = client.get("/api/admin/audit-logs", headers=admin_h).json()[0]
    assert entry["action"] == "CHATBOT_EXPERIENCE_FEEDBACK"
    assert entry["user_id"] is None
    assert "Rating: 1 (Bad)" in entry["details"]


# 13. normal users cannot reach the audit log
def test_normal_user_cannot_read_audit_log(client, user_h, user2_h):
    assert client.get("/api/admin/audit-logs").status_code == 401
    assert client.get("/api/admin/audit-logs", headers=user_h).status_code == 403
    assert client.get("/api/admin/audit-logs", headers=user2_h).status_code == 403
    assert client.get("/api/admin/chat-feedback", headers=user_h).status_code == 403


# --- persistence details -------------------------------------------------


def test_feedback_row_persists_expected_columns(client, user_h):
    conversation = cid()
    client.post(FEEDBACK, json={"conversation_id": conversation, "rating": 2}, headers=user_h)

    rows = stored(client)
    assert len(rows) == 1
    row = rows[0]
    assert row["conversation_id"] == conversation
    assert row["rating"] == 2
    assert row["user_id"] is not None
    assert row["created_at"]


def test_duplicate_row_is_not_created(client):
    conversation = cid()
    client.post(FEEDBACK, json={"conversation_id": conversation, "rating": 3})
    client.post(FEEDBACK, json={"conversation_id": conversation, "rating": 3})
    rows = [r for r in stored(client) if r["conversation_id"] == conversation]
    assert len(rows) == 1


def test_an_invalid_token_still_allows_feedback(client):
    """A stale session must never cost a customer their rating."""
    conversation = cid()
    r = client.post(FEEDBACK, json={"conversation_id": conversation, "rating": 3},
                    headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 200, r.text


def test_audit_filter_and_limit(client, admin_h):
    for _ in range(3):
        client.post(FEEDBACK, json={"conversation_id": cid(), "rating": 3})

    everything = client.get("/api/admin/audit-logs?limit=200", headers=admin_h).json()
    assert len(everything) == 3
    assert all(e["action"] == audit_service.ACTION_CHATBOT_FEEDBACK for e in everything)

    ids = [e["id"] for e in everything]
    assert ids == sorted(ids, reverse=True), "audit log must be newest first"

    limited = client.get("/api/admin/audit-logs?limit=2", headers=admin_h).json()
    assert len(limited) == 2

    filtered = client.get("/api/admin/audit-logs?action=NOPE", headers=admin_h).json()
    assert filtered == []


def test_experience_labels_are_exactly_the_specified_three():
    assert audit_service.EXPERIENCE_LABELS == {1: "Bad", 2: "Neutral", 3: "Excellent"}


def test_admin_portal_still_works(client, admin_h):
    """Regression: the admin dashboard and other admin routes are unaffected."""
    stats = client.get("/api/admin/stats", headers=admin_h)
    assert stats.status_code == 200
    assert client.get("/api/admin/products", headers=admin_h).status_code == 200
    assert client.get("/api/admin/orders", headers=admin_h).status_code == 200
    assert client.get("/api/admin/users", headers=admin_h).status_code == 200