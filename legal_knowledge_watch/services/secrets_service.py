"""Secrets abstraction shared by any connector/provider needing
credentials. Environment variables take precedence over
ir.config_parameter — see docs/legifrance-piste.md and
docs/ai-providers.md. Values are only ever read for outbound HTTP calls;
never log or display what this returns.
"""
import os
import re


def _derive_env_var_name(param_key):
    """'legal_knowledge_watch.ai_brain.token' -> 'LKW_AI_BRAIN_TOKEN'."""
    stripped = re.sub(r"^legal_knowledge_watch\.", "", param_key)
    return "LKW_" + re.sub(r"[^A-Za-z0-9]+", "_", stripped).upper()


def get_secret(env, param_key, env_var_name=None):
    env_var_name = env_var_name or _derive_env_var_name(param_key)
    value = os.environ.get(env_var_name)
    if value:
        return value
    return env["ir.config_parameter"].sudo().get_param(param_key) or None
