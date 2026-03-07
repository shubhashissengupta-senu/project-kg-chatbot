"""
Knowledge Graph Schema
Ontology and type definitions.
"""

from .temporal_types import (
    TimePoint,
    TimeInterval,
    TemporalProperty,
    TemporalEntity,
    TemporalGranularity
)

__all__ = [
    "TimePoint",
    "TimeInterval",
    "TemporalProperty",
    "TemporalEntity",
    "TemporalGranularity"
]
