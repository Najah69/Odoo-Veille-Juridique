"""Deduplication lookup used before creating a legal.knowledge.document.

Order of precedence (see docs/architecture.md):
1. (source_id, external_id) when external_id is known.
2. canonical_url within the same source.
3. content_hash, globally — catches an identical republication under a
   different source/URL without creating a duplicate document.

FR : Recherche de doublon effectuée avant de créer un
legal.knowledge.document.

Ordre de priorité (voir docs/architecture.md) :
1. (source_id, external_id) quand external_id est connu.
2. canonical_url au sein de la même source.
3. content_hash, globalement — détecte une republication identique sous
   une autre source/URL sans créer de document en double.
"""


def find_existing_document(env, source_id, external_id=None,
                            canonical_url=None, content_hash=None):
    """Return (document_recordset, match_type) where match_type is one of
    'external_id', 'canonical_url', 'content_hash' or None if nothing matched.
    The recordset is empty when match_type is None.

    FR : Retourne (document_recordset, match_type), match_type valant
    'external_id', 'canonical_url', 'content_hash' ou None si rien n'a
    correspondu. Le recordset est vide quand match_type vaut None.
    """
    document_model = env["legal.knowledge.document"]

    if external_id:
        document = document_model.search(
            [("source_id", "=", source_id), ("external_id", "=", external_id)],
            limit=1,
        )
        if document:
            return document, "external_id"

    if canonical_url:
        document = document_model.search(
            [("source_id", "=", source_id), ("canonical_url", "=", canonical_url)],
            limit=1,
        )
        if document:
            return document, "canonical_url"

    if content_hash:
        document = document_model.search(
            [("content_hash", "=", content_hash)], limit=1,
        )
        if document:
            return document, "content_hash"

    return document_model.browse(), None
