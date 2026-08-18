"""Secrets abstraction shared by any connector needing credentials.
Environment variables take precedence over ir.config_parameter — see
docs/legifrance-piste.md. Values are only ever read for outbound HTTP
calls; never log or display what this returns.
"""
import os


def get_secret(env, param_key, env_var_name):
    value = os.environ.get(env_var_name)
    if value:
        return value
    return env["ir.config_parameter"].sudo().get_param(param_key) or None
