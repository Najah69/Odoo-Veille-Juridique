# Security policy / Politique de sécurité

## Reporting a vulnerability / Signaler une vulnérabilité

Please use GitHub's private vulnerability reporting for this repository
("Security" tab → "Report a vulnerability") rather than opening a public
issue, so a real, exploitable weakness isn't disclosed before a fix is
available. For anything that isn't sensitive (a hardening suggestion, a
question about the threat model), a regular issue is fine.

Merci d'utiliser le signalement privé de vulnérabilité de GitHub pour ce
dépôt (onglet « Security » → « Report a vulnerability ») plutôt que
d'ouvrir une issue publique, afin qu'une faille réelle et exploitable ne
soit pas divulguée avant qu'un correctif soit disponible. Pour tout ce
qui n'est pas sensible (une suggestion de durcissement, une question sur
le modèle de menace), une issue normale convient très bien.

## What's already documented / Ce qui est déjà documenté

`docs/security.md` is the maintained security audit for this module:
access control, secrets handling, outbound-network (SSRF/redirect/size)
hardening, deletion/retention behavior, AI data handling, and — just as
important — the residual risks that are known and deliberately deferred
rather than silently unaddressed. Read it before reporting something that
might already be a documented, accepted tradeoff (e.g. hostname-based
SSRF via DNS is explicitly out of scope for the current `url_safety.py`
design, for reasons explained there).

`docs/security.md` est l'audit sécurité maintenu de ce module : contrôle
d'accès, gestion des secrets, durcissement du réseau sortant
(SSRF/redirection/taille), comportement de suppression/rétention,
traitement des données par l'IA, et — tout aussi important — les risques
résiduels connus et volontairement différés plutôt que passés sous
silence. Lisez-le avant de signaler quelque chose qui pourrait déjà être
un compromis documenté et accepté (ex : le SSRF par nom d'hôte via DNS
est explicitement hors du périmètre de la conception actuelle de
`url_safety.py`, pour les raisons expliquées là-bas).

## Supported versions / Versions prises en charge

This module tracks Odoo 18.0 Community only. There is no separate
long-term-support branch; the latest tagged version on the default branch
is the one that receives fixes.

Ce module ne suit qu'Odoo 18.0 Community. Il n'existe pas de branche
support long terme séparée ; c'est la dernière version taguée sur la
branche par défaut qui reçoit les correctifs.
