async def test_health_returns_200(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


async def test_health_body_status_ok(client):
    resp = await client.get("/health")
    assert resp.json()["status"] == "ok"


async def test_health_body_version_present(client):
    resp = await client.get("/health")
    assert resp.json()["version"] == "0.1.0"


async def test_health_content_type_is_json(client):
    resp = await client.get("/health")
    assert "application/json" in resp.headers["content-type"]


async def test_health_response_has_no_extra_keys(client):
    resp = await client.get("/health")
    assert set(resp.json().keys()) == {"status", "version"}
