"""Trusted QA harness, copied into a read-only image; NEVER import on the worker.

The approved test overlay executes only inside the restricted Docker container.
No shell, network package installation or arbitrary command profile is exposed.
"""

import compileall
import json
import subprocess
import sys
import unittest


def main():
    stage = int(sys.argv[2])
    if sys.argv[1] == "build":
        if not compileall.compile_dir("/workspace", quiet=1):
            return 1
        if stage == 1:
            for command in (
                ["ruff", "check", "--isolated", "--no-cache", "."],
                ["ruff", "format", "--isolated", "--check", "--no-cache", "."],
            ):
                print(json.dumps({"command": command}), flush=True)
                if subprocess.run(command, check=False).returncode:
                    return 1
        return 0

    results = []

    class Result(unittest.TextTestResult):
        def addSuccess(self, test):
            super().addSuccess(test)
            results.append({"id": test.id(), "status": "PASS"})

        def addFailure(self, test, err):
            super().addFailure(test, err)
            results.append({"id": test.id(), "status": "FAIL"})

        def addError(self, test, err):
            super().addError(test, err)
            results.append({"id": test.id(), "status": "FAIL"})

        def addSkip(self, test, reason):
            super().addSkip(test, reason)
            results.append({"id": test.id(), "status": "BLOCKED"})

        def addExpectedFailure(self, test, err):
            super().addExpectedFailure(test, err)
            results.append({"id": test.id(), "status": "BLOCKED"})

        def addUnexpectedSuccess(self, test):
            super().addUnexpectedSuccess(test)
            results.append({"id": test.id(), "status": "FAIL"})

        def addSubTest(self, test, subtest, err):
            super().addSubTest(test, subtest, err)
            if err:
                results.append({"id": test.id(), "status": "FAIL"})

    # -I removes cwd from sys.path. Explicitly allow only the isolated snapshot.
    sys.path.insert(0, "/workspace")
    suite = unittest.defaultTestLoader.discover(f"aiventra_qa/round_{stage}", top_level_dir=".")
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(suite)
    print("AIVENTRA_QA_RESULT=" + json.dumps({"tests": result.testsRun, "cases": results}), flush=True)
    return 0 if result.wasSuccessful() and result.testsRun else 1


if __name__ == "__main__":
    raise SystemExit(main())
