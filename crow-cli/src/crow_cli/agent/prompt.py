"""
Prompt template management - functional, minimal.

Renders Jinja2 templates with stored arguments.
"""

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


@lru_cache(maxsize=64)
def get_jinja_env() -> Environment:
    """Cached Jinja environment for template rendering"""
    # Use FileSystemLoader to support {% include %} directives
    prompts_dir = Path(__file__).parent / "prompts"
    return Environment(
        loader=FileSystemLoader(prompts_dir),
        autoescape=False,
    )


def render_template(template_str: str, **args) -> str:
    """
    Render a Jinja2 template string with args.
    
    Args:
        template_str: Jinja2 template content
        **args: Template variables
        
    Returns:
        Rendered template string
    """
    env = get_jinja_env()
    template = env.from_string(template_str)
    return template.render(**args).strip()
