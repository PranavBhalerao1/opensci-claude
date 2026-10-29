"""AlphaFold Protein Structure Database: predicted structures for UniProt proteins. https://alphafold.ebi.ac.uk"""

from mcp.server.mcpserver import MCPServer

from ._common import request

server = MCPServer("alphafold", instructions="Predicted protein structures and confidence from AlphaFold DB.")


@server.tool()
async def get_prediction(uniprot_accession: str) -> list[dict]:
    """AlphaFold models for a UniProt accession: mean pLDDT confidence and coordinate/PAE file URLs."""
    data = await request("GET", f"https://alphafold.ebi.ac.uk/api/prediction/{uniprot_accession}")
    return [
        {
            "model": m.get("entryId"),
            "gene": m.get("gene"),
            "organism": m.get("organismScientificName"),
            "residues": f"{m.get('uniprotStart')}–{m.get('uniprotEnd')}",
            "mean_plddt": m.get("globalMetricValue"),
            "pdb_url": m.get("pdbUrl"),
            "cif_url": m.get("cifUrl"),
            "pae_url": m.get("paeDocUrl"),
            "version": m.get("latestVersion"),
        }
        for m in (data if isinstance(data, list) else [])
    ]


if __name__ == "__main__":
    server.run()
