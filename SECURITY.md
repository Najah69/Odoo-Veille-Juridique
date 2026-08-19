# Security policy

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository
("Security" tab → "Report a vulnerability") rather than opening a public
issue, so a real, exploitable weakness isn't disclosed before a fix is
available. For anything that isn't sensitive (a hardening suggestion, a
question about the threat model), a regular issue is fine.

## What's already documented

`docs/security.md` is the maintained security audit for this module:
access control, secrets handling, outbound-network (SSRF/redirect/size)
hardening, deletion/retention behavior, AI data handling, and — just as
important — the residual risks that are known and deliberately deferred
rather than silently unaddressed. Read it before reporting something that
might already be a documented, accepted tradeoff (e.g. hostname-based
SSRF via DNS is explicitly out of scope for the current `url_safety.py`
design, for reasons explained there).

## Supported versions

This module tracks Odoo 18.0 Community only. There is no separate
long-term-support branch; the latest tagged version on the default branch
is the one that receives fixes.
