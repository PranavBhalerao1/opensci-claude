"""NCBI E-utilities: PubMed literature and Gene records. https://www.ncbi.nlm.nih.gov/books/NBK25501/

Set NCBI_API_KEY to raise NCBI's rate limit from 3 to 10 requests per second (optional).
"""

import os
import re

from mcp.server.mcpserver import MCPServer

from ._common import request

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

server = MCPServer("ncbi", instructions="Search PubMed and NCBI Gene.")


def _params(**kw) -> dict:
    return {**kw, "retmode": "json", "tool": "openscientist", "api_key": os.environ.get("NCBI_API_KEY")}


async def _summaries(db: str, ids: list[str]) -> dict:
    if not ids:
        return {}
    data = await request("GET", f"{EUTILS}/esummary.fcgi", params=_params(db=db, id=",".join(ids)))
    result = data.get("result", {})
    return {i: result[i] for i in result.get("uids", [])}


@server.tool()
async def search_pubmed(query: str, max_results: int = 10) -> list[dict]:
    """Search PubMed (e.g. 'sleep spindles memory consolidation'). Returns PMID, title, journal, year, authors."""
    found = await request("GET", f"{EUTILS}/esearch.fcgi", params=_params(db="pubmed", term=query, retmax=min(max_results, 50), sort="relevance"))
    ids = found.get("esearchresult", {}).get("idlist", [])
    docs = await _summaries("pubmed", ids)
    return [
        {"pmid": i, "title": d.get("title"), "journal": d.get("fulljournalname"), "year": (d.get("pubdate") or "")[:4],
         "authors": [a["name"] for a in d.get("authors", [])[:6]], "doi": next((x["value"] for x in d.get("articleids", []) if x.get("idtype") == "doi"), None)}
        for i, d in docs.items()
    ]


@server.tool()
async def get_abstract(pmid: str) -> str:
    """The title and abstract of a PubMed article, as plain text."""
    return await request("GET", f"{EUTILS}/efetch.fcgi", params={"db": "pubmed", "id": pmid, "rettype": "abstract", "retmode": "text",
                                                                  "api_key": os.environ.get("NCBI_API_KEY")}, text=True)


@server.tool()
async def search_genes(query: str, organism: str = "human", max_results: int = 10) -> list[dict]:
    """Search NCBI Gene (e.g. 'BRCA1'). Returns gene id, symbol, name, location and summary."""
    # A bare symbol ("BRCA1") matches that gene; free text matches any gene mentioning it.
    term = f"{query}[sym]" if re.fullmatch(r"[A-Za-z0-9-]+", query.strip()) else f"({query})"
    if organism:
        term += f" AND {organism}[orgn]"
    found = await request("GET", f"{EUTILS}/esearch.fcgi", params=_params(db="gene", term=term, retmax=min(max_results, 50)))
    docs = await _summaries("gene", found.get("esearchresult", {}).get("idlist", []))
    return [
        {"gene_id": i, "symbol": d.get("name"), "name": d.get("description"), "chromosome": d.get("chromosome"),
         "location": d.get("maplocation"), "summary": (d.get("summary") or "")[:600]}
        for i, d in docs.items()
    ]


if __name__ == "__main__":
    server.run()
