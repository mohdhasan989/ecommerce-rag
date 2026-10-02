"""Ingestion CLI entrypoint: ``python -m app.ai.rag``.

Kept separate from ``ingestion`` so running the module does not trigger
``ingestion``'s own ``__main__`` block twice via the package ``__init__``.
"""
import sys

from app.ai.rag.ingestion import main

if __name__ == "__main__":
    sys.exit(main())
