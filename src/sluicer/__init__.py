"""Deterministic extraction of the data a web page already declares."""

from sluicer.api import Extraction, extract
from sluicer.declared.merge import Field, Record
from sluicer.markdown import MarkdownExtraMissing, to_markdown
from sluicer.structure import induce

__all__ = [
    "Extraction",
    "Field",
    "MarkdownExtraMissing",
    "Record",
    "__version__",
    "extract",
    "induce",
    "to_markdown",
]
__version__ = "0.0.1"
