"""
Test setup: an isolated SQLite database and a fake LLM endpoint, so tests are free, fast and need no API key.
Configuration is read at import time, so the environment is set before the app is imported.
"""
import json
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="edureflect-tests-")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "GROQ_API_KEY": "test-key",
    "SECRET_KEY": "test-secret-key-0123456789abcdef0123456789abcdef",
    "EMBEDDED_BACKEND": "false",
    "LLM_MAX_RETRY_WAIT": "0",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database.models import SessionLocal, UsageCounter  # noqa: E402
from app.main import app  # noqa: E402
from app.services import llm_client, usage_limits  # noqa: E402

ANSWER = {
    "answer": "Inertia keeps an object at rest or in uniform motion unless a force acts on it [1].",
    "key_terms": [{"term": "Inertia", "definition": "Resistance to a change in motion"}],
    "followups": ["What is Newton's second law?", "How is mass related to inertia?"],
    "coverage": "full",
}
QUIZ = {
    "questions": [
        {"question": f"Question {i}?", "options": ["A1", "B1", "C1", "D1"], "correct_answer": "A1",
         "explanation": "Because.", "difficulty": "easy"}
        for i in range(5)
    ]
}


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def fake_completion(content: dict) -> FakeResponse:
    return FakeResponse(payload={"choices": [{"message": {"content": json.dumps(content)}}]})


class FakeLLM:
    """Stands in for the provider's HTTP API; records calls and can be told to rate-limit."""

    def __init__(self):
        self.calls = []
        self.rate_limited_models = set()

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.calls.append(json)
        if json["model"] in self.rate_limited_models:
            return FakeResponse(429, headers={"retry-after": "0"})
        prompt = " ".join(m["content"] for m in json["messages"])
        if "multiple-choice" in prompt:
            return fake_completion(QUIZ)
        if '"summary"' in prompt:
            return fake_completion({"summary": "A short summary of the document."})
        return fake_completion(ANSWER)


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm_client.requests, "post", fake)
    return fake


@pytest.fixture(autouse=True)
def reset_limits():
    usage_limits._signups.clear()
    db = SessionLocal()
    db.query(UsageCounter).delete()
    db.commit()
    db.close()


@pytest.fixture(scope="session")
def client():
    # Connect from localhost like the Streamlit frontend does, so X-Client-IP is honoured
    with TestClient(app, client=("127.0.0.1", 50000)) as c:
        yield c


_user_seq = iter(range(10**6))


@pytest.fixture
def auth(client):
    """Register and log in a fresh user; returns auth headers."""
    n = next(_user_seq)
    username = f"user{n}"
    client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@example.invalid", "password": "Test-pass-123"},
        headers={"X-Client-IP": f"81.2.70.{n % 250}"},
    )
    token = client.post("/api/v1/auth/login-json", json={"username": username, "password": "Test-pass-123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
