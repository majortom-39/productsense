"""Maya, built on the Deep Agents harness.

Clean architecture per memory/clean_architecture.md. Maya is a coordinator that
plans her own path (write_todos), reads the product-arc skill, obeys always-on
memory, delegates to stateless specialists, and pauses for the founder via
interrupts. This package is self-contained — it does not depend on the legacy
orchestration modules.
"""
