"""Resilience shim for environments where scikit-learn cannot be imported.

Both ``sentence_transformers`` and ``transformers`` import assorted symbols from
``sklearn`` at import time (e.g. ``pairwise_distances``, ``roc_curve``). On some
hosts the scikit-learn native DLLs are blocked (e.g. Windows Application Control
/ Smart App Control), which would crash embedding. This project never uses
scikit-learn (FAISS / torch handle similarity), so when the real import fails we
install a meta-path finder that turns ANY ``import sklearn[...]`` into a harmless
stub whose attributes are dummy callables (they raise only if actually invoked).

Import this module BEFORE importing ``sentence_transformers`` / ``transformers``.
"""
from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys
import types

from src.logging_config import get_logger

log = get_logger("shim")


class _StubModule(types.ModuleType):
    __path__: list = []  # mark as a package so submodule imports resolve

    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)

        def _unavailable(*_args, **_kwargs):  # pragma: no cover - never used here
            raise NotImplementedError(
                f"{self.__name__}.{name} is unavailable (scikit-learn is blocked on "
                "this host; this project does not use it)."
            )

        return _unavailable


class _SklearnStubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "sklearn" or fullname.startswith("sklearn."):
            return importlib.machinery.ModuleSpec(fullname, self)
        return None

    def create_module(self, spec):
        module = _StubModule(spec.name)
        module.__path__ = []
        return module

    def exec_module(self, module):  # nothing to execute for a stub
        pass


def _install() -> None:
    for name in [n for n in sys.modules if n == "sklearn" or n.startswith("sklearn.")]:
        del sys.modules[name]
    if not any(isinstance(f, _SklearnStubFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _SklearnStubFinder())
    log.warning("scikit-learn unavailable — installed import stub (sklearn not used).")


try:  # use the real library when it loads cleanly
    from sklearn.metrics import pairwise_distances, roc_curve  # noqa: F401
except Exception:  # noqa: BLE001 - blocked DLL, missing pkg, ABI mismatch, etc.
    _install()
