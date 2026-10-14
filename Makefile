# FlowGuard Makefile. Targets marked (planned) are not implemented yet; they fail loudly instead of pretending.
PY ?= $(CURDIR)/.venv-core/bin/python
ENGINE_PY ?= $(CURDIR)/.venv-engine/bin/python
SHELL := /bin/bash

.PHONY: help setup doctor docs docs-check test test-live keygen spike demo start eval test-e2e test-security test-soak

help:
	@echo "FlowGuard targets:"
	@echo "  make setup        install system packages and venvs (scripts/setup_ubuntu.sh)"
	@echo "  make doctor       check the environment"
	@echo "  make docs         regenerate tables and graphs from docs/graphs/status.json"
	@echo "  make docs-check   fail if generated docs are stale"
	@echo "  make test         unit + property tests (both venvs)"
	@echo "  make test-live    live L1 attack tests (root; real OVS + Mininet + engine)"
	@echo "  make keygen       create the HMAC key file (mode 0600, outside the repo)"
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

# the pure engine modules must pass under Python 3.9 (engine venv) and 3.10 (core venv)
test:
	$(PY) -m pytest tests/unit -q -p no:cacheprovider
	$(ENGINE_PY) -m pytest tests/unit tests/engine -q -p no:cacheprovider

# needs root: boots Open vSwitch + Mininet + the real engine and attacks it with ovs-ofctl
test-live:
	$(PY) -m pytest tests/integration -q -p no:cacheprovider

keygen:
	bin/flowguard keygen

spike:
	bash scripts/spike/run_all.sh

start demo eval test-e2e test-security test-soak:
	@echo "make $@: not implemented yet (planned, see ROADMAP.md)"; exit 2
