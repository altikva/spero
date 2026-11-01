<!--
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-11-01
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "Apache-2.0 (https://www.apache.org/licenses/LICENSE-2.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: How to contribute to Spero: the CLA, the branch and PR flow, and
#              the checks a pull request has to pass.
-->

# Contributing to Spero

Thank you for helping. Bug reports, fixes, new probes and remediations, and
documentation are all welcome.

## Contributor License Agreement

Before we can merge your first pull request, you need to sign the
[Spero Contributor License Agreement](./CLA.md). You keep the copyright in your
work and give ALTIKVA a broad license to use it, including under licenses other
than Apache-2.0. Signing is one comment on your pull request, and it covers all
your later ones. The `cla` check on the pull request tells you if anything is
missing.

Every commit has to be authored with an email linked to your GitHub account, so
the check can tell who wrote it.

If you contribute on behalf of an employer, make sure they allow it before you
sign. Open an issue if your employer needs to sign its own agreement.

## Making a change

1. Open an issue first for anything bigger than a small fix, so we can agree on
   the approach before you write it.
2. Fork the repository and create a topic branch off `main`: `feature/...`,
   `fix/...`, `docs/...` or `chore/...`.
3. Set up the environment and run the checks before you push:

   ```bash
   uv sync --locked --all-extras
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy
   uv run pytest
   ```

4. Open a pull request against `main`. Describe what changes and why, and how
   you tested it. CI runs the same checks on Python 3.11 to 3.14 and builds the
   Docker image.

## Ground rules for code

- Providers never raise on a failed command: they return a non-zero result.
- A destructive remediation (kill, rotate, delete a pod) may never run with
  `autonomy: auto`.
- No `shell=True`, anywhere.
- New behavior comes with tests. Tests use `tests/_fakes.py` and need no network.
- New source files start with the header block used across the repository.
