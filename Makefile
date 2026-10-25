PYTHON ?= python
CASE ?=
K ?=
CASE_TEST := tests/protected/cases/test_hook_cases.py::test_hook_case_matches_its_baseline

.PHONY: test test-unit test-integration test-cases test-case debug-case debug-test bless-case lint typecheck \
        publish version-minor version-major

## Everything that CI runs.
test: lint typecheck
	$(PYTHON) -m pytest

test-unit:
	$(PYTHON) -m pytest tests/protected/unit

test-integration:
	$(PYTHON) -m pytest tests/protected/integration

test-cases:
	$(PYTHON) -m pytest tests/protected/cases

## One case: make test-case CASE=claude-edit-of-protected-test-is-denied
test-case:
	$(PYTHON) -m pytest "$(CASE_TEST)[$(CASE)]"

## One case under pdb, without pytest frames.
debug-case:
	$(PYTHON) -m pdb tests/protected/cases/case_runner.py $(CASE)

## One test under pdb, stopping at the failure: make debug-test K=<name part>
debug-test:
	$(PYTHON) -m pytest --pdb -x -k "$(K)"

## Rewrite the baselines of one case. Read the diff line by line before a commit.
bless-case:
	$(PYTHON) tests/protected/cases/case_runner.py $(CASE) --write

lint:
	$(PYTHON) -m ruff format --check src tests
	$(PYTHON) -m ruff check src tests

typecheck:
	$(PYTHON) -m mypy

# A release is a pushed v* tag: .github/workflows/publish.yml tests, builds and
# uploads it to PyPI. If version-minor or version-major set a version that has
# no release yet, publish releases that version without a bump.

## Bump the patch, commit, tag and push. GitHub Actions publishes to PyPI.
publish:
	$(PYTHON) scripts/release.py publish

## Start the next minor version. Commits, does not tag.
version-minor:
	$(PYTHON) scripts/release.py bump minor

## Start the next major version. Commits, does not tag.
version-major:
	$(PYTHON) scripts/release.py bump major
