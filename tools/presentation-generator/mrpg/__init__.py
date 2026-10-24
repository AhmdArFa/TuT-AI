"""Multi-Resource Presentation Generator (MRPG).

Builds a polished PowerPoint deck from many resources at once: local files
(PDF, DOCX, PPTX, TXT, MD) and web pages. A full RAG pipeline chunks and
embeds the sources into a saved vector index (phase 1, offline), then
retrieves topic matched context and generates the deck online or offline
(phase 2), with an always-available extractive fallback that needs no
model at all.

Part of the TuT AI sovereign platform feature set (DEPI PPTX project).
"""

__version__ = "1.1.0"
__all__ = ["__version__"]
