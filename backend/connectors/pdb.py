"""RCSB Protein Data Bank: experimental 3D structures. https://www.rcsb.org"""

from mcp.server.mcpserver import MCPServer

from ._common import clip, request

server = MCPServer("pdb", instructions="Search and read experimental structures in the RCSB PDB.")


@server.tool()
async def search_structures(text: str, max_results: int = 10) -> list[str]:
    """Full-text search of the PDB (e.g. 'SARS-CoV-2 main protease'). Returns PDB ids, best match first."""
    query = {
        "query": {"type": "terminal", "service": "full_text", "parameters": {"value": text}},
        "return_type": "entry",
        "request_options": {"paginate": {"start": 0, "rows": min(max_results, 50)}},
    }
    data = await request("POST", "https://search.rcsb.org/rcsbsearch/v2/query", json_body=query)
    return [r["identifier"] for r in (data or {}).get("result_set", [])] if isinstance(data, dict) else []


@server.tool()
async def get_structure(pdb_id: str) -> dict:
    """Summary of a PDB entry: title, method, resolution, release date and polymer chains."""
    e = await request("GET", f"https://data.rcsb.org/rest/v1/core/entry/{pdb_id.upper()}")
    info = e.get("rcsb_entry_info", {})
    return clip({
        "id": e.get("rcsb_id"),
        "title": e.get("struct", {}).get("title"),
        "method": [m.get("method") for m in e.get("exptl", [])],
        "resolution_A": (info.get("resolution_combined") or [None])[0],
        "released": e.get("rcsb_accession_info", {}).get("initial_release_date"),
        "polymer_entities": info.get("polymer_entity_count"),
        "deposited_atoms": info.get("deposited_atom_count"),
        "citation": (e.get("citation") or [{}])[0].get("title"),
    })


@server.tool()
async def structure_file_url(pdb_id: str, file_format: str = "cif") -> str:
    """Download URL for a structure's coordinates ('cif' or 'pdb')."""
    return f"https://files.rcsb.org/download/{pdb_id.upper()}.{'pdb' if file_format == 'pdb' else 'cif'}"


if __name__ == "__main__":
    server.run()
