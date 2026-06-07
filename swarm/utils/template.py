"""Jinja2 template rendering utilities."""

from __future__ import annotations

from jinja2 import BaseLoader, Environment

_env = Environment(loader=BaseLoader())


def render_template(template_str: str, **kwargs) -> str:
    """Render a Jinja2 template string with the given variables."""
    template = _env.from_string(template_str)
    return template.render(**kwargs)
