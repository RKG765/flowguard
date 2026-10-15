# FlowGuard Makefile. Targets marked (planned) are not implemented yet; they fail loudly instead of pretending.
PY ?= $(CURDIR)/.venv-core/bin/python
ENGINE_PY ?= $(CURDIR)/.venv-engine/bin/python
SHELL := /bin/bash
PYTEST_FLAGS := -q -p no:cacheprovider -W ignore::DeprecationWarning

.PHONY: help setup doctor docs docs-check test test-web test-e2e test-e2e-live build-web dev-web test-live keygen run-core spike demo present start eval test-security test-soak

help:
	@echo "FlowGuard targets:"
	@echo "  make setup        install system packages and venvs (scripts/setup_ubuntu.sh)"
	@echo "  make doctor       check the environment"
	@echo "  make docs         regenerate tables and graphs from docs/graphs/status.json"
	@echo "  make docs-check   fail if generated docs are stale"
	@echo "  make test         unit + property tests (both venvs), core API tests, web typecheck + unit tests"
	@echo "  make test-e2e     Playwright: real browser against a throw-away core (axe accessibility checks)"
	@echo "  make test-e2e-live  Playwright against a live lab + engine + core (root)"
	@echo "  make dev-web      dashboard dev server on http://127.0.0.1:5173 (proxies /api to the core)"
	@echo "  make build-web    production build of the dashboard (web/dist)"
	@echo "  make test-live    live tests (root; real OVS + Mininet + engine + core)"
	@echo "  make keygen       create the HMAC key file (mode 0600, outside the repo)"
	@echo "  make run-core     run the core API on http://127.0.0.1:8787 (development)"
	@echo "  make spike        re-run the Phase 0 feasibility spikes (needs root)"
	@echo "  make demo         sudo: lab + engine + core + dashboard on http://127.0.0.1:8787 (MODE=alert_only optional)"
	@echo "  make present      sudo: guided presentation demo (each step: what to show and say; detection + repair)"
	@echo "  (planned) start eval test-security test-soak"

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
	$(MAKE) test-web

test-web:
	cd web && npm run -s typecheck && npx vitest run

test-e2e:
	cd web && npx playwright test

# needs root (Mininet); browsers come from the invoking user's Playwright cache
PW_BROWSERS ?= $(if $(SUDO_USER),$(shell getent passwd $(SUDO_USER) | cut -d: -f6),$(HOME))/.cache/ms-playwright
test-e2e-live:
	cd web && PLAYWRIGHT_BROWSERS_PATH=$(PW_BROWSERS) npx playwright test -c playwright.live.config.ts; rc=$$?; \
	pkill -f "[r]yu-manager"; pkill -f "[e]2e_live/stack.py"; mn -c >/dev/null 2>&1; exit $$rc

build-web:
	cd web && npm run -s build

dev-web:
	cd web && npx vite

# needs root: boots Open vSwitch + Mininet + the real engine (and the core) and attacks it with ovs-ofctl
test-live:
	$(PY) -m pytest tests/integration $(PYTEST_FLAGS)

keygen:
	bin/flowguard keygen

run-core:
	$(CURDIR)/.venv-core/bin/uvicorn --factory core.main:create_app --host 127.0.0.1 --port 8787

spike:
	bash scripts/spike/run_all.sh

MODE ?= restore
demo:
	bash scripts/demo.sh $(MODE)

present:
	.venv-core/bin/python scripts/present.py

start eval test-security test-soak:
	@echo "make $@: not implemented yet (planned, see ROADMAP.md)"; exit 2
