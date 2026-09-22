"""Deterministic extraction of the data a web page already declares."""

from sluicer.api import Extraction, extract
from sluicer.declared.merge import Field, Record

__all__ = ["Extraction", "Field", "Record", "extract", "__version__"]
__version__ = "0.0.1"
