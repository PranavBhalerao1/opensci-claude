# OpenScientist Connectors

MCP servers that give an agent direct access to scientific databases, and the **Connector Forge**,
which builds a new connector for any HTTP API or experimentation server on demand.

Standalone for now: nothing here is wired into the agent toolset (`app/execution/tools.py`) or the
pipeline. Run everything from `backend/` with the `connectors` dependency group:

```bash
uv sync --group connectors
```

## Ready-made servers

| Server | Source | Tools |
| --- | --- | --- |
| `uniprot` | UniProtKB | `search_proteins`, `get_protein`, `get_sequence` |
| `pdb` | RCSB Protein Data Bank | `search_structures`, `get_structure`, `structure_file_url` |
| `alphafold` | AlphaFold DB | `get_prediction` |
| `ncbi` | NCBI E-utilities | `search_pubmed`, `get_abstract`, `search_genes` |
| `ensembl` | Ensembl REST | `lookup_gene`, `get_variant`, `get_sequence` |
| `chembl` | ChEMBL | `search_molecules`, `search_targets`, `get_activities` |

All use public APIs and need no key. NCBI accepts an optional `NCBI_API_KEY` for higher rate limits.
Rate-limited and 5xx responses are retried.

```bash
uv run --group connectors python -m connectors.uniprot      # serve over MCP (stdio)
```

## Connector Forge

Give the forge an OpenAPI/Swagger spec, or a base URL and a few endpoints, and it writes a complete
MCP server to `connectors/generated/<name>.py`:
- one tool per endpoint, with typed parameters;
- path placeholders URL-encoded;
- credentials read from an environment variable, never written into the code.

It then imports the new server, checks that every tool registers, and records it in
`generated/registry.json`. Code is generated from the structured spec only, so a spec cannot inject
code into a connector.

```bash
# From an OpenAPI spec (here: the EBI Proteins API → 40 tools)
uv run --group connectors python -m connectors.forge openapi ebi_proteins https://www.ebi.ac.uk/proteins/api/openapi.json --max-tools 40

uv run --group connectors python -m connectors.forge list                 # every connector
uv run --group connectors python -m connectors.forge tools pubchem        # a connector's tools
uv run --group connectors python -m connectors.forge call pubchem compound_properties '{"name": "aspirin", "properties": "MolecularWeight,XLogP"}'

uv run --group connectors python -m connectors.generated.ebi_proteins     # serve a forged connector
```

The forge is itself an MCP server (`python -m connectors.forge`). An agent connected to it can build
and use connectors on its own with these tools:
- `forge_connector_from_openapi`: build a connector from a spec URL.
- `forge_connector`: build one from endpoints, for APIs and instruments that have no spec.
- `list_connectors`: list every connector.
- `inspect_connector`: show one connector's tools.
- `call_connector`: call a tool on any connector.

For an API that needs a key, pass `credential_env_var` and `credential_header` (for example
`PLATE_KEY` and `X-API-Key`). The forged connector reads the key from the environment at call time.

Forged so far, as examples:
- `ebi_proteins`: EBI Proteins API, from its OpenAPI spec, 40 tools.
- `ols`: EBI Ontology Lookup Service, from its OpenAPI spec, 30 tools.
- `pubchem`: PubChem PUG REST, from three hand-written endpoints, since PubChem has no spec.

## Using them from an MCP client

Example Claude Desktop / MCP client configuration:

```json
{
  "mcpServers": {
    "uniprot": { "command": "uv", "args": ["run", "--group", "connectors", "python", "-m", "connectors.uniprot"], "cwd": "/path/to/backend" },
    "connector-forge": { "command": "uv", "args": ["run", "--group", "connectors", "python", "-m", "connectors.forge"], "cwd": "/path/to/backend" }
  }
}
```

## Tests

```bash
uv run --group connectors pytest tests/test_connectors.py
```
