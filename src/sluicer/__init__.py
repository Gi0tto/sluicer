"""Deterministic extraction of the data a web page already declares."""

from sluicer.api import Extraction, aextract, extract
from sluicer.declared.merge import Field, Record
from sluicer.declared.microformats import MicroformatsExtraMissing
from sluicer.markdown import MarkdownExtraMissing, to_markdown
from sluicer.structure import induce
from sluicer.summary import SummaryField
from sluicer.visible import Guess, read_visible

__all__ = [
    "Extraction",
    "Field",
    "Guess",
    "MarkdownExtraMissing",
    "MicroformatsExtraMissing",
    "Record",
    "SummaryField",
    "__version__",
    "aextract",
    "extract",
    "induce",
    "read_visible",
    "to_markdown",
]
__version__ = "0.7.1"
