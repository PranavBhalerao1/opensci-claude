"""ols: forged by the OpenScientist Connector Forge on 2026-10-29.

OLS Service — REST API for OLS. Please see  this page for defined response field in OLS.

Base URL: https://www.ebi.ac.uk/ols4
"""

from typing import Any
from urllib.parse import quote

from mcp.server.mcpserver import MCPServer

from connectors._common import auth_headers, clip, request

BASE = "https://www.ebi.ac.uk/ols4"
server = MCPServer("ols", instructions="OLS Service \u2014 REST API for OLS. Please see  this page for defined response field in OLS.")


def _q(value: Any) -> str:
    return quote(str(value), safe="")


def _auth() -> dict:
    return auth_headers(None, None, '')


@server.tool()
async def tag_text_status(tag_text_status: str | None = None) -> Any:
    "GET /api/v2/tag_text\n\ntag_text_status: Check whether the text tagger service is available"
    return clip(await request("GET", BASE + f"/api/v2/tag_text", params={"tag_text_status": tag_text_status},
                              json_body=None, headers=_auth()))


@server.tool()
async def tag_text(ontology_id: list | None = None, source: list | None = None, delimiters: str | None = None, min_length: int | None = None, include_substrings: bool | None = None, include_obsolete_entities: bool | None = None, tag_text: str | None = None, body: dict | None = None) -> Any:
    "POST /api/v2/tag_text\n\ntag_text: Annotate free text with matching ontology terms"
    return clip(await request("POST", BASE + f"/api/v2/tag_text", params={"ontologyId": ontology_id, "source": source, "delimiters": delimiters, "minLength": min_length, "includeSubstrings": include_substrings, "includeObsoleteEntities": include_obsolete_entities, "tag_text": tag_text},
                              json_body=body, headers=_auth()))


@server.tool()
async def search_classes_by_vector_in_ontology(onto: str, model: str, page: int | None = None, size: int | None = None, sort: list | None = None, lang: str | None = None, is_defining_ontology: bool | None = None, include_curations: bool | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None, body: dict | None = None) -> Any:
    "POST /api/v2/ontologies/{onto}/classes/llm_embedding\n\nonto: The ontology ID to filter results.\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nmodel: The embedding model name to use for vector search\nisDefiningOntology: If true, only return classes defined in this ontology. If false (default), include imported classes too.\nincludeCurations: If true (default), include curated text-to-term mapping embeddings in the search. If false, only search label embeddings.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("POST", BASE + f"/api/v2/ontologies/{_q(onto)}/classes/llm_embedding", params={"page": page, "size": size, "sort": sort, "lang": lang, "model": model, "isDefiningOntology": is_defining_ontology, "includeCurations": include_curations, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=body, headers=_auth()))


@server.tool()
async def search_classes_by_vector(model: str, page: int | None = None, size: int | None = None, sort: list | None = None, lang: str | None = None, ontology_id: str | None = None, include_curations: bool | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None, body: dict | None = None) -> Any:
    "POST /api/v2/classes/llm_embedding\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nmodel: The embedding model name to use for vector search\nontologyId: Optional ontology ID to filter results. If specified only returns classes defined in this ontology (not imported classes).\nincludeCurations: If true (default), include curated text-to-term mapping embeddings in the search. If false, only search label embeddings.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("POST", BASE + f"/api/v2/classes/llm_embedding", params={"page": page, "size": size, "sort": sort, "lang": lang, "model": model, "ontologyId": ontology_id, "includeCurations": include_curations, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=body, headers=_auth()))


