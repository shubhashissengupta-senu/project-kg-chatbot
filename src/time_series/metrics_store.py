"""
Time Series Metrics Store
Storage and retrieval of time-indexed metrics.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import numpy as np


@dataclass
class MetricDataPoint:
    """A single metric measurement"""
    timestamp: datetime
    value: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "value": self.value,
            **self.metadata
        }


@dataclass
class MetricSeries:
    """A time series of metric values"""
    name: str
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    unit: str = "value"
    data_points: List[MetricDataPoint] = field(default_factory=list)

    def add(self, timestamp: datetime, value: float, metadata: Dict = None):
        """Add a data point"""
        self.data_points.append(MetricDataPoint(
            timestamp=timestamp,
            value=value,
            metadata=metadata or {}
        ))
        # Keep sorted
        self.data_points.sort(key=lambda x: x.timestamp)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert to pandas DataFrame"""
        if not self.data_points:
            return pd.DataFrame(columns=['timestamp', 'value'])

        return pd.DataFrame([dp.to_dict() for dp in self.data_points])

    def get_value_at(self, timestamp: datetime, interpolate: bool = True) -> Optional[float]:
        """
        Get value at specific timestamp.

        Args:
            timestamp: Time to query
            interpolate: Whether to interpolate between points

        Returns:
            Value at timestamp or None
        """
        if not self.data_points:
            return None

        # Exact match
        for dp in self.data_points:
            if dp.timestamp == timestamp:
                return dp.value

        if not interpolate:
            return None

        # Find surrounding points
        before = None
        after = None

        for dp in self.data_points:
            if dp.timestamp < timestamp:
                before = dp
            elif dp.timestamp > timestamp and after is None:
                after = dp
                break

        # Interpolate
        if before and after:
            time_range = (after.timestamp - before.timestamp).total_seconds()
            if time_range > 0:
                ratio = (timestamp - before.timestamp).total_seconds() / time_range
                return before.value + ratio * (after.value - before.value)

        # Return closest value
        if before:
            return before.value
        if after:
            return after.value

        return None

    def get_values_between(self,
                           start: datetime,
                           end: datetime) -> List[MetricDataPoint]:
        """Get all values in a time range"""
        return [
            dp for dp in self.data_points
            if start <= dp.timestamp <= end
        ]

    def get_statistics(self,
                       start: datetime = None,
                       end: datetime = None) -> Dict:
        """Get statistical summary"""
        if start and end:
            points = self.get_values_between(start, end)
        else:
            points = self.data_points

        if not points:
            return {}

        values = [dp.value for dp in points]

        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": np.mean(values),
            "std": np.std(values),
            "median": np.median(values),
            "first": values[0],
            "last": values[-1],
            "change": values[-1] - values[0],
            "change_pct": ((values[-1] - values[0]) / values[0] * 100) if values[0] != 0 else 0
        }


