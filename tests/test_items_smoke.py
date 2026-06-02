from __future__ import annotations

import unittest

from tests.ui import test_pet_care_flows


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
        test_pet_care_flows.ItemIconPathSmokeTest,
        test_pet_care_flows.ItemLogicSmokeTest,
        test_pet_care_flows.ItemUseWindowBoundarySmokeTest,
        test_pet_care_flows.AutoRefillWindowSmokeTest,
        test_pet_care_flows.ShopInventoryWindowSmokeTest,
        test_pet_care_flows.PetWindowShopInventorySyncSmokeTest,
    ):
        suite.addTests(loader.loadTestsFromTestCase(test_case))
    return suite
