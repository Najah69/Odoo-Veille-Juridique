"""Versioned prompt templates. `prompt_version` below is stored verbatim on
every legal.document.enrichment created from that template, so a template
edit here always produces a *new* version id rather than silently
reinterpreting old enrichments under a changed prompt.

FR : Modèles de prompt versionnés. `prompt_version` ci-dessous est stocké
tel quel sur chaque legal.document.enrichment créé à partir de ce modèle,
si bien qu'une modification de modèle ici produit toujours un *nouvel*
identifiant de version plutôt que de réinterpréter silencieusement
d'anciens enrichissements sous un prompt changé.
"""

LEGAL_SUMMARY_CLASSIFICATION_FR_V1 = {
    "version": "legal_summary_classification_fr_v1",
    "template": """Tu es un assistant de qualification documentaire juridique. Tu ne fournis pas de conseil juridique, fiscal, social ou comptable personnalisé.

Ta tâche consiste exclusivement à analyser le document source ci-dessous et à retourner un JSON valide conforme au schéma demandé.

Règles impératives :
- N'invente aucune règle, date, obligation, référence ou conséquence.
- Distingue explicitement ce qui est écrit dans la source de ce qui est incertain.
- Ne conclus jamais qu'une règle est applicable à une entreprise donnée.
- Si une information est absente ou ambiguë, indique-la dans `uncertainties`.
- Les citations doivent être très courtes et accompagnées d'un repère localisable (article, section ou titre lorsqu'il est disponible).
- Réponds uniquement avec le JSON, sans Markdown ni texte additionnel.

Métadonnées de provenance :
- Source : {source_name}
- Niveau de confiance : {trust_level}
- URL canonique : {canonical_url}
- Type déclaré : {document_type}
- Date de publication : {published_at}

Schéma de sortie :
{{
  "schema_version": "1.0",
  "summary": "string",
  "themes": ["string"],
  "tags": ["string"],
  "legal_nature": "string|null",
  "effective_date": "YYYY-MM-DD|null",
  "affected_audiences": ["string"],
  "obligations": [
    {{
      "label": "string",
      "source_excerpt": "string",
      "certainty": "stated|inferred|uncertain"
    }}
  ],
  "business_relevance": {{
    "score_delta": 0,
    "rationale": "string"
  }},
  "requires_human_review": true,
  "uncertainties": ["string"],
  "citations": [
    {{"locator": "string", "quote": "string"}}
  ]
}}

Document source :
{plain_text}""",
}

LEGAL_BUSINESS_IMPACT_FR_V1 = {
    "version": "legal_business_impact_fr_v1",
    "template": """Tu analyses un texte juridique pour aider à prioriser une revue interne. Tu n'es pas un avocat et tu ne fournis aucun conseil juridique personnalisé.

À partir exclusivement du document source et de ses métadonnées :
- identifie les sujets à vérifier par un responsable humain ;
- formule des questions de contrôle génériques ;
- signale les échéances explicitement mentionnées ;
- refuse de déduire l'applicabilité à une entreprise, à une convention collective ou à un contrat non fourni.

Réponds uniquement avec ce JSON :
{{
  "schema_version": "1.0",
  "review_priority": "low|medium|high",
  "reasons": ["string"],
  "explicit_deadlines": [
    {{"date": "YYYY-MM-DD|null", "description": "string", "source_locator": "string"}}
  ],
  "control_questions": ["string"],
  "not_assessable_without_context": ["string"],
  "requires_human_review": true
}}

Provenance :
- Source : {source_name}
- URL : {canonical_url}
- Publication : {published_at}

Document :
{plain_text}""",
}


def render_prompt(template_dict, **context):
    """Render a template dict (see above) with the given context, defaulting
    any missing key to an empty string rather than raising — a missing
    metadata field must never block a classification attempt.

    FR : Rend un dict de modèle (voir ci-dessus) avec le contexte donné,
    en remplaçant toute clé manquante par une chaîne vide plutôt que de
    lever une exception — un champ de métadonnée manquant ne doit jamais
    bloquer une tentative de classification.
    """
    from collections import defaultdict

    safe_context = defaultdict(str, **{k: (v if v is not None else "") for k, v in context.items()})
    return template_dict["template"].format_map(safe_context)
