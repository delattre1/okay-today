#!/usr/bin/env python3
"""Run the suite with nothing but the standard library.

`just test` uses pytest, which is the right tool and needs a network to fetch.
This runner exists so the same tests still run on a machine that has neither:
it understands the only fixture the suite uses (tmp_path) and reports the same
pass/fail line.
"""
import inspect
import os
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

import test_sinal  # noqa: E402


def main() -> int:
    tests = [(name, fn) for name, fn in vars(test_sinal).items()
             if name.startswith("test_") and callable(fn)]
    failures = []
    for name, fn in tests:
        try:
            if "tmp_path" in inspect.signature(fn).parameters:
                with tempfile.TemporaryDirectory() as tmp:
                    fn(tmp)
            else:
                fn()
            print(f"  ok    {name}")
        except Exception:
            failures.append((name, traceback.format_exc()))
            print(f"  FAIL  {name}")
    for name, tb in failures:
        print(f"\n=== {name}\n{tb}")
    print(f"\n{len(tests) - len(failures)} passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
