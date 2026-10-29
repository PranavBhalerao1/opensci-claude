"""OpenScientist connectors: MCP servers for scientific databases, and the Connector Forge.

Standalone for now: nothing here is wired into the agent toolset (app/execution/tools.py).
Each module is a runnable MCP server, e.g. `uv run --group connectors python -m connectors.uniprot`.
See connectors/README.md.
"""

# Ready-made servers: module name → one-line summary.
SERVERS = {
    "uniprot": "Protein sequences, names, functions and annotations (UniProtKB)",
    "pdb": "Experimental 3D structures (RCSB Protein Data Bank)",
    "alphafold": "Predicted structures and confidence for any UniProt protein (AlphaFold DB)",
    "ncbi": "PubMed literature and NCBI Gene records (E-utilities)",
    "ensembl": "Genes, transcripts, variants and sequences (Ensembl REST)",
    "chembl": "Bioactive molecules, targets and assay activities (ChEMBL)",
}
