# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import datetime
import json
import os
import sys
from pathlib import Path

project = "Squiggle Automation"
copyright = "{}, Sven Hertle".format(datetime.datetime.now().year)
author = "Sven Hertle"

# -- API reference -------------------------------------------------------------
# The API reference (api/index.rst) is rendered from an OpenAPI schema, regenerated here on
# every doc build (via drf-spectacular, introspecting the live DRF views/serializers) so it
# never drifts from the actual API - see docs/source/api/index.rst.

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "squiggle_automation.settings")

import django  # noqa: E402

django.setup()

import jsonref  # noqa: E402
import yaml  # noqa: E402
from django.core.management import call_command  # noqa: E402

openapi_schema_path = Path(__file__).resolve().parent / "api" / "schema.yml"
openapi_schema_path.parent.mkdir(exist_ok=True)
call_command("spectacular", "--file", str(openapi_schema_path))

# sphinxcontrib-openapi doesn't resolve $ref (it renders the spec more or less verbatim), so
# without this, request/response bodies referencing a component schema (which is all of them -
# that's how drf-spectacular emits its schema) would render as empty objects. Inline everything
# so the rendered docs show the full body schema.
with openapi_schema_path.open() as f:
    schema = yaml.safe_load(f)
resolved_schema = jsonref.replace_refs(schema, lazy_load=False, proxies=False)
with openapi_schema_path.open("w") as f:
    yaml.safe_dump(json.loads(json.dumps(resolved_schema)), f, sort_keys=False)

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ["sphinx_rtd_theme", "sphinxcontrib.openapi"]

# sphinxcontrib-openapi's default renderer ("httpdomain:old") doesn't render request/response
# JSON bodies at all - use the newer one, which does.
openapi_default_renderer = "httpdomain"

templates_path = ["_templates"]
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
