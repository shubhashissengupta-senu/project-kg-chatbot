"""
Project Forecaster
Generates future projections based on historical data and trends.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
import numpy as np
from enum import Enum


class ForecastConfidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ForecastPoint:
    """A single forecast data point"""
    date: datetime
    value: float
    lower_bound: float
    upper_bound: float
    confidence: ForecastConfidence


@dataclass
class MilestoneForecast:
    """Forecast for a project milestone"""
    milestone_name: str
    target_date: datetime
    predicted_date: datetime
    probability_on_time: float
    risk_factors: List[str]
    confidence: ForecastConfidence


@dataclass
class ProjectForecast:
    """Complete project forecast"""
    generated_at: datetime
    horizon_days: int
    velocity_forecast: List[ForecastPoint]
    quality_forecast: List[ForecastPoint]
    budget_forecast: List[ForecastPoint]
    milestone_forecasts: List[MilestoneForecast]
    risk_outlook: Dict[str, float]
    summary: str


class ProjectForecaster:
    """
    Generates project forecasts based on historical data.
    """

    # Project milestones
    MILESTONES = [
        ("Stream 1 UAT Start", datetime(2026, 3, 23)),
        ("Stream 1 Go-Live", datetime(2026, 4, 6)),
        ("Stream 2 UAT Start", datetime(2026, 4, 1)),
        ("Stream 2 Go-Live", datetime(2026, 4, 22)),
    ]

    def __init__(self, metrics_store, query_engine):
        self.metrics = metrics_store
        self.query_engine = query_engine

    def generate_forecast(self,
                          reference_date: datetime = None,
                          horizon_days: int = 30) -> ProjectForecast:
        """
        Generate comprehensive project forecast.

        Args:
            reference_date: Starting point for forecast
            horizon_days: Number of days to forecast

        Returns:
            ProjectForecast with all projections
        """
        reference_date = reference_date or datetime(2026, 3, 7)

        # Generate metric forecasts
        velocity_forecast = self._forecast_metric("velocity", reference_date, horizon_days)
        quality_forecast = self._forecast_metric("quality_score", reference_date, horizon_days)
        budget_forecast = self._forecast_metric("budget_variance", reference_date, horizon_days)

        # Generate milestone forecasts
        milestone_forecasts = self._forecast_milestones(reference_date)

        # Generate risk outlook
        risk_outlook = self._generate_risk_outlook(reference_date)

        # Generate summary
        summary = self._generate_summary(
            velocity_forecast, quality_forecast,
            milestone_forecasts, risk_outlook
        )

        return ProjectForecast(
            generated_at=datetime.now(),
            horizon_days=horizon_days,
            velocity_forecast=velocity_forecast,
            quality_forecast=quality_forecast,
            budget_forecast=budget_forecast,
            milestone_forecasts=milestone_forecasts,
            risk_outlook=risk_outlook,
            summary=summary
        )

    def _forecast_metric(self,
                         metric_name: str,
                         start_date: datetime,
                         horizon_days: int) -> List[ForecastPoint]:
        """Forecast a single metric"""
        forecast = []

        # Get historical data
        series = self.metrics.get_series(metric_name)
        if not series or len(series.data_points) < 3:
            # Generate synthetic forecast
            base_value = 85 if 'quality' in metric_name else 200 if 'velocity' in metric_name else 0
            for i in range(1, horizon_days // 7 + 1):
                date = start_date + timedelta(weeks=i)
                forecast.append(ForecastPoint(
                    date=date,
                    value=base_value * (1 + 0.02 * i),
                    lower_bound=base_value * (1 - 0.1),
                    upper_bound=base_value * (1 + 0.15),
                    confidence=ForecastConfidence.MEDIUM
                ))
            return forecast

        # Calculate trend from historical data
        values = [dp.value for dp in series.data_points]
        x = np.arange(len(values))
        slope, intercept = np.polyfit(x, values, 1)
        std = np.std(values)

        # Generate forecast points (weekly)
        for i in range(1, horizon_days // 7 + 1):
            date = start_date + timedelta(weeks=i)
            future_x = len(values) + i - 1
            predicted = slope * future_x + intercept

            # Confidence decreases with distance
            if i <= 2:
                conf = ForecastConfidence.HIGH
            elif i <= 4:
                conf = ForecastConfidence.MEDIUM
            else:
                conf = ForecastConfidence.LOW

            forecast.append(ForecastPoint(
                date=date,
                value=predicted,
                lower_bound=predicted - std * (1 + i * 0.2),
                upper_bound=predicted + std * (1 + i * 0.2),
                confidence=conf
            ))

        return forecast

    def _forecast_milestones(self, reference_date: datetime) -> List[MilestoneForecast]:
        """Forecast milestone achievement probability"""
        forecasts = []

        # Get current project state for context
        state = self.query_engine.get_project_state_at(reference_date)

        for name, target_date in self.MILESTONES:
            days_to_milestone = (target_date - reference_date).days

            # Base probability on stream status and time
            if "Stream 1" in name:
                base_prob = 0.95  # SD stream doing well
                risk_factors = []
            else:
                base_prob = 0.80  # EWM stream has challenges
                risk_factors = ["EWM test coverage at 84%", "Voice picking integration ongoing"]

            # Adjust based on time
            if days_to_milestone < 7:
                base_prob *= 0.95  # Very close, high certainty
                confidence = ForecastConfidence.HIGH
            elif days_to_milestone < 21:
                base_prob *= 0.9
                confidence = ForecastConfidence.MEDIUM
            else:
                base_prob *= 0.85
                confidence = ForecastConfidence.LOW

            # Calculate predicted date
            delay_days = 0 if base_prob > 0.9 else int((1 - base_prob) * 14)
            predicted_date = target_date + timedelta(days=delay_days)

            forecasts.append(MilestoneForecast(
                milestone_name=name,
                target_date=target_date,
                predicted_date=predicted_date,
                probability_on_time=min(0.99, base_prob),
                risk_factors=risk_factors,
                confidence=confidence
            ))

        return forecasts

    def _generate_risk_outlook(self, reference_date: datetime) -> Dict[str, float]:
        """Generate risk probability outlook"""
        return {
            "timeline_slip": 0.15,
            "budget_overrun": 0.10,
            "quality_issues": 0.20,
            "resource_departure": 0.25,  # Lakshmi leaving
            "scope_creep": 0.05,
            "integration_failure": 0.12,
        }

    def _generate_summary(self,
                          velocity: List[ForecastPoint],
                          quality: List[ForecastPoint],
                          milestones: List[MilestoneForecast],
                          risks: Dict[str, float]) -> str:
        """Generate narrative summary"""
        parts = []

        # Overall outlook
        sd_milestone = next((m for m in milestones if "Stream 1 Go-Live" in m.milestone_name), None)
        ewm_milestone = next((m for m in milestones if "Stream 2 Go-Live" in m.milestone_name), None)

        if sd_milestone and sd_milestone.probability_on_time > 0.9:
            parts.append("Stream 1 (SD) is on track for the April 6 go-live with high confidence.")
        else:
            parts.append("Stream 1 (SD) has some risk factors that need attention.")

        if ewm_milestone and ewm_milestone.probability_on_time > 0.8:
            parts.append("Stream 2 (EWM) recovery is progressing well, targeting April 22 go-live.")
        else:
            parts.append("Stream 2 (EWM) remains at risk and requires close monitoring.")

        # Risk highlights
        high_risks = [k for k, v in risks.items() if v > 0.2]
        if high_risks:
            parts.append(f"Key risks to watch: {', '.join(high_risks)}.")

        return " ".join(parts)

    def forecast_metric_value(self,
                              metric_name: str,
                              target_date: datetime) -> Tuple[float, float, float]:
        """
        Forecast a specific metric value at a target date.

        Returns:
            Tuple of (predicted, lower_bound, upper_bound)
        """
        series = self.metrics.get_series(metric_name)

        if not series or len(series.data_points) < 2:
            # Default values
            defaults = {
                "velocity": (210, 180, 240),
                "quality_score": (88, 82, 94),
                "test_coverage": (75, 70, 80),
                "engagement": (90, 85, 95),
            }
            return defaults.get(metric_name, (50, 40, 60))

        # Linear regression forecast
        values = [dp.value for dp in series.data_points]
        timestamps = [dp.timestamp for dp in series.data_points]

        # Convert to days from first timestamp
        first_ts = timestamps[0]
        x = [(ts - first_ts).days for ts in timestamps]
        target_x = (target_date - first_ts).days

        slope, intercept = np.polyfit(x, values, 1)
        std = np.std(values)

        predicted = slope * target_x + intercept
        lower = predicted - std * 1.5
        upper = predicted + std * 1.5

        return (predicted, lower, upper)
