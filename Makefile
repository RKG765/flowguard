# FlowGuard Makefile. Targets marked (planned) are not implemented yet; they fail loudly instead of pretending.
PY ?= $(CURDIR)/.venv-core/bin/python
ENGINE_PY ?= $(CURDIR)/.venv-engine/bin/python
SHELL := /bin/bash
PYTEST_FLAGS := -q -p no:cacheprovider -W ignore::DeprecationWarning

.PHONY: help setup doctor docs docs-check test test-live keygen run-core spike demo start eval test-e2e test-security test-soak

help:
	@echo "FlowGuard targets:"
	@echo "  make setup        install system packages and venvs (scripts/setup_ubuntu.sh)"
	@echo "  make doctor       check the environment"
	@echo "  make docs         regenerate tables and graphs from docs/graphs/status.json"
	@echo "  make docs-check   fail if generated docs are stale"
	@echo "  make test         unit + property tests (both venvs) and core API tests"
	@echo "  make test-live    live tests (root; real OVS + Mininet + engine + core)"
	@echo "  make keygen       create the HMAC key file (mode 0600, outside the repo)"
	@echo "  make run-core     run the core API on http://127.0.0.1:8787 (development)"
	@echo "  make spike        re-run the Phase 0 feasibility spikes (needs root)"
	@echo "  (planned) start demo eval test-e2e test-security test-soak"

setup:
	bash scripts/setup_ubuntu.sh

doctor:
	python3 scripts/doctor.py

docs:
	$(PY) scripts/update_docs.py

docs-check:
	$(PY) scripts/update_docs.py --check

# the pure engine modules must pass under Python 3.9 (engine venv) and 3.10 (core venv); the core runs on 3.10
test:
	$(PY) -m pytest tests/unit tests/api $(PYTEST_FLAGS)
	$(ENGINE_PY) -m pytest tests/unit tests/engine $(PYTEST_FLAGS)

# needs root: boots Open vSwitch + Mininet + the real engine (and the core) and attacks it with ovs-ofctl
test-live:
	$(PY) -m pytest tests/integration $(PYTEST_FLAGS)

keygen:
	bin/flowguard keygen

run-core:
	$(CURDIR)/.venv-core/bin/uvicorn --factory core.main:create_app --host 127.0.0.1 --port 8787

spike:
	bash scripts/spike/run_all.sh

start demo eval test-e2e test-security test-soak:
	@echo "make $@: not implemented yet (planned, see ROADMAP.md)"; exit 2
