"""Shared pytest configuration.

The full ``app`` package pulls heavy third-party dependencies (openai, camel,
graphiti) at import time. Tests that only exercise leaf utility modules avoid
that by loading the target file directly via ``importlib.util`` rather than
going through ``app/__init__.py``.
"""

import importlib.util
import os
import sys
import types

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def load_module_directly(module_name: str, source_path: str) -> types.ModuleType:
    """Load ``source_path`` as ``module_name`` without triggering parent packages."""
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {source_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
