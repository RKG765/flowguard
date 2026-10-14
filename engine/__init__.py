"""FlowGuard engine: L1 authenticated flow rules for a Ryu controller.

Pure modules (canonical, crypto, store, verifier, responder, spool, monitor_parser, policy) have no Ryu
dependency and run under both venvs; ``app`` and ``ryu_codec`` need the Python 3.9 Ryu venv.
"""
