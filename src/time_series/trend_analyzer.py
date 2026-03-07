"""
Trend Analyzer
Detects trends, anomalies, and patterns in time series data.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import numpy as np
from enum import Enum

from .metrics_store import MetricSeries, TimeSeriesMetricsStore


class TrendDirection(Enum):
    """Trend direction classification"""
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    VOLATILE = "volatile"


@dataclass
class TrendResult:
    """Result of trend analysis"""
    direction: TrendDirection
    slope: float
    confidence: float
    start_value: float
    end_value: float
    change_pct: float
    volatility: float
    forecast_next: Optional[float] = None


@dataclass
class AnomalyResult:
    """Result of anomaly detection"""
    timestamp: datetime
    value: float
    expected_value: float
    deviation: float
    severity: str  # "low", "medium", "high"


class TrendAnalyzer:
    """
    Analyzes time series data for trends, anomalies, and patterns.
    """

    def __init__(self, metrics_store: TimeSeriesMetricsStore):
        self.metrics = metrics_store

    def analyze_trend(self,
                      metric_name: str,
                      entity_id: str = None,
                      window_size: int = 4) -> Optional[TrendResult]:
        """
        Analyze trend for a metric.

        Args:
            metric_name: Metric to analyze
            entity_id: Optional entity filter
            window_size: Number of points for moving average

        Returns:
            TrendResult or None
        """
        series = self.metrics.get_series(metric_name, entity_id)
        if not series or len(series.data_points) < 3:
            return None

        df = series.to_dataframe()
        values = df['value'].values

        # Calculate slope using linear regression
        x = np.arange(len(values))
        slope, intercept = np.polyfit(x, values, 1)

        # Calculate volatility (standard deviation)
        volatility = np.std(values)

        # Determine direction
        if abs(slope) < volatility * 0.1:
            direction = TrendDirection.STABLE
        elif volatility > abs(slope) * 2:
            direction = TrendDirection.VOLATILE
        elif slope > 0:
            direction = TrendDirection.INCREASING
        else:
            direction = TrendDirection.DECREASING

        # Calculate confidence based on R-squared
        y_pred = slope * x + intercept
        ss_res = np.sum((values - y_pred) ** 2)
        ss_tot = np.sum((values - np.mean(values)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        confidence = max(0, min(1, r_squared))

        # Calculate change
        start_value = values[0]
        end_value = values[-1]
        change_pct = ((end_value - start_value) / start_value * 100) if start_value != 0 else 0

        # Simple forecast (next point)
        forecast_next = slope * len(values) + intercept

        return TrendResult(
            direction=direction,
            slope=slope,
            confidence=confidence,
            start_value=start_value,
            end_value=end_value,
            change_pct=change_pct,
            volatility=volatility,
            forecast_next=forecast_next
        )

    def detect_anomalies(self,
                         metric_name: str,
                         entity_id: str = None,
                         threshold_std: float = 2.0) -> List[AnomalyResult]:
        """
        Detect anomalies in a metric series.

        Args:
            metric_name: Metric to analyze
            entity_id: Optional entity filter
            threshold_std: Standard deviations for anomaly threshold

        Returns:
            List of detected anomalies
        """
        series = self.metrics.get_series(metric_name, entity_id)
        if not series or len(series.data_points) < 5:
            return []

        df = series.to_dataframe()
        values = df['value'].values
        timestamps = df['timestamp'].values

        mean = np.mean(values)
        std = np.std(values)

        anomalies = []
        for i, (ts, val) in enumerate(zip(timestamps, values)):
            deviation = abs(val - mean) / std if std > 0 else 0

            if deviation > threshold_std:
                severity = "low"
                if deviation > threshold_std * 1.5:
                    severity = "medium"
                if deviation > threshold_std * 2:
                    severity = "high"

                anomalies.append(AnomalyResult(
                    timestamp=ts,
                    value=val,
                    expected_value=mean,
                    deviation=deviation,
                    severity=severity
                ))

        return anomalies

    def detect_change_points(self,
                             metric_name: str,
                             entity_id: str = None,
                             min_change_pct: float = 10.0) -> List[Dict]:
        """
        Detect significant change points in a metric.

        Args:
            metric_name: Metric to analyze
            entity_id: Optional entity filter
            min_change_pct: Minimum percentage change to flag

        Returns:
            List of change points
        """
        series = self.metrics.get_series(metric_name, entity_id)
        if not series or len(series.data_points) < 3:
            return []

        df = series.to_dataframe()
        values = df['value'].values
        timestamps = df['timestamp'].values

        change_points = []
        for i in range(1, len(values)):
            prev_val = values[i - 1]
            curr_val = values[i]

            if prev_val == 0:
                continue

            change_pct = ((curr_val - prev_val) / prev_val) * 100

            if abs(change_pct) >= min_change_pct:
                change_points.append({
                    "timestamp": timestamps[i],
                    "previous_value": prev_val,
                    "current_value": curr_val,
                    "change_pct": change_pct,
                    "direction": "increase" if change_pct > 0 else "decrease"
                })

        return change_points

    def correlate_metrics(self,
                          metric1_name: str,
                          metric2_name: str,
                          entity_id: str = None) -> Dict:
        """
        Calculate correlation between two metrics.

        Args:
            metric1_name: First metric
            metric2_name: Second metric
            entity_id: Optional entity filter

        Returns:
            Correlation analysis results
        """
        series1 = self.metrics.get_series(metric1_name, entity_id)
        series2 = self.metrics.get_series(metric2_name, entity_id)

        if not series1 or not series2:
            return {"error": "Metric series not found"}

        # Align by timestamp
        df1 = series1.to_dataframe().set_index('timestamp')
        df2 = series2.to_dataframe().set_index('timestamp')

        # Find common timestamps
        common_idx = df1.index.intersection(df2.index)

        if len(common_idx) < 3:
            return {"error": "Insufficient common data points"}

        values1 = df1.loc[common_idx, 'value'].values
        values2 = df2.loc[common_idx, 'value'].values

        # Calculate Pearson correlation
        correlation = np.corrcoef(values1, values2)[0, 1]

        # Interpret correlation
        if abs(correlation) < 0.3:
            strength = "weak"
        elif abs(correlation) < 0.7:
            strength = "moderate"
        else:
            strength = "strong"

        direction = "positive" if correlation > 0 else "negative"

        return {
            "metric1": metric1_name,
            "metric2": metric2_name,
            "correlation": correlation,
            "strength": strength,
            "direction": direction,
            "data_points": len(common_idx),
            "interpretation": f"{strength.title()} {direction} correlation ({correlation:.2f})"
        }

    def forecast_simple(self,
                        metric_name: str,
                        periods: int = 4,
                        entity_id: str = None) -> List[Dict]:
        """
        Simple linear forecast for a metric.

        Args:
            metric_name: Metric to forecast
            periods: Number of periods to forecast
            entity_id: Optional entity filter

        Returns:
            List of forecast points
        """
        series = self.metrics.get_series(metric_name, entity_id)
        if not series or len(series.data_points) < 3:
            return []

        df = series.to_dataframe()
        values = df['value'].values
        timestamps = df['timestamp'].values

        # Calculate average time delta
        if len(timestamps) > 1:
            deltas = [(timestamps[i] - timestamps[i-1]) for i in range(1, len(timestamps))]
            # Handle numpy datetime64
            avg_delta = np.mean([d.astype('timedelta64[D]').astype(int) for d in deltas])
            avg_delta = timedelta(days=int(avg_delta))
        else:
            avg_delta = timedelta(days=7)

        # Linear regression
        x = np.arange(len(values))
        slope, intercept = np.polyfit(x, values, 1)

        # Calculate confidence interval
        std = np.std(values)

        forecasts = []
        last_ts = timestamps[-1]

        for i in range(1, periods + 1):
            future_x = len(values) + i - 1
            forecast_value = slope * future_x + intercept
            forecast_ts = last_ts + avg_delta * i

            # Ensure forecast_ts is datetime
            if hasattr(forecast_ts, 'astype'):
                forecast_ts = forecast_ts.astype('datetime64[s]').astype(datetime)

            forecasts.append({
                "period": i,
                "timestamp": forecast_ts,
                "value": forecast_value,
                "lower_bound": forecast_value - std,
                "upper_bound": forecast_value + std,
                "confidence": max(0.5, 0.95 - i * 0.1)  # Decreasing confidence
            })

        return forecasts

    def get_metric_summary(self,
                           metric_name: str,
                           entity_id: str = None) -> Dict:
        """
        Get comprehensive summary for a metric.

        Args:
            metric_name: Metric to summarize
            entity_id: Optional entity filter

        Returns:
            Summary dict
        """
        series = self.metrics.get_series(metric_name, entity_id)
        if not series:
            return {}

        trend = self.analyze_trend(metric_name, entity_id)
        anomalies = self.detect_anomalies(metric_name, entity_id)
        change_points = self.detect_change_points(metric_name, entity_id)
        stats = series.get_statistics()

        return {
            "metric_name": metric_name,
            "entity_id": entity_id,
            "statistics": stats,
            "trend": {
                "direction": trend.direction.value if trend else None,
                "slope": trend.slope if trend else None,
                "confidence": trend.confidence if trend else None,
                "change_pct": trend.change_pct if trend else None
            },
            "anomalies": len(anomalies),
            "change_points": len(change_points),
            "data_points": len(series.data_points)
        }