@server.tool()
async def get_statistics() -> Any:
    "GET /api/v2/stats"
    return clip(await request("GET", BASE + f"/api/v2/stats", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_releases() -> Any:
    "GET /api/v2/releases"
    return clip(await request("GET", BASE + f"/api/v2/releases", params={},
                              json_body=None, headers=_auth()))


@server.tool()
async def api_get_properties(page: int | None = None, size: int | None = None, sort: list | None = None, search: str | None = None, search_fields: str | None = None, boost_fields: str | None = None, exact_match: bool | None = None, include_obsolete_entities: bool | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/properties\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nsearch: This parameter specify the search query text.\nsearchFields: This parameter is a white space separated list of fields to search in. The fields are weighted equally. The fields are defined in the schema. The default fields are label and definition. The fields we\nboostFields: This parameter is a white space separated list of fields appended with a caret to boost in search. The default fields are type, is_defining_ontology, label, curie, shortForm and synonym . The fields w\nexactMatch: As the name suggests its a boolean parameter to specify if search should be exact match or not.The default value is false\nincludeObsoleteEntities: A boolean parameter to specify if obsolete entities should be included or not. Default value is false.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/properties", params={"page": page, "size": size, "sort": sort, "search": search, "searchFields": search_fields, "boostFields": boost_fields, "exactMatch": exact_match, "includeObsoleteEntities": include_obsolete_entities, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_similar_properties(property: str, page: int | None = None, size: int | None = None, sort: list | None = None, lang: str | None = None, model: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/properties/{property}/llm_similar\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nproperty: The IRI of the property, this value must be double URL encoded\nmodel: The embedding model name to use. Defaults to harrier-oss-v1-27b_pca512.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/properties/{_q(property)}/llm_similar", params={"page": page, "size": size, "sort": sort, "lang": lang, "model": model, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def search_properties_by_text(q: str, model: str, page: int | None = None, size: int | None = None, sort: list | None = None, lang: str | None = None, ontology_id: str | None = None, include_curations: bool | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/properties/llm_search\n\nq: The text query to search for using semantic similarity\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nmodel: The embedding model name to use for vector search\nontologyId: Optional ontology ID to filter results. If specified only returns properties defined in this ontology.\nincludeCurations: If true (default), include curated text-to-term mapping embeddings in the search. If false, only search label embeddings.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/properties/llm_search", params={"q": q, "page": page, "size": size, "sort": sort, "lang": lang, "model": model, "ontologyId": ontology_id, "includeCurations": include_curations, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def api_get_ontologies(page: int | None = None, size: int | None = None, sort: list | None = None, search: str | None = None, search_fields: str | None = None, boost_fields: str | None = None, exact_match: bool | None = None, include_obsolete_entities: bool | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nsearch: This parameter specify the search query text.\nsearchFields: This parameter is a white space separated list of fields to search in. The fields are weighted equally. The fields are defined in the schema. The default fields are label, ontologyId and definition. T\nboostFields: This parameter is a white space separated list of fields appended with a caret to boost in search. The default fields are type, is_defining_ontology, label, curie, shortForm and synonym . The fields w\nexactMatch: As the name suggests its a boolean parameter to specify if search should be exact match or not.The default value is false\nincludeObsoleteEntities: A boolean parameter to specify if obsolete entities should be included or not. Default value is false.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies", params={"page": page, "size": size, "sort": sort, "search": search, "searchFields": search_fields, "boostFields": boost_fields, "exactMatch": exact_match, "includeObsoleteEntities": include_obsolete_entities, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def api_get_ontology(onto: str, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}\n\nonto: Ontology Id to get the information about.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}", params={"lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def api_get_properties_2(onto: str, page: int | None = None, size: int | None = None, sort: list | None = None, search: str | None = None, search_fields: str | None = None, boost_fields: str | None = None, exact_match: bool | None = None, include_obsolete_entities: bool | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/properties\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nonto: Ontology Id to search properties in.\nsearch: This parameter specify the search query text.\nsearch fields: This parameter is a white space separated list of fields to search in. The fields are weighted equally. The fields are defined in the schema. The default fields are label and definition. The fields we\nboost fields: This parameter is a white space separated list of fields appended with a caret to boost in search. The default fields are type, is_defining_ontology, label, curie, shortForm and synonym . The fields w\nexactMatch: As the name suggests its a boolean parameter to specify if search should be exact match or not.The default value is false\nincludeObsoleteEntities: A boolean parameter to specify if obsolete entities should be included or not. Default value is false.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/properties", params={"page": page, "size": size, "sort": sort, "search": search, "search fields": search_fields, "boost fields": boost_fields, "exactMatch": exact_match, "includeObsoleteEntities": include_obsolete_entities, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def api_get_property(onto: str, property: str, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/properties/{property}\n\nonto: Ontology Id to search properties in.\nproperty: The IRI of the property, this value must be double URL encoded\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/properties/{_q(property)}", params={"lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def api_get_children_by_ontology(onto: str, property: str, page: int | None = None, size: int | None = None, sort: list | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/properties/{property}/children\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nonto: Ontology Id to search properties in.\nproperty: The IRI of the property, this value must be double URL encoded\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/properties/{_q(property)}/children", params={"page": page, "size": size, "sort": sort, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def api_get_ancestors_by_ontology(onto: str, property: str, page: int | None = None, size: int | None = None, sort: list | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/properties/{property}/ancestors\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nonto: Ontology Id to search properties in.\nproperty: The IRI of the property, this value must be double URL encoded\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/properties/{_q(property)}/ancestors", params={"page": page, "size": size, "sort": sort, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def api_get_individuals(onto: str, page: int | None = None, size: int | None = None, sort: list | None = None, search: str | None = None, search_fields: str | None = None, boost_fields: str | None = None, exact_match: bool | None = None, include_obsolete_entities: bool | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/individuals\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nonto: Ontology Id to search individuals in.\nsearch: This parameter specify the search query text.\nsearchFields: This parameter is a white space separated list of fields to search in. The fields are weighted equally. The fields are defined in the schema. The default fields are label and definition. The fields we\nboostFields: This parameter is a white space separated list of fields appended with a caret to boost in search. The default fields are type, is_defining_ontology, label, curie, shortForm and synonym . The fields w\nexactMatch: As the name suggests its a boolean parameter to specify if search should be exact match or not.The default value is false\nincludeObsoleteEntities: A boolean parameter to specify if obsolete entities should be included or not. Default value is false.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/individuals", params={"page": page, "size": size, "sort": sort, "search": search, "searchFields": search_fields, "boostFields": boost_fields, "exactMatch": exact_match, "includeObsoleteEntities": include_obsolete_entities, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def api_get_individual(onto: str, individual: str, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/individuals/{individual}\n\nonto: Ontology Id to get the information about.\nindividual: The IRI of the individual, this value must be double URL encoded\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/individuals/{_q(individual)}", params={"lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def api_get_hierarchical_children_by_ontology(onto: str, individual: str, page: int | None = None, size: int | None = None, sort: list | None = None, include_obsolete_entities: bool | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/individuals/{individual}/hierarchicalChildren\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nonto: Ontology Id to get the information about.\nindividual: The IRI of the individual, this value must be double URL encoded\nincludeObsoleteEntities: A boolean parameter to specify if obsolete entities should be included or not. Default value is false.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/individuals/{_q(individual)}/hierarchicalChildren", params={"page": page, "size": size, "sort": sort, "includeObsoleteEntities": include_obsolete_entities, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def api_get_hierarchical_ancestors_by_ontology(onto: str, individual: str, page: int | None = None, size: int | None = None, sort: list | None = None, include_obsolete_entities: bool | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/individuals/{individual}/hierarchicalAncestors\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nonto: Ontology Id to get the information about.\nindividual: The IRI of the individual, this value must be double URL encoded\nincludeObsoleteEntities: A boolean parameter to specify if obsolete entities should be included or not. Default value is false.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/individuals/{_q(individual)}/hierarchicalAncestors", params={"page": page, "size": size, "sort": sort, "includeObsoleteEntities": include_obsolete_entities, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_individual_ancestors_by_ontology(onto: str, individual: str, page: int | None = None, size: int | None = None, sort: list | None = None, include_obsolete_entities: bool | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/individuals/{individual}/ancestors\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nonto: Ontology Id to get the information about.\nindividual: The IRI of the individual, this value must be double URL encoded\nincludeObsoleteEntities: A boolean parameter to specify if obsolete entities should be included or not. Default value is false.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/individuals/{_q(individual)}/ancestors", params={"page": page, "size": size, "sort": sort, "includeObsoleteEntities": include_obsolete_entities, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def api_get_terms(onto: str, page: int | None = None, size: int | None = None, sort: list | None = None, search: str | None = None, search_fields: str | None = None, boost_fields: str | None = None, facet_fields: str | None = None, exact_match: bool | None = None, include_obsolete_entities: bool | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "Search and filter entities within a specific ontology. In addition to the named parameters listed, any indexed field can be used as a filter by passing it as a query parameter. Values are case-insensitive and comma-separated values are treated as OR logic. For example: ?type=class&hierarchicalAncest\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nonto: Ontology Id to get the information about.\nsearch: This parameter specify the search query text.\nsearchFields: This parameter is a white space separated list of fields to search in. The fields are weighted equally. The fields are defined in the schema. The default fields are label and definition. The fields we\nboostFields: This parameter is a white space separated list of fields appended with a caret to boost in search. The default fields are type, is_defining_ontology, label, curie, shortForm and synonym . The fields w\nfacetFields: This parameter is a white space separated list of fields to facet data by.\nexactMatch: As the name suggests its a boolean parameter to specify if search should be exact match or not.The default value is false\nincludeObsoleteEntities: A boolean parameter to specify if obsolete entities should be included or not. Default value is false.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/entities", params={"page": page, "size": size, "sort": sort, "search": search, "searchFields": search_fields, "boostFields": boost_fields, "facetFields": facet_fields, "exactMatch": exact_match, "includeObsoleteEntities": include_obsolete_entities, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_entity(onto: str, entity: str, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/entities/{entity}\n\nonto: Ontology Id to get the information about.\nentity: The IRI of the entity, this value must be double URL encoded\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/entities/{_q(entity)}", params={"lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_entity_related_from(onto: str, entity: str, page: int | None = None, size: int | None = None, sort: list | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/entities/{entity}/relatedFrom\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nonto: Ontology Id to get the information about.\nentity: The IRI of the entity, this value must be double URL encoded\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/entities/{_q(entity)}/relatedFrom", params={"page": page, "size": size, "sort": sort, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def api_get_classes(onto: str, page: int | None = None, size: int | None = None, sort: list | None = None, search: str | None = None, search_fields: str | None = None, boost_fields: str | None = None, exact_match: bool | None = None, include_obsolete_entities: bool | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/classes\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nonto: Ontology Id to get the information about.\nsearch: This parameter specify the search query text.\nsearchFields: This parameter is a white space separated list of fields to search in. The fields are weighted equally. The fields are defined in the schema. The default fields are label and definition. The fields we\nboostFields: This parameter is a white space separated list of fields appended with a caret to boost in search. The default fields are type, is_defining_ontology, label, curie, shortForm and synonym . The fields w\nexactMatch: As the name suggests its a boolean parameter to specify if search should be exact match or not.The default value is false\nincludeObsoleteEntities: A boolean parameter to specify if obsolete entities should be included or not. Default value is false.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/classes", params={"page": page, "size": size, "sort": sort, "search": search, "searchFields": search_fields, "boostFields": boost_fields, "exactMatch": exact_match, "includeObsoleteEntities": include_obsolete_entities, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_class(onto: str, p_class: str, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/classes/{class}\n\nonto: Ontology Id to get the information about.\nclass: The IRI of the class, this value must be double URL encoded\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/classes/{_q(p_class)}", params={"lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_class_related_from(onto: str, p_class: str, page: int | None = None, size: int | None = None, sort: list | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/classes/{class}/relatedFrom\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nonto: Ontology Id to get the information about.\nclass: The IRI of the class, this value must be double URL encoded\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/classes/{_q(p_class)}/relatedFrom", params={"page": page, "size": size, "sort": sort, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_class_individuals(onto: str, p_class: str, page: int | None = None, size: int | None = None, sort: list | None = None, include_obsolete_entities: bool | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/classes/{class}/individuals\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nonto: Ontology Id to get the information about.\nclass: The IRI of the class, this value must be double URL encoded\nincludeObsoleteEntities: A boolean parameter to specify if obsolete entities should be included or not. Default value is false.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/classes/{_q(p_class)}/individuals", params={"page": page, "size": size, "sort": sort, "includeObsoleteEntities": include_obsolete_entities, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def get_hierarchical_descendants_by_ontology(onto: str, p_class: str, page: int | None = None, size: int | None = None, sort: list | None = None, include_obsolete_entities: bool | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/classes/{class}/hierarchicalDescendants\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nonto: Ontology Id to get the information about.\nclass: The IRI of the class, this value must be double URL encoded\nincludeObsoleteEntities: A boolean parameter to specify if obsolete entities should be included or not. Default value is false.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/classes/{_q(p_class)}/hierarchicalDescendants", params={"page": page, "size": size, "sort": sort, "includeObsoleteEntities": include_obsolete_entities, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def api_get_hierarchical_children_by_ontology_2(onto: str, p_class: str, page: int | None = None, size: int | None = None, sort: list | None = None, include_obsolete_entities: bool | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/classes/{class}/hierarchicalChildren\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nonto: Ontology Id to get the information about.\nclass: The IRI of the class, this value must be double URL encoded\nincludeObsoleteEntities: A boolean parameter to specify if obsolete entities should be included or not. Default value is false.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/classes/{_q(p_class)}/hierarchicalChildren", params={"page": page, "size": size, "sort": sort, "includeObsoleteEntities": include_obsolete_entities, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


@server.tool()
async def api_get_hierarchical_ancestors_by_ontology_2(onto: str, p_class: str, page: int | None = None, size: int | None = None, sort: list | None = None, include_obsolete_entities: bool | None = None, lang: str | None = None, resolve_references: bool | None = None, manchester_syntax: bool | None = None) -> Any:
    "GET /api/v2/ontologies/{onto}/classes/{class}/hierarchicalAncestors\n\npage: Zero-based page index (0..N)\nsize: The size of the page to be returned\nsort: Sorting criteria in the format: property,(asc|desc). Default sort order is ascending. Multiple sort criteria are supported.\nonto: Ontology Id to get the information about.\nclass: The IRI of the class, this value must be double URL encoded\nincludeObsoleteEntities: A boolean parameter to specify if obsolete entities should be included or not. Default value is false.\nresolveReferences: Whether to resolve any referenced entities inline in the response JSON. Otherwise linked entities will be available in the linkedEntities map.\nmanchesterSyntax: Whether to convert class expressions to Manchester syntax. If false a JSON representation of the class expressions will be returned."
    return clip(await request("GET", BASE + f"/api/v2/ontologies/{_q(onto)}/classes/{_q(p_class)}/hierarchicalAncestors", params={"page": page, "size": size, "sort": sort, "includeObsoleteEntities": include_obsolete_entities, "lang": lang, "resolveReferences": resolve_references, "manchesterSyntax": manchester_syntax},
                              json_body=None, headers=_auth()))


if __name__ == "__main__":
    server.run()
