"""Connectors (connectors/): the Connector Forge's code generation and a ready-made server, offline.

Needs the `connectors` dependency group: uv run --group connectors pytest tests/test_connectors.py
"""

import asyncio
import json

import pytest

pytest.importorskip("mcp")

from connectors import forge, uniprot  # noqa: E402

SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Lab instrument", "description": "<b>Plate reader</b> control"},
    "servers": [{"url": "/api/v1"}],
    "paths": {
        "/plates/{plate_id}": {"get": {"operationId": "getPlate", "summary": "Read a plate",
                                       "parameters": [{"name": "plate-id", "in": "path", "schema": {"type": "string"}}]}},
        "/plates/{plate_id}/read": {"post": {"operationId": "getPlate_1", "summary": "Start a read",
                                             "parameters": [{"name": "wavelength", "in": "query", "schema": {"type": "integer"}}],
                                             "requestBody": {"content": {}}}},
        "/runs": {"get": {"operationId": "class", "summary": "List runs\nmore text",
                          "parameters": [{"name": "limit", "in": "query", "required": True, "schema": {"type": "integer"}}]}},
    },
}


@pytest.fixture
def workshop(tmp_path, monkeypatch):
    monkeypatch.setattr(forge, "GENERATED", tmp_path)
    monkeypatch.setattr(forge, "REGISTRY", tmp_path / "registry.json")
    return tmp_path


def test_openapi_operations_become_tools_with_safe_unique_names():
    base, eps = forge.endpoints_from_openapi(SPEC)
    assert base == "/api/v1" and [e.method for e in eps] == ["get", "post", "get"]
    taken: set[str] = set()
    sources = [forge._tool_source(e, taken) for e in eps]
    assert taken == {"plates_get_plate", "plates_get_plate_2", "p_class"}  # repeats prefixed, keywords escaped
    assert "plate_id: str" in sources[0] and "{_q(plate_id)}" in sources[0]
    assert "wavelength: int | None = None, body: dict | None = None" in sources[1]
    assert sources[2].split("\n")[2].strip() == json.dumps("List runs")


def test_a_spec_cannot_inject_code(workshop):
    evil = forge.Endpoint('x"); import os; os.system("boom', "get", '/a"); import os #', 'doc"""; import os', [])
    code = forge.render("t", "https://x", [evil], description='""" import os')
    compile(code, "t.py", "exec")
    assert "os.system" not in code.split('"""')[-1].split("async def")[0]  # only ever inside literals


def test_forging_writes_loads_and_registers_a_connector(workshop, monkeypatch):
    calls = []

    async def fake_request(method, url, **kw):
        calls.append((method, url, kw.get("params"), kw.get("headers")))
        return {"ok": True}

    async def fake_spec(method, url, **kw):
        return SPEC

    monkeypatch.setattr(forge, "request", fake_spec)
    out = asyncio.run(forge.forge_openapi("Plate Reader", "https://lab.example/api/v1/openapi.json",
                                          auth_header="X-Key", auth_env="PLATE_KEY"))
    assert out["connector"] == "plate_reader" and len(out["tools"]) == 3
    registry = json.loads((workshop / "registry.json").read_text())
    assert registry["plate_reader"]["base_url"] == "https://lab.example/api/v1"
    assert registry["plate_reader"]["description"] == "Lab instrument — Plate reader control"

    module = forge._module("plate_reader")
    monkeypatch.setattr(module, "request", fake_request)
    monkeypatch.setenv("PLATE_KEY", "s3cret")
    assert asyncio.run(forge.call("plate_reader", "plates_get_plate", {"plate_id": "A/1"})) == {"ok": True}
    assert calls[-1][1] == "https://lab.example/api/v1/plates/A%2F1" and calls[-1][3] == {"X-Key": "s3cret"}
    asyncio.run(forge.call("plate_reader", "p_class", {"limit": 5}))
    assert calls[-1][2] == {"limit": 5}


def test_a_ready_made_name_cannot_be_overwritten(workshop):
    with pytest.raises(ValueError, match="ready-made"):
        asyncio.run(forge.forge("uniprot", "https://x", [forge.Endpoint("a", "get", "/a")]))


def test_uniprot_search_returns_compact_records(monkeypatch):
    async def fake(method, url, **kw):
        assert kw["params"]["query"] == "(insulin) AND reviewed:true"
        return {"results": [{"primaryAccession": "P01308", "organism": {"scientificName": "Homo sapiens"},
                             "proteinDescription": {"recommendedName": {"fullName": {"value": "Insulin"}}},
                             "genes": [{"geneName": {"value": "INS"}}], "sequence": {"length": 110}}]}

    monkeypatch.setattr(uniprot, "request", fake)
    assert asyncio.run(uniprot.search_proteins("insulin")) == [
        {"accession": "P01308", "name": "Insulin", "genes": ["INS"], "organism": "Homo sapiens", "length": 110}]
