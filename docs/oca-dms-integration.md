# OCA DMS integration (optional)

`legal_knowledge_watch` never depends on `dms` in its manifest. Every
`dms.*` reference lives in one isolated file,
`legal_knowledge_watch/services/storage_dms.py`, and is only ever touched
at runtime after checking `"dms.file" in self.env` — the module installs
and works fully on the `ir.attachment` fallback alone.

## What was actually verified

The field names below were read directly from the real
[OCA/dms](https://github.com/OCA/dms) source, branch `18.0`
(`dms/models/dms_file.py`, `directory.py`, `storage.py`, `tag.py`,
`dms_category.py`) — not guessed. This was **not** tested against a live
DMS install (none was available in this environment); that is the one
thing still worth confirming before relying on this in production.

| Model | Fields used | Source confirmed |
|---|---|---|
| `dms.file` | `name` (required), `directory_id` (required Many2one to `dms.directory`), `content` (Binary, base64) | `dms/models/dms_file.py` |
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

**Still to validate against a live DMS install** before production use:
whether the acting user's (or `sudo()`'s) access is actually accepted by
DMS's own `dms.security.mixin` permission layer on the configured
directories — this module does not attempt to configure that for you (see
"Access Groups" below).

## Why a plain Integer, not a Many2one

`legal.document.version.dms_file_res_id` and
`legal.dms.directory.route.dms_directory_id` are plain `fields.Integer`,
not `fields.Many2one(comodel_name="dms.file"/"dms.directory")`. A Many2one
requires its comodel to exist in the registry — which would break
installability (and every existing test) on a database without OCA DMS.
The tradeoff: no autocomplete/clickable widget for these fields unless DMS
is installed and someone builds one as a follow-up.

## Enabling DMS storage

1. Install OCA DMS (`dms` module) and configure at least one `dms.storage`
   and one root `dms.directory` as you normally would.
2. Note the numeric id of the directory(ies) you want this module to file
   into (open the directory record, read the id from the URL, or from
   Settings > Technical > Database Structure > Records).
3. Either set a single default via **Technical > System Parameters**:
   key `legal_knowledge_watch.dms_default_directory_id`, value = that id;
   or configure per-tag/per-company routes under **Legal Knowledge Watch >
   Configuration > DMS Directory Routing** (`legal.dms.directory.route`:
   tag + company → directory id; leave tag empty for a company's
   default/catch-all route).
4. Set a `legal.watch`'s (or the manual-import wizard's) **Storage Mode**
   to `dms` (always required) or `auto` (DMS if installed, `ir.attachment`
   otherwise).

## Fallback behavior (fail closed, never silent)

| Storage Mode | DMS installed | DMS not installed |
|---|---|---|
| `attachment` | Always `ir.attachment`, regardless. | Always `ir.attachment`. |
| `auto` | `dms.file`. | `ir.attachment`. |
| `dms` | `dms.file`. | **Raises a clear error** (`LegalStorageError`, a `UserError`) — the import/ingestion of that item fails visibly (surfaces in the wizard, or as a `partial`/`failed` `legal.ingestion.run` with the message in `log_excerpt`). Never silently falls back to attachment. |

`dms` mode with no directory route configured at all (no
`legal.dms.directory.route` match and no
`ir.config_parameter dms_default_directory_id`) fails the same way, with a
message naming the company that needs a route.

## Preserving history across a backend switch

Storage backend is recorded **per version**
(`legal.document.version.storage_backend`), not per document. Changing a
watch's Storage Mode only affects *future* versions — past versions keep
pointing at whatever backend actually stored them. There is no automatic
migration of already-stored content between backends in this phase.

## Access Groups (DMS's own permission layer)

DMS writes in this module use `sudo()` deliberately: this module's own
groups (`User`/`Reviewer`/`Manager`/`Administrator`) already gate who may
trigger an ingestion or manual import, and coupling that to DMS's separate
per-directory "Access Groups" system would make ingestion fail for reasons
configured entirely outside this module. If you want DMS-native users to
browse the resulting `dms.file` records directly in the DMS UI (not just
via this module's "Open in DMS" button), configure DMS's Access Groups on
the target directories yourself — this module does not attempt to infer or
manage that.
