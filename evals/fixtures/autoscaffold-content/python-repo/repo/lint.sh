#!/bin/sh
# Runs the pinned linter across the tree. Version is whatever is on PATH --
# see .github/workflows/ci.yml for the version this repo actually verifies in CI.
ruff --version
ruff check app utils
