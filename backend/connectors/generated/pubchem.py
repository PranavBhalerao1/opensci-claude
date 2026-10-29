"""pubchem: forged by the OpenScientist Connector Forge on 2026-10-29.

PubChem compounds: properties, synonyms and bioassay summaries (PUG REST)

Base URL: https://pubchem.ncbi.nlm.nih.gov/rest/pug
"""

from typing import Any
from urllib.parse import quote

from mcp.server.mcpserver import MCPServer

from connectors._common import auth_headers, clip, request

BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
server = MCPServer("pubchem", instructions="PubChem compounds: properties, synonyms and bioassay summaries (PUG REST)")


def _q(value: Any) -> str:
    return quote(str(value), safe="")


def _auth() -> dict:
    return auth_headers(None, None, '')


@server.tool()
async def compound_properties(name: str, properties: str) -> Any:
    "Properties of a compound by name, e.g. properties=MolecularFormula,MolecularWeight,XLogP,CanonicalSMILES"
    return clip(await request("GET", BASE + f"/compound/name/{_q(name)}/property/{_q(properties)}/JSON", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def compound_synonyms(name: str) -> Any:
    "Synonyms of a compound"
    return clip(await request("GET", BASE + f"/compound/name/{_q(name)}/synonyms/JSON", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def compound_assay_summary(cid: str) -> Any:
    "Bioassay results for a compound id (CID)"
    return clip(await request("GET", BASE + f"/compound/cid/{_q(cid)}/assaysummary/JSON", params={},
                              json_body=None, headers=_auth()))


if __name__ == "__main__":
    server.run()
