"""Catalog of scientific services, data repositories and software across fields.

Agents reach APIs through the generic `http_request` tool and install software
with `install_packages`; this catalog tells them (and the Blueprint Agent) what
exists, how to call it, and what it requires. It is data, so covering a new
field means adding entries, not code.

`requires` lists runtime capabilities (see e2b_sandbox.E2BSandbox.capabilities);
anything unmet is flagged by the Blueprint Agent instead of failing mid-run.
"""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Resource:
    name: str
    kind: str  # api | data_repository | software
    fields: tuple[str, ...]
    description: str
    docs: str
    usage: str  # how an agent should call or install it
    auth: str = "none"  # none | api_key:<ENV_VAR> (user must supply) | account
    requires: tuple[str, ...] = field(default_factory=lambda: ("internet",))

    def as_dict(self) -> dict:
        return asdict(self)


R = Resource
CATALOG: tuple[Resource, ...] = (
    # ── Literature & general data ──────────────────────────────────────────
    R("Semantic Scholar", "api", ("all",), "Papers, abstracts, citations, TLDRs.",
      "https://api.semanticscholar.org/api-docs/", "Use the search_papers tool."),
    R("OpenAlex", "api", ("all",), "Open catalog of works, authors, institutions, concepts.",
      "https://docs.openalex.org", "GET https://api.openalex.org/works?filter=title_and_abstract.search:<q>"),
    R("arXiv API", "api", ("physics", "math", "cs", "biology", "economics"), "Preprint metadata and PDFs.",
      "https://info.arxiv.org/help/api/", "GET http://export.arxiv.org/api/query?search_query=all:<q>"),
    R("Europe PMC", "api", ("biomedicine", "life sciences"), "Biomedical literature with open full text.",
      "https://europepmc.org/RestfulWebService", "GET https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=<q>&format=json"),
    R("Zenodo", "data_repository", ("all",), "General research data and software deposits (DOIs).",
      "https://developers.zenodo.org", "GET https://zenodo.org/api/records?q=<q>; files under record['files']"),
    R("Figshare", "data_repository", ("all",), "Research outputs and datasets.",
      "https://docs.figshare.com", "POST https://api.figshare.com/v2/articles/search {\"search_for\": \"<q>\"}"),
    R("Dryad", "data_repository", ("ecology", "biology", "earth science"), "Curated research data behind papers.",
      "https://datadryad.org/api/v2/docs", "GET https://datadryad.org/api/v2/search?q=<q>"),
    R("OSF", "data_repository", ("psychology", "social science", "all"), "Preregistrations, study materials, data.",
      "https://developer.osf.io", "GET https://api.osf.io/v2/nodes/?filter[title]=<q>"),
    R("Hugging Face Hub", "data_repository", ("ml", "nlp", "biology", "all"), "Datasets and pretrained models.",
      "https://huggingface.co/docs/datasets", "install_packages ['datasets']; datasets.load_dataset('<id>')",
      requires=("internet", "python")),
    R("Kaggle", "data_repository", ("all",), "Community datasets and competitions.",
      "https://www.kaggle.com/docs/api", "Needs a user Kaggle token; otherwise find a mirror.", auth="api_key:KAGGLE_KEY"),
    # ── Biology & medicine ────────────────────────────────────────────────
    R("NCBI E-utilities", "api", ("genomics", "biology", "biomedicine"),
      "PubMed, GenBank, Gene, Protein, SRA, Taxonomy search and fetch.",
      "https://www.ncbi.nlm.nih.gov/books/NBK25501/",
      "GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=<db>&term=<q>&retmode=json then efetch.fcgi; ≤3 req/s"),
    R("NCBI BLAST (web)", "api", ("genomics", "biology"), "Sequence similarity search.",
      "https://blast.ncbi.nlm.nih.gov/doc/blast-help/developerinfo.html",
      "Biopython: Bio.Blast.NCBIWWW.qblast('blastp','nr',seq); slow, poll politely", requires=("internet", "python")),
    R("UniProt", "api", ("proteomics", "biology"), "Protein sequences, functions, annotations.",
      "https://www.uniprot.org/help/api", "GET https://rest.uniprot.org/uniprotkb/search?query=<q>&format=json"),
    R("RCSB PDB", "api", ("structural biology", "chemistry"), "3D macromolecular structures.",
      "https://data.rcsb.org", "Files: https://files.rcsb.org/download/<ID>.cif; search API at https://search.rcsb.org"),
    R("AlphaFold DB", "api", ("structural biology",), "Predicted protein structures.",
      "https://alphafold.ebi.ac.uk/api-docs", "GET https://alphafold.ebi.ac.uk/api/prediction/<UniProt accession>"),
    R("Ensembl REST", "api", ("genomics",), "Genes, variants, comparative genomics.",
      "https://rest.ensembl.org", "GET https://rest.ensembl.org/lookup/symbol/homo_sapiens/<gene>?content-type=application/json"),
    R("GEO", "data_repository", ("genomics", "transcriptomics"), "Gene expression datasets.",
      "https://www.ncbi.nlm.nih.gov/geo/info/geo_paccess.html", "Search via E-utilities db=gds; install_packages ['GEOparse']"),
    R("ClinicalTrials.gov", "api", ("medicine", "public health"), "Registered clinical trials and results.",
      "https://clinicaltrials.gov/data-api/api", "GET https://clinicaltrials.gov/api/v2/studies?query.term=<q>"),
    R("GBIF", "api", ("ecology", "biodiversity"), "Species occurrence records worldwide.",
      "https://techdocs.gbif.org/en/openapi/", "GET https://api.gbif.org/v1/occurrence/search?scientificName=<name>"),
    R("Biopython", "software", ("biology", "genomics"), "Sequence IO, alignments, NCBI access, structures.",
      "https://biopython.org/docs/", "install_packages ['biopython']", requires=("python",)),
    R("scanpy", "software", ("single-cell", "transcriptomics"), "Single-cell RNA-seq analysis.",
      "https://scanpy.readthedocs.io", "install_packages ['scanpy']", requires=("python",)),
    # ── Chemistry & materials ────────────────────────────────────────────
    R("PubChem PUG-REST", "api", ("chemistry", "pharmacology"), "Compounds, properties, bioassays.",
      "https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest",
      "GET https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/<name>/property/MolecularWeight,XLogP/JSON"),
    R("ChEMBL", "api", ("chemistry", "drug discovery"), "Bioactive molecules and assay data.",
      "https://chembl.gitbook.io/chembl-interface-documentation/web-services",
      "GET https://www.ebi.ac.uk/chembl/api/data/molecule/search?q=<q>&format=json"),
    R("Materials Project", "api", ("materials science",), "Computed properties of inorganic materials.",
      "https://docs.materialsproject.org/downloading-data/using-the-api",
      "install_packages ['mp-api']; needs the user's key", auth="api_key:MP_API_KEY", requires=("internet", "python")),
    R("RDKit", "software", ("chemistry",), "Cheminformatics: molecules, descriptors, fingerprints.",
      "https://www.rdkit.org/docs/", "install_packages ['rdkit']", requires=("python",)),
    R("ASE / pymatgen", "software", ("materials science", "physics"), "Atomistic structures and simulations.",
      "https://wiki.fysik.dtu.dk/ase/", "install_packages ['ase', 'pymatgen']", requires=("python",)),
    R("OpenMM", "software", ("molecular dynamics", "biophysics"), "GPU/CPU molecular dynamics.",
      "http://docs.openmm.org", "install_packages ['openmm'] (CPU works locally; large runs need a GPU)",
      requires=("python",)),
    # ── Physics, earth & space ───────────────────────────────────────────
    R("NASA APIs / Earthdata", "api", ("earth science", "astronomy"), "Satellite, climate and space data.",
      "https://api.nasa.gov", "Many endpoints accept api_key=DEMO_KEY at low rate limits"),
    R("NOAA Climate Data Online", "api", ("climate", "meteorology"), "Historical weather and climate records.",
      "https://www.ncdc.noaa.gov/cdo-web/webservices/v2", "Needs a free token", auth="api_key:NOAA_TOKEN"),
    R("Open-Meteo", "api", ("climate", "meteorology", "energy"), "Free weather forecasts and historical reanalysis.",
      "https://open-meteo.com/en/docs", "GET https://archive-api.open-meteo.com/v1/archive?latitude=..&longitude=..&start_date=..&end_date=..&hourly=temperature_2m"),
    R("USGS Earthquake API", "api", ("geophysics",), "Global earthquake catalog.",
      "https://earthquake.usgs.gov/fdsnws/event/1/", "GET https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime=.."),
    R("Astropy / astroquery", "software", ("astronomy",), "Astronomy computations and archive queries (SIMBAD, Gaia…).",
      "https://astroquery.readthedocs.io", "install_packages ['astropy', 'astroquery']", requires=("python",)),
    # ── Engineering, architecture & design ───────────────────────────────
    R("CadQuery / build123d", "software", ("mechanical engineering", "architecture", "design"),
      "Parametric CAD in Python; exports STEP/STL for geometry studies.",
      "https://cadquery.readthedocs.io", "install_packages ['cadquery'] or ['build123d']", requires=("python",)),
    R("trimesh", "software", ("design", "engineering", "graphics"), "Mesh analysis: volume, area, collisions.",
      "https://trimesh.org", "install_packages ['trimesh']", requires=("python",)),
    R("EnergyPlus", "software", ("architecture", "building energy"), "Whole-building energy simulation.",
      "https://energyplus.net/documentation",
      "Needs the EnergyPlus binary (not pip); eppy/geomeppy drive it", requires=("python", "system_binary")),
    R("FEniCSx", "software", ("engineering", "physics"), "Finite-element PDE solving.",
      "https://docs.fenicsproject.org", "Needs conda or a container", requires=("conda",)),
    R("OpenStreetMap Overpass", "api", ("urban planning", "geography", "architecture"),
      "Buildings, roads, land use anywhere on Earth.",
      "https://wiki.openstreetmap.org/wiki/Overpass_API", "POST https://overpass-api.de/api/interpreter data=<overpass QL>"),
    R("GeoPandas / OSMnx", "software", ("geography", "urban planning"), "Spatial data and street-network analysis.",
      "https://osmnx.readthedocs.io", "install_packages ['geopandas', 'osmnx']", requires=("python",)),
    # ── Social science, economics & policy ───────────────────────────────
    R("World Bank Indicators", "api", ("economics", "development"), "Country-level development indicators.",
      "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392",
      "GET https://api.worldbank.org/v2/country/all/indicator/<code>?format=json&per_page=20000"),
    R("US Census API", "api", ("demography", "economics", "social science"), "ACS and decennial census tables.",
      "https://www.census.gov/data/developers.html", "GET https://api.census.gov/data/<year>/acs/acs5?get=NAME,<var>&for=state:*"),
    R("FRED", "api", ("economics", "finance"), "Macroeconomic time series.",
      "https://fred.stlouisfed.org/docs/api/fred/", "Needs a free key", auth="api_key:FRED_API_KEY"),
    R("OECD / Eurostat SDMX", "api", ("economics", "policy"), "International statistics.",
      "https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access",
      "install_packages ['pandasdmx'] or GET the SDMX REST endpoints"),
    R("statsmodels / linearmodels", "software", ("statistics", "econometrics", "all"), "Regression, time series, panels.",
      "https://www.statsmodels.org", "install_packages ['statsmodels', 'linearmodels']", requires=("python",)),
    R("Mesa", "software", ("social simulation", "ecology"), "Agent-based modelling.",
      "https://mesa.readthedocs.io", "install_packages ['mesa']", requires=("python",)),
    # ── Math, CS & ML ────────────────────────────────────────────────────
    R("SymPy", "software", ("math", "physics"), "Symbolic mathematics and proofs by computation.",
      "https://docs.sympy.org", "install_packages ['sympy']", requires=("python",)),
    R("scikit-learn", "software", ("ml", "all"), "Classical machine learning.", "https://scikit-learn.org",
      "install_packages ['scikit-learn']", requires=("python",)),
    R("PyTorch", "software", ("ml", "all"), "Deep learning; Apple GPU via MPS locally, CUDA in the cloud.",
      "https://pytorch.org/docs", "install_packages ['torch']", requires=("python",)),
    R("NetworkX", "software", ("network science", "all"), "Graph algorithms and network analysis.",
      "https://networkx.org", "install_packages ['networkx']", requires=("python",)),
    R("SimPy", "software", ("operations research", "engineering"), "Discrete-event simulation.",
      "https://simpy.readthedocs.io", "install_packages ['simpy']", requires=("python",)),
    # ── Not executable by agents ─────────────────────────────────────────
    R("Human / wet-lab step", "software", ("all",),
      "Physical experiments, fieldwork, surveys with people, lab assays.",
      "", "Cannot be executed by agents; mark the task human_required and plan around it.",
      requires=("human",)),
)


def search(query: str, limit: int = 8) -> list[dict]:
    """Keyword match over names, fields and descriptions (simple, deterministic)."""
    terms = [t for t in query.lower().split() if len(t) > 2]
    scored = []
    for r in CATALOG:
        hay = " ".join([r.name, r.kind, " ".join(r.fields), r.description]).lower()
        score = sum(hay.count(t) for t in terms)
        if score:
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    return [r.as_dict() for _, r in scored[:limit]]


def summary() -> str:
    """Compact one-line-per-resource listing for prompts."""
    return "\n".join(
        f"- {r.name} [{r.kind}; {', '.join(r.fields)}] {r.description}"
        + (f" (auth: {r.auth})" if r.auth != "none" else "")
        + (f" (requires: {', '.join(x for x in r.requires if x not in ('internet', 'python'))})"
           if any(x not in ("internet", "python") for x in r.requires) else "")
        for r in CATALOG
    )
