# OCA DMS integration (optional)

# Intégration OCA DMS (optionnelle)

`legal_knowledge_watch` never depends on `dms` in its manifest. Every
`dms.*` reference lives in one isolated file,
`legal_knowledge_watch/services/storage_dms.py`, and is only ever touched
at runtime after checking `"dms.file" in self.env` — the module installs
and works fully on the `ir.attachment` fallback alone.

`legal_knowledge_watch` ne dépend jamais de `dms` dans son manifeste.
Toute référence à `dms.*` vit dans un unique fichier isolé,
`legal_knowledge_watch/services/storage_dms.py`, et n'est touchée qu'au
moment de l'exécution après vérification de `"dms.file" in self.env` —
le module s'installe et fonctionne pleinement sur le seul repli
`ir.attachment`.

## What was actually verified / Ce qui a réellement été vérifié

The field names below were read directly from the real
[OCA/dms](https://github.com/OCA/dms) source, branch `18.0`
(`dms/models/dms_file.py`, `directory.py`, `storage.py`, `tag.py`,
`dms_category.py`) — not guessed. This was **not** tested against a live
DMS install (none was available in this environment); that is the one
thing still worth confirming before relying on this in production.

Les noms de champs ci-dessous ont été lus directement dans le vrai code
source [OCA/dms](https://github.com/OCA/dms), branche `18.0`
(`dms/models/dms_file.py`, `directory.py`, `storage.py`, `tag.py`,
`dms_category.py`) — jamais devinés. Ceci n'a **pas** été testé contre
une installation DMS réelle (aucune n'était disponible dans cet
environnement) ; c'est la seule chose qui mérite encore d'être confirmée
avant de s'y fier en production.

| Model / Modèle | Fields used / Champs utilisés | Source confirmed / Source confirmée |
|---|---|---|
| `dms.file` | `name` (required / requis), `directory_id` (required Many2one to `dms.directory` / Many2one requis vers `dms.directory`), `content` (Binary, base64) | `dms/models/dms_file.py` |
| `dms.directory` | `name`, `parent_id`, `storage_id`, `is_root_directory` | `dms/models/directory.py` |
| `dms.storage` | `name`, `save_type` (`database`/`file`/`attachment`), `company_id` | `dms/models/storage.py` |
| `dms.tag` | `name`, `category_id`, `color` | `dms/models/tag.py` |
| `dms.category` | `name`, `parent_id` | `dms/models/dms_category.py` |

Confirmed: `self.env["dms.file"].create({"name": ..., "directory_id": ...,
"content": <base64>})` is a complete, correct minimal create call —
`dms.file.create()` (in `dms_file.py`) handles the underlying storage
mechanics (database/filestore/attachment, per the target directory's
`dms.storage.save_type`) internally; this module does not need to care
which one is configured.

Confirmé : `self.env["dms.file"].create({"name": ..., "directory_id":
..., "content": <base64>})` est un appel de création minimal complet et
correct — `dms.file.create()` (dans `dms_file.py`) gère en interne la
mécanique de stockage sous-jacente (base de données/filestore/pièce
jointe, selon le `dms.storage.save_type` du répertoire cible) ; ce module
n'a pas besoin de savoir lequel est configuré.

**Still to validate against a live DMS install** before production use:
whether the acting user's (or `sudo()`'s) access is actually accepted by
DMS's own `dms.security.mixin` permission layer on the configured
directories — this module does not attempt to configure that for you (see
"Access Groups" below).

**Reste à valider contre une installation DMS réelle** avant une mise en
production : est-ce que l'accès de l'utilisateur agissant (ou du
`sudo()`) est bien accepté par la propre couche de permissions
`dms.security.mixin` de DMS sur les répertoires configurés — ce module
ne tente pas de configurer cela à votre place (voir « Groupes d'accès »
plus bas).

## Why a plain Integer, not a Many2one / Pourquoi un simple Integer, pas un Many2one

`legal.document.version.dms_file_res_id` and
`legal.dms.directory.route.dms_directory_id` are plain `fields.Integer`,
not `fields.Many2one(comodel_name="dms.file"/"dms.directory")`. A Many2one
requires its comodel to exist in the registry — which would break
installability (and every existing test) on a database without OCA DMS.
The tradeoff: no autocomplete/clickable widget for these fields unless DMS
is installed and someone builds one as a follow-up.

`legal.document.version.dms_file_res_id` et
`legal.dms.directory.route.dms_directory_id` sont de simples
`fields.Integer`, pas des `fields.Many2one(comodel_name="dms.file"/
"dms.directory")`. Un Many2one exige que son comodèle existe dans le
registre — ce qui casserait l'installabilité (et tous les tests
existants) sur une base sans OCA DMS. La contrepartie : pas de widget
autocomplétion/cliquable pour ces champs, sauf si DMS est installé et que
quelqu'un en construit un en complément plus tard.

## Enabling DMS storage / Activer le stockage DMS

1. Install OCA DMS (`dms` module) and configure at least one `dms.storage`
   and one root `dms.directory` as you normally would.
   <br>Installer OCA DMS (module `dms`) et configurer au moins un
   `dms.storage` et un `dms.directory` racine, comme d'habitude.
