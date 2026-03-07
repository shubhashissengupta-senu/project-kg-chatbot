"""
Temporal Types for Knowledge Graph
Defines time-aware entity and property classes.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Generic, TypeVar
from enum import Enum

T = TypeVar('T')


class TemporalGranularity(Enum):
    """Granularity levels for temporal data"""
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    SPRINT = "sprint"
    MONTH = "month"
    QUARTER = "quarter"


@dataclass
class TimePoint:
    """Represents a specific point in time with context"""
    timestamp: datetime
    granularity: TemporalGranularity = TemporalGranularity.DAY
    sprint_number: Optional[int] = None
    week_number: Optional[int] = None
    label: Optional[str] = None

    @property
    def week_key(self) -> str:
        """Get week key for indexing"""
        if self.week_number:
            return f"W{self.week_number}"
        return self.timestamp.strftime("%Y-W%V")

    @property
    def month_key(self) -> str:
        """Get month key for indexing"""
        return self.timestamp.strftime("%Y-%m")

    @property
    def sprint_key(self) -> Optional[str]:
        """Get sprint key for indexing"""
        if self.sprint_number:
            return f"S{self.sprint_number}"
        return None

    def __lt__(self, other: 'TimePoint') -> bool:
        return self.timestamp < other.timestamp

    def __le__(self, other: 'TimePoint') -> bool:
        return self.timestamp <= other.timestamp

    @classmethod
    def from_datetime(cls, dt: datetime, project_start: datetime = None) -> 'TimePoint':
        """Create TimePoint from datetime, calculating week/sprint numbers"""
        project_start = project_start or datetime(2025, 12, 1)

        # Calculate week number from project start
        days_diff = (dt - project_start).days
        week_number = (days_diff // 7) + 1 if days_diff >= 0 else None

        # Calculate sprint number (2-week sprints)
        sprint_number = ((days_diff // 14) + 1) if days_diff >= 0 else None

        return cls(
            timestamp=dt,
            week_number=week_number,
            sprint_number=sprint_number
        )


@dataclass
class TimeInterval:
    """Represents a time range with start and end points"""
    start: TimePoint
    end: TimePoint
    label: Optional[str] = None

    def contains(self, point: TimePoint) -> bool:
        """Check if interval contains a time point"""
        return self.start.timestamp <= point.timestamp <= self.end.timestamp

    def contains_datetime(self, dt: datetime) -> bool:
        """Check if interval contains a datetime"""
        return self.start.timestamp <= dt <= self.end.timestamp

    def overlaps(self, other: 'TimeInterval') -> bool:
        """Check if this interval overlaps with another"""
        return (self.start.timestamp <= other.end.timestamp and
                self.end.timestamp >= other.start.timestamp)

    @property
    def duration_days(self) -> int:
        """Get duration in days"""
        return (self.end.timestamp - self.start.timestamp).days

    @classmethod
    def from_month(cls, year: int, month: int) -> 'TimeInterval':
        """Create interval for a specific month"""
        from calendar import monthrange
        start_dt = datetime(year, month, 1)
        _, last_day = monthrange(year, month)
        end_dt = datetime(year, month, last_day, 23, 59, 59)

        return cls(
            start=TimePoint(start_dt),
            end=TimePoint(end_dt),
            label=start_dt.strftime("%B %Y")
        )

    @classmethod
    def from_week(cls, project_start: datetime, week_number: int) -> 'TimeInterval':
        """Create interval for a specific project week"""
        start_dt = project_start + timedelta(weeks=week_number - 1)
        end_dt = start_dt + timedelta(days=6, hours=23, minutes=59, seconds=59)

        return cls(
            start=TimePoint(start_dt, week_number=week_number),
            end=TimePoint(end_dt, week_number=week_number),
            label=f"Week {week_number}"
        )


@dataclass
class TemporalProperty(Generic[T]):
    """
    A property value with temporal validity.
    Tracks when a property value was valid.
    """
    value: T
    valid_from: datetime
    valid_to: Optional[datetime] = None  # None means currently valid
    source: Optional[str] = None  # Source document/meeting

    def is_valid_at(self, timestamp: datetime) -> bool:
        """Check if this property value is valid at given time"""
        if self.valid_to is None:
            return self.valid_from <= timestamp
        return self.valid_from <= timestamp <= self.valid_to

    def is_current(self) -> bool:
        """Check if this is the current value"""
        return self.valid_to is None

    def close(self, end_time: datetime):
        """Close this property value (mark as no longer valid)"""
        self.valid_to = end_time


@dataclass
class TemporalEntity:
    """
    An entity with time-varying properties.
    Maintains history of property changes.
    """
    entity_id: str
    entity_type: str
    static_properties: Dict[str, Any] = field(default_factory=dict)
    temporal_properties: Dict[str, List[TemporalProperty]] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    def get_property(self, prop_name: str, timestamp: datetime = None) -> Any:
        """
        Get property value, optionally at a specific time.

        Args:
            prop_name: Property name
            timestamp: Time to query (None for current)

        Returns:
            Property value or None
        """
        # Check static properties first
        if prop_name in self.static_properties:
            return self.static_properties[prop_name]

        # Check temporal properties
        if prop_name not in self.temporal_properties:
            return None

        if timestamp is None:
            # Return current value
            for tp in reversed(self.temporal_properties[prop_name]):
                if tp.is_current():
                    return tp.value
            return None

        # Return value at specific time
        for tp in self.temporal_properties[prop_name]:
            if tp.is_valid_at(timestamp):
                return tp.value

        return None

    def set_property(self, prop_name: str, value: Any, timestamp: datetime, source: str = None):
        """
        Set a property value at a specific time.

        Args:
            prop_name: Property name
            value: New value
            timestamp: When this value becomes valid
            source: Source of the change
        """
        if prop_name not in self.temporal_properties:
            self.temporal_properties[prop_name] = []

        # Close previous value
        for tp in self.temporal_properties[prop_name]:
            if tp.is_current():
                tp.close(timestamp)

        # Add new value
        self.temporal_properties[prop_name].append(
            TemporalProperty(value=value, valid_from=timestamp, source=source)
        )

    def get_property_history(self, prop_name: str) -> List[TemporalProperty]:
        """Get full history of a property"""
        return self.temporal_properties.get(prop_name, [])

    def get_state_at(self, timestamp: datetime) -> Dict[str, Any]:
        """
        Get complete entity state at a specific time.

        Returns:
            Dict with all property values at that time
        """
        state = dict(self.static_properties)

        for prop_name, history in self.temporal_properties.items():
            for tp in history:
                if tp.is_valid_at(timestamp):
                    state[prop_name] = tp.value
                    break

        return state

    def get_changes_between(self, start: datetime, end: datetime) -> List[Dict]:
        """
        Get all property changes between two times.

        Returns:
            List of change records
        """
        changes = []

        for prop_name, history in self.temporal_properties.items():
            for tp in history:
                if start <= tp.valid_from <= end:
                    changes.append({
                        "property": prop_name,
                        "value": tp.value,
                        "timestamp": tp.valid_from,
                        "source": tp.source
                    })

        return sorted(changes, key=lambda c: c["timestamp"])

    def is_active_at(self, timestamp: datetime) -> bool:
        """Check if entity exists at given time"""
        if self.created_at and timestamp < self.created_at:
            return False
        if self.deleted_at and timestamp > self.deleted_at:
            return False
        return True

    def to_dict(self, timestamp: datetime = None) -> Dict[str, Any]:
        """Convert to dict representation"""
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "properties": self.get_state_at(timestamp) if timestamp else {
                **self.static_properties,
                **{k: v[-1].value if v else None for k, v in self.temporal_properties.items()}
            },
            "created_at": self.created_at,
            "deleted_at": self.deleted_at
        }
