import datetime

from jose import jwt

from app.services import llm_client, usage_limits


def test_health(client):
    assert client.get("/health").json() == {"status": "healthy"}


def test_forged_token_rejected(client, auth):
    user_id = client.get("/api/v1/auth/me", headers=auth).json()["id"]
    forged = jwt.encode(
        {"sub": user_id, "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=5)},
        "your-secret-key-change-in-production",
        algorithm="HS256",
    )
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_admin_endpoints_disabled_without_key(client):
    assert client.post("/api/v1/admin/send-weekly-quizzes").status_code == 403
    assert client.post("/api/v1/test/send-quiz-email/x", headers={"X-Admin-Key": "guess"}).status_code == 403


def test_self_service_upgrade_removed(client, auth):
    assert client.post("/api/v1/auth/subscription", json={"tier": "premium"}, headers=auth).status_code in (404, 405)
    assert client.post("/api/v1/auth/reset-usage", headers=auth).status_code in (404, 405)


def test_question_answer_with_evidence_and_followups(client, auth):
    chat_id = client.post("/api/v1/chats", json={"title": "t"}, headers=auth).json()["id"]
    r = client.post(f"/api/v1/chats/{chat_id}/messages", json={"question": "What is inertia?"}, headers=auth)
    assert r.status_code == 200
    message = r.json()["assistant_message"]
    assert len(message["evidence"]) == 5
    assert "[1]" in message["content"] and "**Key terms**" in message["content"]
    assert message["metadata"]["conf"] == "High"
    assert len(message["metadata"]["followups"]) == 2

    chats = client.get("/api/v1/chats", headers=auth).json()
    assert chats[0]["message_count"] == 2


def test_quiz_generation_and_ownership(client, auth):
    chat_id = client.post("/api/v1/chats", json={"title": "t"}, headers=auth).json()["id"]
    client.post(f"/api/v1/chats/{chat_id}/messages", json={"question": "What is inertia?"}, headers=auth)
    quiz = client.post(f"/api/v1/chats/{chat_id}/quiz", headers=auth).json()["quiz"]
    assert len(quiz) == 5 and all(q["correct_answer"] in q["options"] for q in quiz)

    other = client.post(
        "/api/v1/auth/register",
        json={"username": "intruder", "email": "intruder@example.invalid", "password": "Test-pass-123"},
        headers={"X-Client-IP": "81.2.69.162"},
    )
    assert other.status_code == 200
    token = client.post("/api/v1/auth/login-json", json={"username": "intruder", "password": "Test-pass-123"}).json()["access_token"]
    assert client.post(f"/api/v1/chats/{chat_id}/quiz", headers={"Authorization": f"Bearer {token}"}).status_code == 404


def test_per_user_daily_limit(client, auth, monkeypatch):
    monkeypatch.setattr(usage_limits, "USER_DAILY_ACTION_LIMIT", 2)
    chat_id = client.post("/api/v1/chats", json={"title": "t"}, headers=auth).json()["id"]
    for _ in range(2):
        assert client.post(f"/api/v1/chats/{chat_id}/messages", json={"question": "What is force?"}, headers=auth).status_code == 200
    r = client.post(f"/api/v1/chats/{chat_id}/messages", json={"question": "What is force?"}, headers=auth)
    assert r.status_code == 429 and "free actions" in r.json()["detail"]


def test_global_llm_budget_returns_friendly_429_not_500(client, auth, monkeypatch):
    monkeypatch.setattr(llm_client, "DAILY_LLM_CALL_LIMIT", 0)
    chat_id = client.post("/api/v1/chats", json={"title": "t"}, headers=auth).json()["id"]
    r = client.post(f"/api/v1/chats/{chat_id}/messages", json={"question": "What is force?"}, headers=auth)
    assert r.status_code == 429 and "daily AI limit" in r.json()["detail"]


def test_model_fallback_when_rate_limited(client, auth, fake_llm):
    fake_llm.rate_limited_models = {llm_client.LLM_MODELS[0]}
    r = client.post("/api/v1/ask", json={"question": "What is inertia?"}, headers=auth)
    assert r.status_code == 200
    assert [c["model"] for c in fake_llm.calls] == llm_client.LLM_MODELS[:2]


def test_all_models_rate_limited_is_busy_message(client, auth, fake_llm):
    fake_llm.rate_limited_models = set(llm_client.LLM_MODELS)
    r = client.post("/api/v1/ask", json={"question": "What is inertia?"}, headers=auth)
    assert r.status_code == 429 and "busy" in r.json()["detail"]
    # Waits for Retry-After and tries every model once more before giving up
    assert len(fake_llm.calls) == 2 * len(llm_client.LLM_MODELS)


def test_signup_limit_per_ip(client):
    def signup(name, ip):
        return client.post(
            "/api/v1/auth/register",
            json={"username": name, "email": f"{name}@example.invalid", "password": "Test-pass-123"},
            headers={"X-Client-IP": ip},
        )

    assert [signup(f"ipuser{i}", "81.2.69.160").status_code for i in range(3)] == [200, 200, 200]
    assert signup("ipuser3", "81.2.69.160").status_code == 429
    assert signup("ipuser4", "81.2.69.161").status_code == 200


def test_signup_without_visitor_ip_uses_shared_cap(client, monkeypatch):
    monkeypatch.setattr(usage_limits, "SIGNUPS_PER_HOUR_GLOBAL", 5)
    # A private address means a proxy hid the visitor: don't lump everyone into one per-IP bucket of 3
    codes = [
        client.post(
            "/api/v1/auth/register",
            json={"username": f"proxied{i}", "email": f"proxied{i}@example.invalid", "password": "Test-pass-123"},
            headers={"X-Client-IP": "10.0.0.5"},
        ).status_code
        for i in range(6)
    ]
    assert codes == [200] * 5 + [429]


def test_upload_size_limit(client, auth):
    r = client.post("/api/v1/documents/process", headers=auth, files={"file": ("big.pdf", b"0" * (11 * 1024 * 1024), "application/pdf")})
    assert r.status_code == 413
