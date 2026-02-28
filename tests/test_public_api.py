"""API tests for the public read-only server (server_public.py)."""
import pytest

from tests.conftest import KNXPROJ_ETS6, KNXPROJ_NOPASS


# ---------------------------------------------------------------------------
# Meta / static endpoints
# ---------------------------------------------------------------------------

async def test_mode_returns_public(public_client):
    r = await public_client.get("/api/mode")
    assert r.status_code == 200
    assert r.json() == {"public": True}


async def test_chrome_devtools_suppressed(public_client):
    r = await public_client.get("/.well-known/appspecific/com.chrome.devtools.json")
    assert r.status_code == 200
    assert r.json() == {}


# ---------------------------------------------------------------------------
# Private-only routes must not exist on the public server
# ---------------------------------------------------------------------------

async def test_gateway_not_available(public_client):
    r = await public_client.get("/api/gateway")
    assert r.status_code == 404


async def test_current_values_not_available(public_client):
    r = await public_client.get("/api/current-values")
    assert r.status_code == 404


async def test_annotations_not_available(public_client):
    r = await public_client.get("/api/annotations")
    assert r.status_code == 404


async def test_log_not_available(public_client):
    r = await public_client.get("/api/log")
    assert r.status_code == 404


async def test_last_project_info_not_available(public_client):
    r = await public_client.get("/api/last-project/info")
    assert r.status_code == 404


async def test_ws_not_available(public_client):
    r = await public_client.get("/ws")
    # FastAPI returns 403 for websocket upgrade on non-websocket route, or 404
    assert r.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Parse .knxproj  (also available on public server)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not KNXPROJ_ETS6.exists(), reason="Test resources not available")
async def test_parse_ets6_project(public_client):
    with open(KNXPROJ_ETS6, "rb") as f:
        r = await public_client.post(
            "/api/parse",
            files={"file": ("ets6_free.knxproj", f, "application/zip")},
            data={"password": "", "language": "de-DE"},
        )
    assert r.status_code == 200
    data = r.json()
    assert "devices" in data
    assert "group_addresses" in data


@pytest.mark.skipif(not KNXPROJ_NOPASS.exists(), reason="Test resources not available")
async def test_parse_no_password_project(public_client):
    with open(KNXPROJ_NOPASS, "rb") as f:
        r = await public_client.post(
            "/api/parse",
            files={"file": ("test.knxproj", f, "application/zip")},
            data={"password": "", "language": "de-DE"},
        )
    assert r.status_code == 200


async def test_parse_invalid_file_returns_error(public_client):
    r = await public_client.post(
        "/api/parse",
        files={"file": ("bad.knxproj", b"not a zip file", "application/zip")},
        data={"password": ""},
    )
    assert r.status_code in (422, 500)


@pytest.mark.skipif(
    not (KNXPROJ_ETS6.parent / "xknx_test_project.knxproj").exists(),
    reason="Test resources not available",
)
async def test_parse_wrong_password_returns_422(public_client):
    protected = KNXPROJ_ETS6.parent / "xknx_test_project.knxproj"
    with open(protected, "rb") as f:
        r = await public_client.post(
            "/api/parse",
            files={"file": ("test.knxproj", f, "application/zip")},
            data={"password": "definitely_wrong"},
        )
    assert r.status_code in (422, 500)
