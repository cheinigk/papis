import os
from typing import Dict, Any, List, Optional, Sequence, Tuple

import tqdm
import colorama

import papis.config
import papis.database
import papis.crossref
import papis.yaml
import papis.utils
import papis.logging
from papis.document import Document, to_dict

logger = papis.logging.get_logger(__name__)

Citation = Dict[str, Any]
Citations = Sequence[Citation]


def get_metadata_citations(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Get the citations in the metadata that contains a doi.
    """
    return [cit for cit in doc.get("citations", [])
            if isinstance(cit, dict) and "doi" in cit]


def _delete_citations_key(citations: Citations) -> None:
    # remove the citations from dois_with_data, it would be too much
    for data in citations:
        if "citations" in data:
            del data["citations"]


def fetch_citations(doc: Document) -> List[Dict[str, Any]]:
    metadata_citations = get_metadata_citations(doc)
    if not metadata_citations:
        if doc.has("doi"):
            logger.debug("trying with doi '%s'", doc["doi"])
            data = papis.crossref.doi_to_data(doc["doi"])
            metadata_citations = get_metadata_citations(data)
            if not metadata_citations:
                raise ValueError("We could not retrieve citations from the doi"
                                 " '{}'".format(doc["doi"]))
        else:
            raise ValueError("No possible finding citations "
                             "in '{}' due to lack of doi "
                             .format(doc))

    dois = [str(d.get("doi")).lower() for d in metadata_citations
            if "doi" in d]
    logger.info("%d citations found to query", len(dois))

    dois_with_data = [
    ]  # type: List[Dict[str, Any]]
    found_in_lib_dois = [
    ]  # type: List[Dict[str, Any]]

    logger.info("Checking which citations are already in the library")
    dois_with_data = get_citations_from_database(dois)

    for data in dois_with_data:
        doi = data.get("doi", "").lower()
        if doi:
            dois.remove(doi)

    logger.info("Found %d DOIs in library", len(found_in_lib_dois))
    logger.info("Fetching %d citations from crossref", len(dois))

    with tqdm.tqdm(iterable=dois) as progress:
        for doi in progress:
            _data = papis.crossref.get_data(dois=[doi])
            progress.set_description("{c.Fore.GREEN}{c.Back.BLACK}"
                                     "{0: <22.22}{c.Style.RESET_ALL}"
                                     .format(doi, c=colorama))
            if _data:
                dois_with_data.extend(_data)

    _delete_citations_key(dois_with_data)

    return dois_with_data


def get_citations_from_database(
        dois: Sequence[str]) -> List[Dict[str, Any]]:
    """
    Look for dois in the database from a list of dois,
    and return a sequence of data from the database
    with the information of these documents.
    """
    db = papis.database.get()
    dois_with_data = []  # type: List[Dict[str, Any]]
    with tqdm.tqdm(iterable=dois) as progress:
        for doi in progress:
            citation = db.query_dict({"doi": doi})
            if citation:
                progress.set_description("{c.Fore.GREEN}{c.Back.BLACK}"
                                         "{0: <22.22}"
                                         "{c.Style.RESET_ALL}"
                                         .format(doi, c=colorama))
                data = to_dict(citation[0])
                dois_with_data.append(data)
            else:
                progress.set_description("{c.Fore.RED}{c.Back.BLACK}"
                                         "{0: <22.22}{c.Style.RESET_ALL}"
                                         .format(doi, c=colorama))
    return dois_with_data


def update_and_save_citations_from_database_from_doc(doc: Document) -> None:
    citations = get_citations(doc)
    new_citations = update_citations_from_database(citations)
    save_citations(doc, new_citations)


def update_citations_from_database(citations: Citations) -> Citations:
    new_citations = []  # type: List[Dict[str, Any]]
    dois = [str(c.get("doi")).lower() for c in citations
            if "doi" in c]
    new_data_list = get_citations_from_database(dois)
    for data in new_data_list:
        doi = data.get("doi", "").lower()
        if doi:
            dois.remove(doi)
    new_citations.extend(new_data_list)
    for citation in citations:
        doi = citation.get("doi")
        if doi and doi not in dois:
            continue
        new_citations.append(citation)
    _delete_citations_key(new_citations)
    return new_citations


def save_citations(doc: Document, citations: Citations) -> None:
    file_path = get_citations_file(doc)
    if not file_path:
        return
    papis.yaml.list_to_path(citations, file_path)


def fetch_and_save_citations(doc: Document) -> None:
    citations = fetch_citations(doc)
    if citations:
        save_citations(doc, citations)


def get_citations_file(doc: Document) -> Optional[str]:
    folder = doc.get_main_folder()
    file_name = papis.config.getstring("citations-file-name")
    if not folder:
        return None
    return os.path.join(folder, file_name)


def has_citations(doc: Document) -> bool:
    file_path = get_citations_file(doc)
    if not file_path:
        return False
    return os.path.exists(file_path)


def get_citations(doc: Document) -> Citations:
    if has_citations(doc):
        file_path = get_citations_file(doc)
        if not file_path:
            return []
        return papis.yaml.yaml_to_list(file_path)
    return []

# =============================================================================
# CITED BY FUNCTIONS
# =============================================================================


def get_cited_by_file(doc: Document) -> Optional[str]:
    folder = doc.get_main_folder()
    file_name = papis.config.getstring("cited-by-file-name")
    if not folder:
        return None
    return os.path.join(folder, file_name)


def has_cited_by(doc: Document) -> bool:
    file_path = get_cited_by_file(doc)
    if not file_path:
        return False
    return os.path.exists(file_path)


def save_cited_by(doc: Document, citations: Citations) -> None:
    file_path = get_citations_file(doc)
    if not file_path:
        return
    papis.yaml.list_to_path(citations, file_path)


def _cites_me_p(doi_doc: Tuple[str, Document]) -> Optional[Citation]:
    doi, doc = doi_doc
    if not has_citations(doc):
        return None
    citations = get_citations(doc)
    found = [c for c in citations
             if c.get("doi", "").lower() == doi]
    if found:
        return to_dict(doc)
    return None


def fetch_cited_by_from_database(cit: Citation) -> Citations:
    doi = str(cit.get("doi", "")).lower()
    if not doi:
        return []

    result = []  # type: List[Citation]
    db = papis.database.get()
    documents = db.get_all_documents()

    # NOTE: using parmap makes it around 2.5x faster with an ssd
    # in a 2k documents library
    result = [d for d in papis.utils.parmap(_cites_me_p,
                                            [(doi, x) for x in documents])
              if d is not None]

    _delete_citations_key(result)
    return result


def fetch_and_save_cited_by_from_database(doc: Document) -> None:
    citations = fetch_cited_by_from_database(doc)
    file_path = get_cited_by_file(doc)
    if citations and file_path:
        papis.yaml.list_to_path(citations, file_path)


def get_cited_by(doc: Document) -> Citations:
    if has_cited_by(doc):
        file_path = get_cited_by_file(doc)
        if not file_path:
            return []
        return papis.yaml.yaml_to_list(file_path)
    return []
