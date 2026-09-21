import pytest

from kev_mcp.config import Settings


def test_settings_use_local_defaults_and_private_store(monkeypatch, tmp_path):
    monkeypatch.delenv("KEV_BASE_URL", raising=False)
    monkeypatch.delenv("KEV_MODEL", raising=False)
    monkeypatch.delenv("KEV_API_KEY", raising=False)
    monkeypatch.setenv("KEV_MCP_DB", str(tmp_path / "store.sqlite3"))

    settings = Settings.from_env()

    assert settings.base_url == "http://127.0.0.1:8009"
    assert settings.model == "kev-latest"
    assert settings.api_key == "local"
    assert settings.db_path == tmp_path / "store.sqlite3"
    assert settings.timeout == 120.0


def test_settings_reject_invalid_positive_bounds(monkeypatch):
    monkeypatch.setenv("KEV_TIMEOUT", "0")
    with pytest.raises(ValueError, match="KEV_TIMEOUT"):
        Settings.from_env()


def test_remote_http_requires_bearer_token(monkeypatch):
    monkeypatch.setenv("KEV_MCP_HOST", "0.0.0.0")
    monkeypatch.delenv("KEV_MCP_TOKEN", raising=False)
    with pytest.raises(ValueError, match="KEV_MCP_TOKEN"):
        Settings.from_env(transport="streamable-http")


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_timeout_must_be_finite(monkeypatch, value):
    monkeypatch.setenv("KEV_TIMEOUT", value)
    with pytest.raises(ValueError, match="KEV_TIMEOUT"):
        Settings.from_env()


def test_backend_url_credentials_and_query_are_rejected(monkeypatch):
    monkeypatch.setenv("KEV_BASE_URL", "http://user:pass@127.0.0.1:8009/path?secret=x")
    with pytest.raises(ValueError, match="KEV_BASE_URL"):
        Settings.from_env()


def test_all_interface_bind_requires_explicit_host_allowlist(monkeypatch):
    monkeypatch.setenv("KEV_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("KEV_MCP_TOKEN", "token")
    with pytest.raises(ValueError, match="KEV_MCP_ALLOWED_HOSTS"):
        Settings.from_env(transport="streamable-http")


def test_settings_parse_http_options(monkeypatch, tmp_path):
    monkeypatch.setenv("KEV_BASE_URL", "http://127.0.0.1:8010/")
    monkeypatch.setenv("KEV_MODEL", "kev-4b")
    monkeypatch.setenv("KEV_API_KEY", "test-key")
    monkeypatch.setenv("KEV_MCP_DB", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("KEV_MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("KEV_MCP_PORT", "9010")
    monkeypatch.setenv("KEV_MCP_TOKEN", "http-token")

    settings = Settings.from_env(transport="streamable-http")

    assert settings.base_url == "http://127.0.0.1:8010"
    assert settings.model == "kev-4b"
    assert settings.port == 9010
    assert settings.token == "http-token"


@pytest.mark.parametrize("port", ["0", "-1", "65536"])
def test_cli_rejects_invalid_port_before_starting(monkeypatch, port):
    from kev_mcp import server

    def must_not_start(*args, **kwargs):
        raise AssertionError("invalid port reached server startup")

    monkeypatch.setattr(server, "create_server", must_not_start)
    with pytest.raises(ValueError, match="port"):
        server.main(["--transport", "streamable-http", "--port", port])
