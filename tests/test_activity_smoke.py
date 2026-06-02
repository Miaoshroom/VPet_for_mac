from __future__ import annotations

import unittest

from tests.raising import test_activity


def load_tests(
    loader: unittest.TestLoader,
    standard_tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del standard_tests
    if pattern is not None:
        return unittest.TestSuite()

    suite = unittest.TestSuite()
    for test_case in (
        test_activity.ActivitySystemSmokeTest,
        test_activity.PetWindowActivityWindowSyncSmokeTest,
        test_activity.PetWindowActivityBoundarySmokeTest,
    ):
        suite.addTests(loader.loadTestsFromTestCase(test_case))
    return suite
