"""ChEMBL: bioactive molecules, drug targets and assay activities. https://www.ebi.ac.uk/chembl/"""

from mcp.server.mcpserver import MCPServer

from ._common import request

BASE = "https://www.ebi.ac.uk/chembl/api/data"

server = MCPServer("chembl", instructions="Search molecules, targets and bioactivities in ChEMBL.")


def _molecule(m: dict) -> dict:
    props = m.get("molecule_properties") or {}
    return {
        "chembl_id": m.get("molecule_chembl_id"), "name": m.get("pref_name"), "max_phase": m.get("max_phase"),
        "smiles": (m.get("molecule_structures") or {}).get("canonical_smiles"),
        "mw": props.get("full_mwt"), "alogp": props.get("alogp"), "hbd": props.get("hbd"), "hba": props.get("hba"),
    }


@server.tool()
async def search_molecules(query: str, limit: int = 10) -> list[dict]:
    """Search molecules by name or synonym (e.g. 'imatinib'). Returns ChEMBL id, phase, SMILES and properties."""
    data = await request("GET", f"{BASE}/molecule/search.json", params={"q": query, "limit": min(limit, 50)})
    return [_molecule(m) for m in data.get("molecules", [])]


@server.tool()
async def search_targets(query: str, limit: int = 10) -> list[dict]:
    """Search drug targets (e.g. 'EGFR'). Returns target ChEMBL id, name, type and organism."""
    data = await request("GET", f"{BASE}/target/search.json", params={"q": query, "limit": min(limit, 50)})
    return [{"chembl_id": t.get("target_chembl_id"), "name": t.get("pref_name"), "type": t.get("target_type"), "organism": t.get("organism")}
            for t in data.get("targets", [])]


@server.tool()
async def get_activities(target_chembl_id: str, activity_type: str = "IC50", limit: int = 25) -> list[dict]:
    """Measured activities against a target (e.g. CHEMBL203, type 'IC50' or 'Ki'), with molecule, value and units."""
    data = await request("GET", f"{BASE}/activity.json",
                         params={"target_chembl_id": target_chembl_id, "standard_type": activity_type, "limit": min(limit, 100)})
    return [{"molecule": a.get("molecule_chembl_id"), "type": a.get("standard_type"), "relation": a.get("standard_relation"),
             "value": a.get("standard_value"), "units": a.get("standard_units"), "assay": a.get("assay_chembl_id"),
             "pchembl": a.get("pchembl_value")} for a in data.get("activities", [])]


if __name__ == "__main__":
    server.run()
