#!/usr/bin/env python3
"""Start the browser from its compiled module.

`python3 browser.py` runs the file as __main__, and Python never keeps
bytecode for the script it is started with: all 84k lines were compiled
again on every start (about 0.6 s). Imported as a module it comes from
__pycache__ (or from what the package compiled at install). Use this
as the program to run; browser.py still works directly."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import browser  # noqa: E402

sys.exit(browser.main())
