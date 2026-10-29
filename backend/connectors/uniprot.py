"""UniProtKB: protein sequences, names, functions and annotations. https://rest.uniprot.org"""

from mcp.server.mcpserver import MCPServer

from ._common import clip, request

BASE = "https://rest.uniprot.org/uniprotkb"
FIELDS = "accession,id,protein_name,gene_names,organism_name,length,reviewed,annotation_score"

server = MCPServer("uniprot", instructions="Search and read UniProtKB protein entries.")


@server.tool()
async def search_proteins(query: str, size: int = 10, reviewed_only: bool = True) -> list[dict]:
    """Search UniProtKB with its query syntax, e.g. 'gene:TP53 AND organism_id:9606' or 'kinase human'."""
    q = f"({query}) AND reviewed:true" if reviewed_only else query
    data = await request("GET", f"{BASE}/search", params={"query": q, "fields": FIELDS, "format": "json", "size": min(size, 50)})
    return [
        {
            "accession": r["primaryAccession"],
            "name": (r.get("proteinDescription", {}).get("recommendedName") or {}).get("fullName", {}).get("value"),
            "genes": [g["geneName"]["value"] for g in r.get("genes", []) if "geneName" in g],
            "organism": r.get("organism", {}).get("scientificName"),
            "length": r.get("sequence", {}).get("length"),
        }
        for r in data.get("results", [])
    ]


@server.tool()
async def get_protein(accession: str) -> dict:
    """A UniProtKB entry by accession (e.g. P04637): names, function, location, features and cross-references."""
    r = await request("GET", f"{BASE}/{accession}.json")
    comments = {c["commentType"]: c for c in r.get("comments", [])}
    function = comments.get("FUNCTION", {}).get("texts", [{}])[0].get("value")
    return clip({
        "accession": r["primaryAccession"],
        "name": (r.get("proteinDescription", {}).get("recommendedName") or {}).get("fullName", {}).get("value"),
        "organism": r.get("organism", {}).get("scientificName"),
        "function": function,
        "length": r.get("sequence", {}).get("length"),
        "features": [{"type": f["type"], "location": f["location"], "description": f.get("description")} for f in r.get("features", [])[:60]],
        "xrefs": {db: [x["id"] for x in r.get("uniProtKBCrossReferences", []) if x["database"] == db][:20] for db in ("PDB", "AlphaFoldDB", "Pfam", "Ensembl")},
    })


@server.tool()
async def get_sequence(accession: str) -> str:
    """The protein sequence of a UniProtKB entry, in FASTA format."""
    return await request("GET", f"{BASE}/{accession}.fasta", text=True)


if __name__ == "__main__":
    server.run()
