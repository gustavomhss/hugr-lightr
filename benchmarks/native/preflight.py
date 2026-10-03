"""Fail closed on absent CLI options, missing controls, zero execution or skips."""
import argparse
import unittest
from unittest.mock import patch

import campaign
from evidence import require

with patch.object(argparse.ArgumentParser, "parse_args", autospec=True,
                  side_effect=RuntimeError("preflight parse interception")) as parse:
    try:
        campaign.main()
    except RuntimeError:
        pass
    require(parse.call_count == 1, "campaign CLI parser not reached exactly once")
    parser = parse.call_args.args[0]
    options = {option for action in parser._actions for option in action.option_strings}
    require({"--binary", "--source-dir", "--source-sha", "--build-receipt", "--out",
             "--rounds", "--warmups", "--sizes"} <= options, "campaign CLI interface incomplete")
names = ["test_orchestration.FixtureTests.test_unique_deterministic_payloads_and_modes",
         "test_orchestration.FixtureTests.test_untimed_deadline_retains_failure_before_acceptance"]
suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromNames(names))
require(suite.countTestCases() == 2 and all(len(part._tests) == 1 and
        isinstance(part._tests[0], unittest.TestCase) and part._tests[0].id() == name
        for part, name in zip(suite, names)), "required orchestration controls missing or empty")
result = unittest.TextTestRunner(verbosity=2).run(suite)
require(result.testsRun == 2 and not result.skipped and result.wasSuccessful(), "orchestration controls failed or skipped")
