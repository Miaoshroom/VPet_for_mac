from __future__ import annotations

import unittest
import importlib.util
from pathlib import Path


def load_tests(
    loader: unittest.TestLoader,
    standard_tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    suite.addTests(standard_tests)
    test_root = Path(__file__).resolve().parent
    for child in ("core", "raising", "ui"):
        for test_file in sorted((test_root / child).glob(pattern or "test*.py")):
            module_name = f"tests_{child}_{test_file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, test_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            suite.addTests(loader.loadTestsFromModule(module))
    return suite