class TimeSeriesMetricsStore:
    """
    Central store for all time series metrics.
    Supports multiple metrics per entity with temporal queries.
    """

    def __init__(self):
        self.series: Dict[str, MetricSeries] = {}
        self.entity_metrics: Dict[str, List[str]] = {}  # entity_id -> [series_keys]

    def _make_key(self, metric_name: str, entity_id: str = None) -> str:
        """Generate storage key"""
        if entity_id:
            return f"{entity_id}:{metric_name}"
        return metric_name

    def add_metric(self,
                   metric_name: str,
                   timestamp: datetime,
                   value: float,
                   entity_id: str = None,
                   entity_type: str = None,
                   unit: str = "value",
                   metadata: Dict = None):
        """
        Add a metric data point.

        Args:
            metric_name: Name of the metric
            timestamp: When the measurement was taken
            value: Metric value
            entity_id: Optional entity this metric belongs to
            entity_type: Type of entity
            unit: Unit of measurement
            metadata: Additional metadata
        """
        key = self._make_key(metric_name, entity_id)

        if key not in self.series:
            self.series[key] = MetricSeries(
                name=metric_name,
                entity_id=entity_id,
                entity_type=entity_type,
                unit=unit
            )

            # Track entity metrics
            if entity_id:
                if entity_id not in self.entity_metrics:
                    self.entity_metrics[entity_id] = []
                self.entity_metrics[entity_id].append(key)

        self.series[key].add(timestamp, value, metadata)

    def get_series(self,
                   metric_name: str,
                   entity_id: str = None) -> Optional[MetricSeries]:
        """Get a metric series"""
        key = self._make_key(metric_name, entity_id)
        return self.series.get(key)

    def get_value(self,
                  metric_name: str,
                  timestamp: datetime,
                  entity_id: str = None) -> Optional[float]:
        """Get metric value at specific time"""
        series = self.get_series(metric_name, entity_id)
        if series:
            return series.get_value_at(timestamp)
        return None

    def get_entity_metrics(self, entity_id: str) -> Dict[str, MetricSeries]:
        """Get all metrics for an entity"""
        result = {}
        for key in self.entity_metrics.get(entity_id, []):
            if key in self.series:
                series = self.series[key]
                result[series.name] = series
        return result

    def get_entity_metrics_at(self,
                              entity_id: str,
                              timestamp: datetime) -> Dict[str, float]:
        """Get all metrics for an entity at a specific time"""
        result = {}
        for key in self.entity_metrics.get(entity_id, []):
            series = self.series.get(key)
            if series:
                value = series.get_value_at(timestamp)
                if value is not None:
                    result[series.name] = value
        return result

    def compare_periods(self,
                        metric_name: str,
                        period1: Tuple[datetime, datetime],
                        period2: Tuple[datetime, datetime],
                        entity_id: str = None) -> Dict:
        """
        Compare metric across two time periods.

        Args:
            metric_name: Metric to compare
            period1: First period (start, end)
            period2: Second period (start, end)
            entity_id: Optional entity filter

        Returns:
            Comparison results
        """
        series = self.get_series(metric_name, entity_id)
        if not series:
            return {}

        stats1 = series.get_statistics(period1[0], period1[1])
        stats2 = series.get_statistics(period2[0], period2[1])

        return {
            "metric": metric_name,
            "period1": {
                "start": period1[0],
                "end": period1[1],
                **stats1
            },
            "period2": {
                "start": period2[0],
                "end": period2[1],
                **stats2
            },
            "comparison": {
                "mean_change": stats2.get("mean", 0) - stats1.get("mean", 0),
                "mean_change_pct": (
                    (stats2.get("mean", 0) - stats1.get("mean", 0)) / stats1.get("mean", 1) * 100
                    if stats1.get("mean", 0) != 0 else 0
                )
            }
        }

    def get_all_metrics(self) -> List[str]:
        """Get list of all metric names"""
        return list(set(s.name for s in self.series.values()))

    def get_all_entities(self) -> List[str]:
        """Get list of all entities with metrics"""
        return list(self.entity_metrics.keys())

    def to_dataframe(self,
                     metric_name: str = None,
                     entity_id: str = None) -> pd.DataFrame:
        """
        Convert metrics to DataFrame.

        Args:
            metric_name: Filter by metric name
            entity_id: Filter by entity

        Returns:
            DataFrame with all matching metrics
        """
        dfs = []

        for key, series in self.series.items():
            if metric_name and series.name != metric_name:
                continue
            if entity_id and series.entity_id != entity_id:
                continue

            df = series.to_dataframe()
            df['metric_name'] = series.name
            df['entity_id'] = series.entity_id
            dfs.append(df)

        if dfs:
            return pd.concat(dfs, ignore_index=True)
        return pd.DataFrame()

    def summary(self) -> Dict:
        """Get store summary"""
        return {
            "total_series": len(self.series),
            "total_entities": len(self.entity_metrics),
            "metrics": self.get_all_metrics(),
            "total_data_points": sum(len(s.data_points) for s in self.series.values())
        }