2. Note the numeric id of the directory(ies) you want this module to file
   into (open the directory record, read the id from the URL, or from
   Settings > Technical > Database Structure > Records).
   <br>Noter l'id numérique du/des répertoire(s) dans lesquels ce module
   doit classer (ouvrir l'enregistrement du répertoire, lire l'id dans
   l'URL, ou via Réglages > Technique > Structure de la base > Records).
3. Either set a single default via **Technical > System Parameters**:
   key `legal_knowledge_watch.dms_default_directory_id`, value = that id;
   or configure per-tag/per-company routes under **Legal Knowledge Watch >
   Configuration > DMS Directory Routing** (`legal.dms.directory.route`:
   tag + company → directory id; leave tag empty for a company's
   default/catch-all route).
   <br>Soit définir une valeur par défaut unique via **Technique >
   Paramètres système** : clé `legal_knowledge_watch.dms_default_directory_id`,
   valeur = cet id ; soit configurer des routes par tag/par société sous
   **Legal Knowledge Watch > Configuration > Routage des répertoires
   DMS** (`legal.dms.directory.route` : tag + société → id de répertoire ;
   laisser le tag vide pour la route par défaut/fourre-tout d'une
   société).
4. Set a `legal.watch`'s (or the manual-import wizard's) **Storage Mode**
   to `dms` (always required) or `auto` (DMS if installed, `ir.attachment`
   otherwise).
   <br>Positionner le **Mode de stockage** d'une `legal.watch` (ou de
   l'assistant d'import manuel) sur `dms` (toujours requis) ou `auto`
   (DMS si installé, sinon `ir.attachment`).

## Fallback behavior (fail closed, never silent) / Comportement de repli (échec fermé, jamais silencieux)

| Storage Mode / Mode | DMS installed / DMS installé | DMS not installed / DMS non installé |
|---|---|---|
| `attachment` | Always `ir.attachment`, regardless. <br>Toujours `ir.attachment`, dans tous les cas. | Always `ir.attachment`. <br>Toujours `ir.attachment`. |
| `auto` | `dms.file`. | `ir.attachment`. |
| `dms` | `dms.file`. | **Raises a clear error** (`LegalStorageError`, a `UserError`) — the import/ingestion of that item fails visibly (surfaces in the wizard, or as a `partial`/`failed` `legal.ingestion.run` with the message in `log_excerpt`). Never silently falls back to attachment. <br>**Lève une erreur claire** (`LegalStorageError`, un `UserError`) — l'import/l'ingestion de cet élément échoue visiblement (remonte dans l'assistant, ou sous forme de `legal.ingestion.run` `partial`/`failed` avec le message dans `log_excerpt`). Jamais de repli silencieux vers l'attachment. |

`dms` mode with no directory route configured at all (no
`legal.dms.directory.route` match and no
`ir.config_parameter dms_default_directory_id`) fails the same way, with a
message naming the company that needs a route.

Le mode `dms` sans aucune route de répertoire configurée (aucune
correspondance `legal.dms.directory.route` et aucun
`ir.config_parameter dms_default_directory_id`) échoue de la même
manière, avec un message nommant la société qui a besoin d'une route.

## Preserving history across a backend switch / Préserver l'historique lors d'un changement de backend

Storage backend is recorded **per version**
(`legal.document.version.storage_backend`), not per document. Changing a
watch's Storage Mode only affects *future* versions — past versions keep
pointing at whatever backend actually stored them. There is no automatic
migration of already-stored content between backends in this phase.

Le backend de stockage est enregistré **par version**
(`legal.document.version.storage_backend`), pas par document. Changer le
mode de stockage d'une veille n'affecte que les *futures* versions — les
versions passées continuent de pointer vers le backend qui les a
réellement stockées. Il n'y a aucune migration automatique du contenu
déjà stocké entre backends à cette phase.

## Access Groups (DMS's own permission layer) / Groupes d'accès (la propre couche de permissions de DMS)

DMS writes in this module use `sudo()` deliberately: this module's own
groups (`User`/`Reviewer`/`Manager`/`Administrator`) already gate who may
trigger an ingestion or manual import, and coupling that to DMS's separate
per-directory "Access Groups" system would make ingestion fail for reasons
configured entirely outside this module. If you want DMS-native users to
browse the resulting `dms.file` records directly in the DMS UI (not just
via this module's "Open in DMS" button), configure DMS's Access Groups on
the target directories yourself — this module does not attempt to infer or
manage that.

Les écritures DMS de ce module utilisent délibérément `sudo()` : les
propres groupes de ce module (`User`/`Reviewer`/`Manager`/
`Administrator`) contrôlent déjà qui peut déclencher une ingestion ou un
import manuel, et lier cela au système séparé de « Groupes d'accès » par
répertoire de DMS ferait échouer l'ingestion pour des raisons configurées
entièrement en dehors de ce module. Si vous voulez que des utilisateurs
natifs DMS parcourent directement les `dms.file` résultants dans
l'interface DMS (pas seulement via le bouton « Ouvrir dans DMS » de ce
module), configurez vous-même les Groupes d'accès de DMS sur les
répertoires cibles — ce module ne tente ni de les déduire ni de les
gérer.
