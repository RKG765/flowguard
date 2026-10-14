"""FlowGuard core service: storage, REST + WebSocket API, auth, audit log, and ingest from the engine.

Runs in .venv-core (Python 3.10) as a separate process from the Ryu engine (ADR-002).
Start: .venv-core/bin/uvicorn --factory core.main:create_app --host 127.0.0.1 --port 8787
"""
