# FlowGuard Makefile. Targets marked (planned) are not implemented yet; they fail loudly instead of pretending.
PY ?= $(CURDIR)/.venv-core/bin/python
SHELL := /bin/bash

.PHONY: help setup doctor docs docs-check test spike demo start eval test-e2e test-security test-soak

help:
	@echo "FlowGuard targets:"
	@echo "  make setup        install system packages and venvs (scripts/setup_ubuntu.sh)"
	@echo "  make doctor       check the environment"
	@echo "  make docs         regenerate tables and graphs from docs/graphs/status.json"
	@echo "  make docs-check   fail if generated docs are stale"
	@echo "  make test         run the unit tests available in this phase"
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

test:
	$(PY) -m pytest tests -q

spike:
	bash scripts/spike/run_all.sh

start demo eval test-e2e test-security test-soak:
	@echo "make $@: not implemented yet (planned, see ROADMAP.md)"; exit 2
