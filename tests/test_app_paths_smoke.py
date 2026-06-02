from __future__ import annotations

import unittest

from tests.core import test_app_paths


def load_tests(
    loader: unittest.TestLoader,
    standard_tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del standard_tests
    if pattern is not None:
        return unittest.TestSuite()

    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(test_app_paths.AppPathSmokeTest))
    return suite
