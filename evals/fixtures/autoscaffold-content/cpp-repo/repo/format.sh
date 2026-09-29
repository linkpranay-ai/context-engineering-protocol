#!/bin/sh
# Runs the pinned formatter across the tree. Version is whatever is on PATH --
# see .github/workflows/ci.yml for the version this repo actually verifies in CI.
clang-format --version
clang-format -i $(find alpha beta -name '*.cpp' -o -name '*.h')
