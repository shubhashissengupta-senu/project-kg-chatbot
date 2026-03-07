"""
Risk Predictor
Predicts project risks based on patterns and metrics.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import numpy as np

from .query_engine import TemporalQueryEngine
from ..time_series.metrics_store import TimeSeriesMetricsStore
from ..time_series.trend_analyzer import TrendAnalyzer


@dataclass
class RiskPrediction:
    """A predicted risk"""
    risk_id: str
    risk_type: str
    description: str
    probability: float  # 0-1
    confidence: float  # 0-1
    severity: str  # Low, Medium, High
    contributing_factors: List[str]
    recommended_actions: List[str]
    timeline_days: int
    affected_entities: List[str] = field(default_factory=list)


class RiskPredictor:
    """
    Predicts project risks based on patterns, metrics, and historical data.
    """

    # Risk patterns with indicators and weights
    RISK_PATTERNS = {
        "resource_departure": {
            "description": "Team member departure risk",
            "indicators": [
                ("engagement_score", "<", 70, 0.35),
                ("engagement_trend", "<", 0, 0.25),
                ("overtime_hours", ">", 15, 0.20),
                ("task_completion_rate", "<", 80, 0.20),
            ],
            "severity": "High",
            "actions": [
                "Schedule 1:1 meeting with at-risk team member",
                "Review and balance workload",
                "Identify backup resources",
                "Document critical knowledge"
            ]
        },
        "timeline_slip": {
            "description": "Project timeline delay risk",
            "indicators": [
                ("velocity_trend", "<", 0, 0.30),
                ("open_blockers", ">", 3, 0.25),
                ("defect_density", ">", 3.0, 0.25),
                ("test_pass_rate", "<", 90, 0.20),
            ],
            "severity": "High",
            "actions": [
                "Review scope and prioritize critical features",
                "Consider resource augmentation",
                "Increase standup frequency",
                "Identify and remove blockers"
            ]
        },
        "quality_degradation": {
            "description": "Code quality decline risk",
            "indicators": [
                ("test_coverage", "<", 60, 0.30),
                ("code_churn", ">", 20, 0.25),
                ("review_turnaround", ">", 24, 0.25),
                ("rework_rate", ">", 15, 0.20),
            ],
            "severity": "Medium",
            "actions": [
                "Enforce code review requirements",
                "Implement pair programming",
                "Increase test automation",
                "Address technical debt"
            ]
        },
        "scope_creep": {
            "description": "Uncontrolled scope expansion risk",
            "indicators": [
                ("new_requirements_rate", ">", 5, 0.40),
                ("baseline_deviation", ">", 10, 0.35),
                ("cr_discussions", ">", 3, 0.25),
            ],
            "severity": "High",
            "actions": [
                "Enforce change control process",
                "Schedule scope review meeting",
                "Update baseline documentation",
                "Communicate scope boundaries to stakeholders"
            ]
        },
        "integration_failure": {
            "description": "System integration issues risk",
            "indicators": [
                ("integration_test_pass", "<", 85, 0.35),
                ("api_errors", ">", 5, 0.30),
                ("cross_stream_defects", ">", 3, 0.35),
            ],
            "severity": "High",
            "actions": [
                "Increase integration testing frequency",
                "Review API contracts",
                "Schedule cross-team sync",
                "Implement contract testing"
            ]
        },
        "budget_overrun": {
            "description": "Budget exceed risk",
            "indicators": [
                ("cpi", "<", 0.95, 0.40),
                ("overtime_cost", ">", 10, 0.30),
                ("consultant_spend", ">", 15, 0.30),
            ],
            "severity": "High",
            "actions": [
                "Review cost drivers",
                "Optimize resource allocation",
                "Evaluate consultant necessity",
                "Implement cost controls"
            ]
        }
    }

    def __init__(self,
                 query_engine: TemporalQueryEngine,
                 metrics_store: TimeSeriesMetricsStore):
        self.query_engine = query_engine
        self.metrics = metrics_store
        self.trend_analyzer = TrendAnalyzer(metrics_store)

    def predict_risks(self,
                      timestamp: datetime = None,
                      horizon_days: int = 14) -> List[RiskPrediction]:
        """
        Predict risks for the upcoming period.

        Args:
            timestamp: Reference time (defaults to now)
            horizon_days: Prediction horizon in days

        Returns:
            List of risk predictions sorted by probability
        """
        timestamp = timestamp or datetime.now()
        predictions = []

        # Get current metrics
        current_metrics = self._gather_current_metrics(timestamp)

        # Evaluate each risk pattern
        for risk_type, pattern in self.RISK_PATTERNS.items():
            probability, factors = self._evaluate_pattern(pattern, current_metrics)

            if probability > 0.25:  # Threshold for reporting
                prediction = RiskPrediction(
                    risk_id=f"PRED_{risk_type.upper()}_{timestamp.strftime('%Y%m%d')}",
                    risk_type=risk_type,
                    description=pattern["description"],
                    probability=probability,
                    confidence=self._calculate_confidence(factors, current_metrics),
                    severity=pattern["severity"],
                    contributing_factors=factors,
                    recommended_actions=pattern["actions"],
                    timeline_days=horizon_days
                )
                predictions.append(prediction)

        # Add entity-specific predictions
        entity_predictions = self._predict_entity_risks(timestamp, horizon_days)
        predictions.extend(entity_predictions)

        # Sort by probability (highest first)
        predictions.sort(key=lambda p: p.probability, reverse=True)

        return predictions

    def _gather_current_metrics(self, timestamp: datetime) -> Dict[str, float]:
        """Gather current metric values"""
        metrics = {}

        # Key metrics to check
        metric_names = [
            "engagement_score", "velocity", "test_coverage", "defect_density",
            "code_churn", "rework_rate", "test_pass_rate", "cpi"
        ]

        for name in metric_names:
            value = self.metrics.get_value(name, timestamp)
            if value is not None:
                metrics[name] = value

            # Also get trends
            trend = self.trend_analyzer.analyze_trend(name)
            if trend:
                metrics[f"{name}_trend"] = trend.slope

        # Get counts from query engine
        project_state = self.query_engine.get_project_state_at(timestamp)
        if project_state and "error" not in project_state:
            metrics["open_blockers"] = len(project_state.get("open_risks", []))
            metrics["open_defects"] = len(project_state.get("open_defects", []))
            metrics["team_size"] = len(project_state.get("team", []))

        return metrics

    def _evaluate_pattern(self,
                          pattern: Dict,
                          current_metrics: Dict) -> Tuple[float, List[str]]:
        """
        Evaluate a risk pattern against current metrics.

        Returns:
            (probability, list of triggered factors)
        """
        total_weight = 0
        triggered_weight = 0
        factors = []

        for indicator_name, operator, threshold, weight in pattern.get("indicators", []):
            total_weight += weight

            value = current_metrics.get(indicator_name)
            if value is None:
                continue

            triggered = False
            if operator == "<" and value < threshold:
                triggered = True
            elif operator == ">" and value > threshold:
                triggered = True
            elif operator == "=" and value == threshold:
                triggered = True

            if triggered:
                triggered_weight += weight
                factors.append(f"{indicator_name}: {value:.1f} ({operator} {threshold})")

        probability = triggered_weight / total_weight if total_weight > 0 else 0
        return probability, factors

    def _calculate_confidence(self,
                              factors: List[str],
                              metrics: Dict) -> float:
        """Calculate confidence in prediction"""
        # Base confidence on data availability
        available_metrics = sum(1 for v in metrics.values() if v is not None)
        data_confidence = min(0.9, available_metrics / 10)

        # Factor count confidence
        factor_confidence = min(0.95, 0.5 + len(factors) * 0.15)

        return (data_confidence + factor_confidence) / 2

    def _predict_entity_risks(self,
                              timestamp: datetime,
                              horizon_days: int) -> List[RiskPrediction]:
        """Predict risks for specific entities"""
        predictions = []

        # Get project state
        state = self.query_engine.get_project_state_at(timestamp)
        if not state or "error" in state:
            return predictions

        # Check each team member for flight risk
        for person in state.get("team", []):
            person_id = person.get("id")
            if not person_id:
                continue

            # Check engagement trend
            engagement = self.metrics.get_value("engagement_score", timestamp, person_id)
            engagement_trend = self.trend_analyzer.analyze_trend("engagement_score", person_id)

            if engagement and engagement < 75:
                probability = 0.3
                factors = [f"Engagement: {engagement:.0f}"]

                if engagement_trend and engagement_trend.direction.value == "decreasing":
                    probability += 0.25
                    factors.append(f"Trend: declining ({engagement_trend.slope:.2f})")

                if engagement < 65:
                    probability += 0.15
                    factors.append("Engagement critically low")

                if probability > 0.4:
                    predictions.append(RiskPrediction(
                        risk_id=f"PRED_DEPARTURE_{person.get('name', 'UNKNOWN').upper()}",
                        risk_type="resource_departure",
                        description=f"Flight risk for {person.get('name', 'team member')}",
                        probability=min(0.95, probability),
                        confidence=0.7,
                        severity="High",
                        contributing_factors=factors,
                        recommended_actions=[
                            "Schedule 1:1 meeting",
                            "Review workload and concerns",
                            "Identify backup resources"
                        ],
                        timeline_days=horizon_days,
                        affected_entities=[person_id]
                    ))

        # Check streams for delay risk
        for stream in state.get("streams", []):
            stream_id = stream.get("id")
            completion = stream.get("completion_pct", 0)
            status = stream.get("status", "Unknown")

            if status == "Red" or (status == "Amber" and completion < 70):
                probability = 0.6 if status == "Red" else 0.4
                factors = [f"Status: {status}", f"Completion: {completion:.0f}%"]

                predictions.append(RiskPrediction(
                    risk_id=f"PRED_DELAY_{stream.get('name', 'STREAM').upper()}",
                    risk_type="timeline_slip",
                    description=f"Delay risk for {stream.get('name', 'stream')}",
                    probability=probability,
                    confidence=0.75,
                    severity="High",
                    contributing_factors=factors,
                    recommended_actions=[
                        "Review critical path",
                        "Assess resource needs",
                        "Update stakeholders"
                    ],
                    timeline_days=horizon_days,
                    affected_entities=[stream_id]
                ))

        return predictions

    def get_risk_summary(self, timestamp: datetime = None) -> Dict:
        """Get summary of all predicted risks"""
        predictions = self.predict_risks(timestamp)

        return {
            "total_risks": len(predictions),
            "high_probability": len([p for p in predictions if p.probability > 0.6]),
            "by_severity": {
                "High": len([p for p in predictions if p.severity == "High"]),
                "Medium": len([p for p in predictions if p.severity == "Medium"]),
                "Low": len([p for p in predictions if p.severity == "Low"])
            },
            "by_type": {
                risk_type: len([p for p in predictions if p.risk_type == risk_type])
                for risk_type in set(p.risk_type for p in predictions)
            },
            "top_risks": [
                {
                    "type": p.risk_type,
                    "description": p.description,
                    "probability": p.probability,
                    "severity": p.severity
                }
                for p in predictions[:5]
            ]
        }
