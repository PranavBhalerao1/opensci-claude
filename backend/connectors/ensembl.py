"""Ensembl REST: genes, transcripts, variants and sequences across species. https://rest.ensembl.org"""

from mcp.server.mcpserver import MCPServer

from ._common import clip, request

BASE = "https://rest.ensembl.org"
JSON = {"Content-Type": "application/json"}

server = MCPServer("ensembl", instructions="Look up genes, variants and sequences in Ensembl.")


@server.tool()
async def lookup_gene(symbol: str, species: str = "homo_sapiens") -> dict:
    """A gene by symbol (e.g. 'TP53'): Ensembl id, location, biotype and transcripts."""
    g = await request("GET", f"{BASE}/lookup/symbol/{species}/{symbol}", params={"expand": 1}, headers=JSON)
    return clip({
        "id": g.get("id"), "symbol": g.get("display_name"), "description": g.get("description"), "biotype": g.get("biotype"),
        "location": f"{g.get('seq_region_name')}:{g.get('start')}-{g.get('end')}:{g.get('strand')}",
        "transcripts": [{"id": t["id"], "biotype": t.get("biotype"), "canonical": bool(t.get("is_canonical"))} for t in g.get("Transcript", [])[:30]],
    })


@server.tool()
async def get_variant(variant_id: str, species: str = "homo_sapiens") -> dict:
    """A variant by id (e.g. 'rs699'): alleles, location, consequence and clinical significance."""
    v = await request("GET", f"{BASE}/variation/{species}/{variant_id}", headers=JSON)
    return clip({
        "id": v.get("name"), "class": v.get("var_class"), "consequence": v.get("most_severe_consequence"),
        "minor_allele": v.get("minor_allele"), "maf": v.get("MAF"), "clinical_significance": v.get("clinical_significance"),
        "mappings": [{"location": m.get("location"), "alleles": m.get("allele_string")} for m in v.get("mappings", [])[:5]],
    })


@server.tool()
async def get_sequence(ensembl_id: str, sequence_type: str = "protein") -> str:
    """Sequence for an Ensembl id; type is 'genomic', 'cdna', 'cds' or 'protein'."""
    data = await request("GET", f"{BASE}/sequence/id/{ensembl_id}", params={"type": sequence_type, "multiple_sequences": 1}, headers=JSON)
    seqs = data if isinstance(data, list) else [data]
    return clip("\n".join(f">{s.get('id')}\n{s.get('seq')}" for s in seqs))


if __name__ == "__main__":
    server.run()
