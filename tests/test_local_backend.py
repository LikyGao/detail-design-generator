from pathlib import Path
from fastapi.testclient import TestClient
from local_backend.app import APP_HEADER, APP_HEADER_VALUE, create_app
from local_backend import desktop

ROOT = Path(__file__).resolve().parents[1]

def test_health_and_application_identity():
    response = TestClient(create_app()).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers[APP_HEADER] == APP_HEADER_VALUE

def test_root_returns_current_html_verbatim():
    response = TestClient(create_app()).get("/")
    assert response.status_code == 200
    assert response.content == (ROOT / "基本設計書generator.html").read_bytes()
    assert response.headers[APP_HEADER] == APP_HEADER_VALUE

def test_activate_endpoint_calls_existing_window_callback():
    calls = []
    response = TestClient(create_app(lambda: calls.append("activate"))).post("/api/app/activate")
    assert response.status_code == 204
    assert response.headers[APP_HEADER] == APP_HEADER_VALUE
    assert calls == ["activate"]

def test_existing_instance_requires_health_payload_and_identity_header(monkeypatch):
    class Response:
        headers = {APP_HEADER: APP_HEADER_VALUE}
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self): return b'{"status":"ok"}'
    monkeypatch.setattr(desktop, "_request", lambda *_args, **_kwargs: Response())
    assert desktop.is_existing_instance()
    Response.headers = {}
    assert not desktop.is_existing_instance()

def test_second_instance_activates_without_starting_backend(monkeypatch):
    monkeypatch.setattr(desktop, "acquire_single_instance_mutex", lambda: False)
    monkeypatch.setattr(desktop, "activate_existing_instance", lambda: True)
    monkeypatch.setattr(desktop, "start_backend", lambda: (_ for _ in ()).throw(AssertionError()))
    assert desktop.run_desktop() == 0
