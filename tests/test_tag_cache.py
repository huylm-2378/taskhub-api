from functools import lru_cache
from unittest.mock import Mock

import fakeredis
import pytest

import config
from crud import tags
from services import tag_cache


@pytest.fixture
def cached_client(client, monkeypatch):
    server = fakeredis.FakeServer()
    cache = fakeredis.FakeRedis(server=server, decode_responses=True)
    monkeypatch.setattr(tag_cache, "get_client", lru_cache(maxsize=1)(lambda: cache))
    read = Mock(wraps=tags.list_tags)
    monkeypatch.setattr(tags, "list_tags", read)
    yield client, cache, server, read
    cache.close()


def create_tag(client, name):
    response = client.post("/api/tags", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def test_cache_hit_pagination_and_empty_list(cached_client):
    client, cache, _, read = cached_client
    assert client.get("/api/tags").json() == []
    assert client.get("/api/tags").json() == []
    assert read.call_count == 1
    created = [create_tag(client, name) for name in ("backend", "frontend")]
    read.reset_mock()
    for offset in (0, 1, 2):
        for _ in range(2):
            response = client.get(f"/api/tags?offset={offset}&limit=1")
            assert response.status_code == 200
            assert response.json() == created[offset:offset + 1]
    assert read.call_count == 3
    keys = [key for key in cache.scan_iter(f"{config.TAGS_CACHE_PREFIX}:*") if not key.endswith(":generation")]
    assert keys and all(0 < cache.ttl(key) <= config.TAGS_CACHE_TTL_SECONDS for key in keys)


def test_successful_mutations_invalidate_all_pages(cached_client):
    client, _, _, read = cached_client
    first = create_tag(client, "first")
    second = create_tag(client, "second")
    page0, page1 = "/api/tags?limit=1", "/api/tags?offset=1&limit=1"
    assert client.get(page0).json() == [first]
    assert client.get(page1).json() == [second]
    renamed = client.patch(f"/api/tags/{first['id']}", json={"name": "renamed"})
    assert renamed.status_code == 200
    read.reset_mock()
    assert client.get(page0).json() == [renamed.json()]
    assert client.get(page1).json() == [second]
    assert read.call_count == 2
    assert len(client.get("/api/tags").json()) == 2
    create_tag(client, "third")
    assert len(client.get("/api/tags").json()) == 3


def test_failed_mutations_keep_valid_cache(cached_client):
    client, _, _, read = cached_client
    first = create_tag(client, "first")
    second = create_tag(client, "second")
    expected = client.get("/api/tags").json()
    read.reset_mock()
    assert client.post("/api/tags", json={"name": "first"}).status_code == 409
    assert client.patch(f"/api/tags/{second['id']}", json={"name": first["name"]}).status_code == 409
    assert client.post("/api/tags", json={"name": " "}).status_code == 422
    assert client.get("/api/tags").json() == expected
    read.assert_not_called()


def test_redis_outage_falls_back_for_reads_and_writes(cached_client):
    client, _, server, read = cached_client
    first = create_tag(client, "first")
    assert client.get("/api/tags").json() == [first]
    server.connected = False
    read.reset_mock()
    second = create_tag(client, "second")
    updated = client.patch(f"/api/tags/{first['id']}", json={"name": "updated"})
    assert updated.status_code == 200
    assert client.get("/api/tags").json() == [updated.json(), second]
    assert read.call_count == 1


def test_corrupt_and_expired_entries_are_reloaded(cached_client):
    client, cache, _, read = cached_client
    first = create_tag(client, "first")
    assert client.get("/api/tags").json() == [first]
    generation = cache.get(f"{config.TAGS_CACHE_PREFIX}:generation")
    key = f"{config.TAGS_CACHE_PREFIX}:{generation}:0:20"
    for value in ("not-json", '[{"id":"invalid"}]', "null"):
        cache.set(key, value)
        assert client.get("/api/tags").json() == [first]
        assert cache.ttl(key) > 0
    cache.pexpire(key, 0)
    assert client.get("/api/tags").json() == [first]
    assert read.call_count == 5


def test_inflight_read_cannot_refill_current_generation(cached_client, monkeypatch):
    client, _, _, read = cached_client
    first = create_tag(client, "first")

    def invalidate_during_read(*args):
        result = read(*args)
        tag_cache.invalidate()
        return result

    monkeypatch.setattr(tags, "list_tags", invalidate_during_read)
    assert client.get("/api/tags").json() == [first]
    monkeypatch.setattr(tags, "list_tags", read)
    assert client.get("/api/tags").json() == [first]
    assert read.call_count == 2
    assert client.get("/api/tags").json() == [first]
    assert read.call_count == 2


def test_cache_does_not_bypass_authentication(cached_client):
    from main import api as app
    from routers.dependencies import get_current_user

    client, _, _, read = cached_client
    first = create_tag(client, "first")
    assert client.get("/api/tags").json() == [first]
    override = app.dependency_overrides.pop(get_current_user)
    try:
        assert client.get("/api/tags").status_code == 401
        assert client.get("/api/tags", headers={"Authorization": "Bearer bad"}).status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = override
    assert read.call_count == 1


def test_cache_disabled_reads_database(client, monkeypatch):
    monkeypatch.setattr(config, "REDIS_URL", "")
    tag_cache.close_cache()
    read = Mock(wraps=tags.list_tags)
    monkeypatch.setattr(tags, "list_tags", read)
    assert client.get("/api/tags").json() == []
    assert client.get("/api/tags").json() == []
    assert read.call_count == 2
