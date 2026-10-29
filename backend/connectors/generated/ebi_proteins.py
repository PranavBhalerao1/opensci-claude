"""ebi_proteins: forged by the OpenScientist Connector Forge on 2026-10-29.

Proteins REST API — The Proteins REST API provides access to key biological data from UniProt and data from Large Scale Studies data mapped to UniProt. The services provide sequence feature annotations from UniProtKB, variation data from UniProtKB and mapped from Large Scale data sources (1000 Genomes, ExAC and COSMIC)

Base URL: https://www.ebi.ac.uk/proteins/api
"""

from typing import Any
from urllib.parse import quote

from mcp.server.mcpserver import MCPServer

from connectors._common import auth_headers, clip, request

BASE = "https://www.ebi.ac.uk/proteins/api"
server = MCPServer("ebi_proteins", instructions="Proteins REST API \u2014 The Proteins REST API provides access to key biological data from UniProt and data from Large Scale Studies data mapped to UniProt. The services provide sequence feature annotations from UniProtKB, variation data from UniProtKB and mapped from Large Scale data sources (1000 Genomes, ExAC and COSMIC)")


def _q(value: Any) -> str:
    return quote(str(value), safe="")


def _auth() -> dict:
    return auth_headers(None, None, '')


@server.tool()
async def antigen_get_by_accession(accession: str) -> Any:
    "Get antigen by UniProt accession"
    return clip(await request("GET", BASE + f"/antigen/{_q(accession)}", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def antigen_search(offset: int | None = None, size: int | None = None, accession: str | None = None, antigen_sequence: str | None = None, antigen_id: str | None = None, ensembl_ids: str | None = None, match_score: int | None = None) -> Any:
    "Search antigens in UniProt\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\naccession: UniProt accession(s). Comma separated values accepted up to 100.\nantigen_sequence: Antigen sequence\nantigen_id: Human Protein Atlas (HPA) antigen ID. Comma separated values accepted up to 20.\nensembl_ids: Ensembl IDs. Comma separated values accepted up to 20.\nmatch_score: Minimum alignment score for the antigen sequence and the target protein sequence"
    return clip(await request("GET", BASE + f"/antigen", params={"offset": offset, "size": size, "accession": accession, "antigen_sequence": antigen_sequence, "antigen_id": antigen_id, "ensembl_ids": ensembl_ids, "match_score": match_score},
                              json_body=None, headers=_auth()))


@server.tool()
async def coordinates_get_by_accession(accession: str) -> Any:
    "Get genomic coordinates for a UniProt accession"
    return clip(await request("GET", BASE + f"/coordinates/{_q(accession)}", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_by_db_xref(dbtype: str, dbid: str, offset: int | None = None, size: int | None = None) -> Any:
    "Search UniProt entries by genomic database cross reference IDs: Ensembl, CCDS, HGNC or RefSeq\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\ndbtype: Cross-reference database type: Ensembl, CCDC, HGNC or RefSeq\ndbid: Cross reference ID, such as ENSP00000351276 for Ensembl, NP_083392 for RefSeq, CCDS52493 for CCDS, 26588 for HGNC, (case insensitive)."
    return clip(await request("GET", BASE + f"/coordinates/{_q(dbtype)}:{_q(dbid)}", params={"offset": offset, "size": size},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_by_locations(taxonomy: str, locations: str, offset: int | None = None, size: int | None = None, in_range: bool | None = None) -> Any:
    "Search UniProt entries by taxonomy and genomic coordinates\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\ntaxonomy: Organism taxon ID\nlocations: genomic locations such as x:58205437-58219305,12452535-12452536,2:32452, before colon is the chromosome such as x:58205437-58219305, or without chromosome such as 12452535-12452536, means any chromoso\nin_range: When it is set to true for location search, only those entries that are in the range will be retrieved"
    return clip(await request("GET", BASE + f"/coordinates/{_q(taxonomy)}/{_q(locations)}", params={"offset": offset, "size": size, "in_range": in_range},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_feature_by_locations(taxonomy: str, locations: str, offset: int | None = None, size: int | None = None, in_range: bool | None = None) -> Any:
    "Search UniProt entries by taxonomy and genomic coordinates\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\ntaxonomy: Organism taxon ID\nlocations: genomic locations such as x:58205437-58219305,12452535-12452536,2:32452, before colon is the chromosome such as x:58205437-58219305, or without chromosome such as 12452535-12452536, means any chromoso\nin_range: When it is set to true for location search, only those entries that are in the range will be retrieved"
    return clip(await request("GET", BASE + f"/coordinates/{_q(taxonomy)}/{_q(locations)}/feature", params={"offset": offset, "size": size, "in_range": in_range},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_genome_location_by_accession(accession: str, p_start: int, p_end: int) -> Any:
    "Get genome coordinate by protein sequence position range"
    return clip(await request("GET", BASE + f"/coordinates/location/{_q(accession)}:{_q(p_start)}-{_q(p_end)}", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_genome_position_by_accession(accession: str, p_position: int) -> Any:
    "Get genome coordinate by protein sequence position"
    return clip(await request("GET", BASE + f"/coordinates/location/{_q(accession)}:{_q(p_position)}", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_protein_position_by_genome_location(taxonomy: str, chromosome: str, g_position: str) -> Any:
    "Get genome coordinate by protein sequence position\n\ntaxonomy: Organism taxon ID\nchromosome: Chromosome name, i.e. 1, 2, X, etc.\ngPosition: Genome location position"
    return clip(await request("GET", BASE + f"/coordinates/glocation/{_q(taxonomy)}/{_q(chromosome)}:{_q(g_position)}", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_protein_position_by_genome_location2(taxonomy: str, chromosome: str, gstart: str, gend: str) -> Any:
    "Get genome coordinate by protein sequence position\n\ntaxonomy: Organism taxon ID\nchromosome: Chromosome name, i.e. 1, 2, X, etc.\ngstart: Genome location start\ngend: Genome location end"
    return clip(await request("GET", BASE + f"/coordinates/glocation/{_q(taxonomy)}/{_q(chromosome)}:{_q(gstart)}-{_q(gend)}", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def coordinates_search(offset: int | None = None, size: int | None = None, accession: str | None = None, chromosome: str | None = None, ensembl: str | None = None, gene: str | None = None, protein: str | None = None, taxid: str | None = None, location: str | None = None) -> Any:
    "Search genomic coordinates for UniProt entries\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\naccession: UniProt accession(s). Comma separated values accepted up to 100.\nchromosome: Chromosome name, i.e. 1, 2, X, etc. Comma separated values accepted up to 20.\nensembl: Ensembl gene ID, transcript ID or translation ID. Comma separated values accepted up to 20.\ngene: UniProt gene name. Comma separated values accepted up to 20.\nprotein: UniProt protein name\ntaxid: Organism taxon ID. Comma separated values accepted up to 20.\nlocation: Genome location range such as 58205437-58219305 (genome start to genome end)"
    return clip(await request("GET", BASE + f"/coordinates", params={"offset": offset, "size": size, "accession": accession, "chromosome": chromosome, "ensembl": ensembl, "gene": gene, "protein": protein, "taxid": taxid, "location": location},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_all_interaction_entries(accession: str) -> Any:
    "Get UniProt interactions by accession"
    return clip(await request("GET", BASE + f"/proteins/interaction/{_q(accession)}", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def proteins_get_by_accession(accession: str) -> Any:
    "Get UniProt entry by accession"
    return clip(await request("GET", BASE + f"/proteins/{_q(accession)}", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_by_cross_reference(dbtype: str, dbid: str, offset: int | None = None, size: int | None = None, reviewed: str | None = None, isoform: int | None = None) -> Any:
    "Get UniProt entries by UniProt cross reference and its ID\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\ndbtype: Cross reference database type, e.g, Ensembl, PDBe, etc. \ndbid: Cross-reference ID, e.g. ENSP00000351276 for Ensembl\nreviewed: Reviewed(true) or not Reviewed (false)\nisoform: 0 for exclude isoform only and 1 for isoform only"
    return clip(await request("GET", BASE + f"/proteins/{_q(dbtype)}:{_q(dbid)}", params={"offset": offset, "size": size, "reviewed": reviewed, "isoform": isoform},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_entries_for_isoforms(accession: str) -> Any:
    "Get UniProt isoform entries from parent entry accession"
    return clip(await request("GET", BASE + f"/proteins/{_q(accession)}/isoforms", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def proteins_search(offset: int | None = None, size: int | None = None, accession: str | None = None, reviewed: str | None = None, isoform: int | None = None, goterms: str | None = None, keywords: str | None = None, ec: str | None = None, gene: str | None = None, exact_gene: str | None = None, protein: str | None = None, organism: str | None = None, taxid: str | None = None, pubmed: str | None = None, seq_length: str | None = None, md5: str | None = None) -> Any:
    "Search UniProt entries\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\naccession: UniProt accession(s). Comma separated values accepted up to 100.\nreviewed: Reviewed(true) or not Reviewed (false)\nisoform: 0 for excluding isoform, 1 for isoform only and 2 for both canonical and isoform\ngoterms: GO ontology terms\nkeywords: UniProt keywords\nec: UniProt EC number. Comma separated values accepted up to 20.\ngene: UniProt gene name. Comma separated values accepted up to 20.\nexact_gene: UniProt exact gene name. Comma separated values accepted up to 20.\nprotein: UniProt protein name\norganism: Organism name\ntaxid: Organism taxon ID. Comma separated values accepted up to 20.\npubmed: UniProt reference PubMed ID. Comma separated values accepted up to 20.\nseqLength: Sequence length. Sequence length can be a single length value such as 123 or range 123-234\nmd5: Sequence md5 value."
    return clip(await request("GET", BASE + f"/proteins", params={"offset": offset, "size": size, "accession": accession, "reviewed": reviewed, "isoform": isoform, "goterms": goterms, "keywords": keywords, "ec": ec, "gene": gene, "exact_gene": exact_gene, "protein": protein, "organism": organism, "taxid": taxid, "pubmed": pubmed, "seqLength": seq_length, "md5": md5},
                              json_body=None, headers=_auth()))


@server.tool()
async def epitope_get_by_accession(accession: str) -> Any:
    "Get epitope by UniProt accession"
    return clip(await request("GET", BASE + f"/epitope/{_q(accession)}", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def epitope_search(offset: int | None = None, size: int | None = None, accession: str | None = None, epitope_sequence: str | None = None, iedb_id: str | None = None, match_score: int | None = None) -> Any:
    "Search epitope in UniProt\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\naccession: UniProt accession(s). Comma separated values accepted up to 100.\nepitope_sequence: Epitope sequence\niedb_id: Epitope or antigenic determinant ID. Comma separated values accepted up to 20.\nmatch_score: Minimum alignment score for the antigen sequence and the target protein sequence"
    return clip(await request("GET", BASE + f"/epitope", params={"offset": offset, "size": size, "accession": accession, "epitope_sequence": epitope_sequence, "iedb_id": iedb_id, "match_score": match_score},
                              json_body=None, headers=_auth()))


@server.tool()
async def features_get_by_accession(uni_prot_accession: str, accession: str, category_type_s_molecule_processing_topology_sequence_information_structural_domains_and_sites_ptm_variants_mutagenesis_comma_separated_values_accepted_up_to_20: str | None = None, feature_type_s_init_met_signal_propep_transit_chain_peptide_topo_dom_transmem_domain_repeat_zn_fing_dna_bind_region_coiled_motif_compbias_act_site_binding_site_non_std_mod_res_lipid_carbohyd_disulfid_crosslnk_var_seq_variant_mutagen_unsure_conflict_non_cons_non_ter_helix_turn_strand_intramem_comma_separated_values_accepted_up_to_20: str | None = None, location: str | None = None) -> Any:
    "Get UniProt protein sequence features by accession\n\nlocation: Filter by the amino acid range position in the sequence(s). Any valid amino acid range position within the length of the protein sequence such as 10-60 (start position to end position)"
    return clip(await request("GET", BASE + f"/features/{_q(accession)}", params={"Category type(s): MOLECULE_PROCESSING, TOPOLOGY, SEQUENCE_INFORMATION, STRUCTURAL, DOMAINS_AND_SITES, PTM, VARIANTS, MUTAGENESIS. Comma separated values accepted up to 20": category_type_s_molecule_processing_topology_sequence_information_structural_domains_and_sites_ptm_variants_mutagenesis_comma_separated_values_accepted_up_to_20, "Feature type(s): INIT_MET, SIGNAL, PROPEP, TRANSIT, CHAIN, PEPTIDE, TOPO_DOM, TRANSMEM, DOMAIN, REPEAT, ZN_FING, DNA_BIND, REGION, COILED, MOTIF, COMPBIAS, ACT_SITE, BINDING, SITE, NON_STD, MOD_RES, LIPID, CARBOHYD, DISULFID, CROSSLNK, VAR_SEQ, VARIANT, MUTAGEN, UNSURE, CONFLICT, NON_CONS, NON_TER, HELIX, TURN, STRAND, INTRAMEM. Comma separated values accepted up to 20": feature_type_s_init_met_signal_propep_transit_chain_peptide_topo_dom_transmem_domain_repeat_zn_fing_dna_bind_region_coiled_motif_compbias_act_site_binding_site_non_std_mod_res_lipid_carbohyd_disulfid_crosslnk_var_seq_variant_mutagen_unsure_conflict_non_cons_non_ter_helix_turn_strand_intramem_comma_separated_values_accepted_up_to_20, "location": location},
                              json_body=None, headers=_auth()))


@server.tool()
async def features_search(offset: int | None = None, size: int | None = None, accession: str | None = None, reviewed: str | None = None, gene: str | None = None, exact_gene: str | None = None, protein: str | None = None, organism: str | None = None, taxid: str | None = None, categories: str | None = None, types: str | None = None) -> Any:
    "Search protein sequence features in UniProt\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\naccession: UniProt accession(s). Comma separated values accepted up to 100.\nreviewed: The reviewed parameter can only be true or false\ngene: UniProt gene name. Comma separated values accepted up to 20.\nexact_gene: UniProt exact gene name. Comma separated values accepted up to 20.\nprotein: UniProt protein name\norganism: Organism name\ntaxid: Organism taxon ID. Comma separated values accepted up to 20.\ncategories: Category type(s): MOLECULE_PROCESSING, TOPOLOGY, SEQUENCE_INFORMATION, STRUCTURAL, DOMAINS_AND_SITES, PTM, VARIANTS, MUTAGENESIS. Comma separated values accepted up to 20\ntypes: Feature type(s): INIT_MET, SIGNAL, PROPEP, TRANSIT, CHAIN, PEPTIDE, TOPO_DOM, TRANSMEM, DOMAIN, REPEAT, ZN_FING, DNA_BIND, REGION, COILED, MOTIF, COMPBIAS, ACT_SITE, BINDING, SITE, NON_STD, MOD_RES, L"
    return clip(await request("GET", BASE + f"/features", params={"offset": offset, "size": size, "accession": accession, "reviewed": reviewed, "gene": gene, "exact_gene": exact_gene, "protein": protein, "organism": organism, "taxid": taxid, "categories": categories, "types": types},
                              json_body=None, headers=_auth()))


@server.tool()
async def search_feature_type(type: str, terms: str, offset: int | None = None, size: int | None = None, categories: str | None = None, types: str | None = None) -> Any:
    "Search protein sequence features of a given type in UniProt\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\ntype: Feature type: INIT_MET, SIGNAL, PROPEP, TRANSIT, CHAIN, PEPTIDE, TOPO_DOM, TRANSMEM, DOMAIN, REPEAT, ZN_FING, DNA_BIND, REGION, COILED, MOTIF, COMPBIAS, ACT_SITE, BINDING, SITE, NON_STD, MOD_RES, LIPI\ncategories: Category type(s): MOLECULE_PROCESSING, TOPOLOGY, SEQUENCE_INFORMATION, STRUCTURAL, DOMAINS_AND_SITES, PTM, VARIANTS, MUTAGENESIS. Comma separated values accepted up to 20\ntypes: Feature type(s): INIT_MET, SIGNAL, PROPEP, TRANSIT, CHAIN, PEPTIDE, TOPO_DOM, TRANSMEM, DOMAIN, REPEAT, ZN_FING, DNA_BIND, REGION, COILED, MOTIF, COMPBIAS, ACT_SITE, BINDING, SITE, NON_STD, MOD_RES, L\nterms: Search for term(s) that appear in feature description for your specified feature type. For example, you can search by type=DOMAIN and Term=Kinase.  Comma separated values accepted up to 20."
    return clip(await request("GET", BASE + f"/features/type/{_q(type)}", params={"offset": offset, "size": size, "categories": categories, "types": types, "terms": terms},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_gene_centric_by_accession(accession: str) -> Any:
    "Get gene centric proteins by Uniprot accession"
    return clip(await request("GET", BASE + f"/genecentric/{_q(accession)}", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_gene_centric_by_upid(offset: int | None = None, size: int | None = None, upid: str | None = None, accession: str | None = None, gene: str | None = None) -> Any:
    "Search gene centric proteins\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\nupid: UniProt proteome UPID(s). Comma separated values accepted up to 100.\naccession: UniProt accession(s). Comma separated values accepted up to 100.\ngene: It is a unique gene identifier found in MOD, Ensembl, Ensembl Genomes, OLN ,ORF or UniProt Gene Name database. Comma separated values accepted up to 20."
    return clip(await request("GET", BASE + f"/genecentric", params={"offset": offset, "size": size, "upid": upid, "accession": accession, "gene": gene},
                              json_body=None, headers=_auth()))


@server.tool()
async def hpp_get_by_accession(accession: str) -> Any:
    "Get hpp peptides mapped to UniProt by accession"
    return clip(await request("GET", BASE + f"/hpp/{_q(accession)}", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def hpp_search(offset: int | None = None, size: int | None = None, accession: str | None = None, taxid: str | None = None, upid: str | None = None, datasource: str | None = None, peptide: str | None = None, unique: str | None = None) -> Any:
    "Search hpp peptides in UniProt\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\naccession: UniProt accession(s). Comma separated values accepted up to 100.\ntaxid: Organism taxon ID. Comma separated values accepted up to 20.\nupid: UniProt proteome UPID(s). Comma separated values accepted up to 100.\ndatasource: HPP data source(s): MaxQB, PeptideAtlas, EPD or HppDB. Comma separated values accepted up to 2.\npeptide: Peptide sequence. Comma separated values accepted up to 20.\nunique: Peptide uniqueness (unique peptides map to one gene group only). Values can be true or false."
    return clip(await request("GET", BASE + f"/hpp", params={"offset": offset, "size": size, "accession": accession, "taxid": taxid, "upid": upid, "datasource": datasource, "peptide": peptide, "unique": unique},
                              json_body=None, headers=_auth()))


@server.tool()
async def proteomics_get_by_accession(accession: str) -> Any:
    "Get hpp peptides mapped to UniProt by accession"
    return clip(await request("GET", BASE + f"/proteomics/hpp/{_q(accession)}", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def proteomics_search(offset: int | None = None, size: int | None = None, accession: str | None = None, taxid: str | None = None, upid: str | None = None, datasource: str | None = None, peptide: str | None = None, unique: str | None = None) -> Any:
    "Search hpp peptides in UniProt\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\naccession: UniProt accession(s). Comma separated values accepted up to 100.\ntaxid: Organism taxon ID. Comma separated values accepted up to 20.\nupid: UniProt proteome UPID(s). Comma separated values accepted up to 100.\ndatasource: HPP data source(s): MaxQB, PeptideAtlas, EPD or HppDB. Comma separated values accepted up to 2.\npeptide: Peptide sequence. Comma separated values accepted up to 20.\nunique: Peptide uniqueness (unique peptides map to one gene group only). Values can be true or false."
    return clip(await request("GET", BASE + f"/proteomics/hpp", params={"offset": offset, "size": size, "accession": accession, "taxid": taxid, "upid": upid, "datasource": datasource, "peptide": peptide, "unique": unique},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_uni_prot_info(raw: bool | None = None) -> Any:
    "GET /info"
    return clip(await request("GET", BASE + f"/info", params={"raw": raw},
                              json_body=None, headers=_auth()))


@server.tool()
async def mutagenesis_get_by_accession(uni_prot_accession: str, accession: str, location: str | None = None) -> Any:
    "Get mutagenesis mapped to UniProt by accession\n\nlocation: Filter by the amino acid range position in the sequence(s). Any valid amino acid range position within the length of the protein sequence such as 10-60 (start position to end position)"
    return clip(await request("GET", BASE + f"/mutagenesis/{_q(accession)}", params={"location": location},
                              json_body=None, headers=_auth()))


@server.tool()
async def mutagenesis_search(offset: int | None = None, size: int | None = None, accession: str | None = None, taxid: str | None = None, dbid: str | None = None) -> Any:
    "Search mutagensis in UniProt\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\naccession: UniProt accession(s). Comma separated values accepted up to 100.\ntaxid: Organism taxon ID. Comma separated values accepted up to 20.\ndbid: Cross-reference database ID, e.g. rs121918508 for dbSNP, COSM29836 for cosmic curated, rcv61200 for ClinVar. Comma separated values accepted up to 20."
    return clip(await request("GET", BASE + f"/mutagenesis", params={"offset": offset, "size": size, "accession": accession, "taxid": taxid, "dbid": dbid},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_by_upid(upid: str) -> Any:
    "Get proteome by proteome UPID"
    return clip(await request("GET", BASE + f"/proteomes/{_q(upid)}", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_gene_centric_by_upid_deprecated(upid: str) -> Any:
    "Get gene centric proteins by proteome UPID is deprecated, please use new /genecentric?upid= endpoint"
    return clip(await request("GET", BASE + f"/proteomes/genecentric/{_q(upid)}", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_proteins_by_upid(uni_prot_proteome_upid: str, upid: str, reviewed: str | None = None) -> Any:
    "Get proteins by proteome UPID\n\nreviewed: Reviewed(true) or not Reviewed (false)"
    return clip(await request("GET", BASE + f"/proteomes/proteins/{_q(upid)}", params={"reviewed": reviewed},
                              json_body=None, headers=_auth()))


@server.tool()
async def proteomes_search(offset: int | None = None, size: int | None = None, upid: str | None = None, name: str | None = None, taxid: str | None = None, keyword: str | None = None, xref: str | None = None, genome_acc: str | None = None, is_ref_proteome: str | None = None) -> Any:
    "Search proteomes in UniProt\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\nupid: UniProt proteome UPID(s). Comma separated values accepted up to 100.\nname: Search proteome name\ntaxid: Organism taxon ID. Comma separated values accepted up to 20.\nkeyword: Terms the proteome contains\nxref: Proteome cross references such as Genome assembly ID or Biosample ID. Comma separated values accepted up to 20.\ngenome_acc: Genome accession. Comma separated values accepted up to 20.\nis_ref_proteome: Reference Proteome(true) or not reference proteome (false)"
    return clip(await request("GET", BASE + f"/proteomes", params={"offset": offset, "size": size, "upid": upid, "name": name, "taxid": taxid, "keyword": keyword, "xref": xref, "genome_acc": genome_acc, "is_ref_proteome": is_ref_proteome},
                              json_body=None, headers=_auth()))


@server.tool()
async def proteomics_get_by_accession_2(accession: str) -> Any:
    "Get proteomics peptides mapped to UniProt by accession"
    return clip(await request("GET", BASE + f"/proteomics/{_q(accession)}", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_non_ptm_by_accession(accession: str) -> Any:
    "Get proteomics peptides mapped to UniProt by accession"
    return clip(await request("GET", BASE + f"/proteomics/nonPtm/{_q(accession)}", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def proteomics_search_2(offset: int | None = None, size: int | None = None, accession: str | None = None, taxid: str | None = None, upid: str | None = None, datasource: str | None = None, peptide: str | None = None, unique: str | None = None) -> Any:
    "Search proteomics peptides in UniProt\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\naccession: UniProt accession(s). Comma separated values accepted up to 100.\ntaxid: Organism taxon ID. Comma separated values accepted up to 20.\nupid: UniProt proteome UPID(s). Comma separated values accepted up to 100.\ndatasource: Proteomics data source(s): MaxQB, PeptideAtlas, EPD or ProteomicsDB. Comma separated values accepted up to 2.\npeptide: Peptide sequence. Comma separated values accepted up to 20.\nunique: Peptide uniqueness (unique peptides map to one gene group only). Values can be true or false."
    return clip(await request("GET", BASE + f"/proteomics", params={"offset": offset, "size": size, "accession": accession, "taxid": taxid, "upid": upid, "datasource": datasource, "peptide": peptide, "unique": unique},
                              json_body=None, headers=_auth()))


@server.tool()
async def search_non_ptm(offset: int | None = None, size: int | None = None, accession: str | None = None, taxid: str | None = None, upid: str | None = None, datasource: str | None = None, peptide: str | None = None, unique: str | None = None) -> Any:
    "Search proteomics peptides in UniProt\n\noffset: Off set, page starting point, with default value 0\nsize: Page size with default value 100. When page size is -1, it returns all records and offset will be ignored\naccession: UniProt accession(s). Comma separated values accepted up to 100.\ntaxid: Organism taxon ID. Comma separated values accepted up to 20.\nupid: UniProt proteome UPID(s). Comma separated values accepted up to 100.\ndatasource: Proteomics data source(s): MaxQB, PeptideAtlas, EPD or ProteomicsDB. Comma separated values accepted up to 2.\npeptide: Peptide sequence. Comma separated values accepted up to 20.\nunique: Peptide uniqueness (unique peptides map to one gene group only). Values can be true or false."
    return clip(await request("GET", BASE + f"/proteomics/nonPtm", params={"offset": offset, "size": size, "accession": accession, "taxid": taxid, "upid": upid, "datasource": datasource, "peptide": peptide, "unique": unique},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_overview() -> Any:
    "Get proteomics metadata overview"
    return clip(await request("GET", BASE + f"/proteomics/species", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def search_species(datatype: str | None = None, taxid: str | None = None, upid: str | None = None) -> Any:
    "Search proteomics species by datatype, taxid, or upid"
    return clip(await request("GET", BASE + f"/proteomics/species/search", params={"datatype": datatype, "taxid": taxid, "upid": upid},
                              json_body=None, headers=_auth()))


if __name__ == "__main__":
    server.run()
