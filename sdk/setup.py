"""
sdk/setup.py — thin backward-compatibility shim.

All real packaging metadata (name, version, dependencies, classifiers,
URLs, entry points) now lives in pyproject.toml (PEP 621) -- a single
source of truth, not duplicated here (this file previously declared the
same fields independently, which is exactly the kind of two-copies-of-
the-same-fact drift the rest of this platform has repeatedly needed
fixing for). Kept only so older tooling that expects a setup.py to exist
(e.g. `pip install -e .` on very old pip versions) keeps working; modern
pip/build read pyproject.toml directly and don't need this file at all.

    pip install -e .          (development, from this directory)
    pip install sentinel-apex-sdk   (production, once published to PyPI)
"""
from setuptools import setup

setup()
