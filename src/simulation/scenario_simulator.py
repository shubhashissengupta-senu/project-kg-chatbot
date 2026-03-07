"""
Scenario Simulator
Runs what-if simulations for project planning.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import random
import copy


@dataclass
class ScenarioParameter:
    """A parameter that can be varied in simulation"""
    name: str
    description: str
    current_value: Any
    min_value: Any = None
    max_value: Any = None
    options: List[Any] = field(default_factory=list)


@dataclass
class SimulationResult:
    """Result of a simulation run"""
    scenario_name: str
    parameters: Dict[str, Any]
    outcomes: Dict[str, Any]
    probability: float
    impact_assessment: str
    recommendations: List[str]


@dataclass
class SimulationSummary:
    """Summary of multiple simulation runs"""
    total_runs: int
    scenarios_tested: List[str]
    best_case: SimulationResult
    worst_case: SimulationResult
    most_likely: SimulationResult
    key_insights: List[str]


class ScenarioSimulator:
    """
    Runs what-if scenarios for project planning and risk assessment.
    """

    # Predefined scenario templates
    SCENARIO_TEMPLATES = {
        "resource_departure": {
            "name": "Team Member Departure",
            "description": "Simulate impact of a team member leaving",
            "parameters": {
                "departing_member": {
                    "options": ["Ryan", "Dhyanesh", "Riaz", "Nayan", "Jhanvi"],
                    "description": "Team member who might leave"
                },
                "notice_period_days": {
                    "min": 0, "max": 30, "default": 14,
                    "description": "Notice period in days"
                },
                "replacement_time_days": {
                    "min": 7, "max": 45, "default": 21,
                    "description": "Time to find and onboard replacement"
                }
            },
            "impact_model": "_model_resource_departure"
        },

        "scope_addition": {
            "name": "Scope Addition",
            "description": "Simulate impact of adding new requirements",
            "parameters": {
                "story_points": {
                    "min": 10, "max": 100, "default": 30,
                    "description": "Additional story points"
                },
                "stream": {
                    "options": ["SD", "EWM", "Both"],
                    "description": "Affected stream"
                },
                "cr_approved": {
                    "options": [True, False], "default": True,
                    "description": "Whether CR is approved (with budget)"
                }
            },
            "impact_model": "_model_scope_addition"
        },

        "quality_issue": {
            "name": "Quality Issue Discovery",
            "description": "Simulate discovery of significant quality issues",
            "parameters": {
                "severity": {
                    "options": ["Low", "Medium", "High", "Critical"],
                    "default": "Medium",
                    "description": "Issue severity"
                },
                "affected_module": {
                    "options": ["SD Core", "SD Pricing", "EWM Core", "EWM Voice", "Integration"],
                    "description": "Module with issues"
                },
                "discovery_timing": {
                    "options": ["Now", "During UAT", "Post Go-Live"],
                    "description": "When issue is discovered"
                }
            },
            "impact_model": "_model_quality_issue"
        },

        "timeline_change": {
            "name": "Timeline Change",
            "description": "Simulate impact of timeline adjustments",
            "parameters": {
                "days_change": {
                    "min": -14, "max": 30, "default": 0,
                    "description": "Days added (+) or removed (-)"
                },
                "affected_milestone": {
                    "options": ["Stream 1 UAT", "Stream 1 Go-Live", "Stream 2 UAT", "Stream 2 Go-Live"],
                    "description": "Which milestone changes"
                }
            },
            "impact_model": "_model_timeline_change"
        },

        "budget_pressure": {
            "name": "Budget Pressure",
            "description": "Simulate response to budget constraints",
            "parameters": {
                "budget_reduction_pct": {
                    "min": 5, "max": 25, "default": 10,
                    "description": "Percentage budget reduction"
                },
                "response_strategy": {
                    "options": ["Reduce scope", "Reduce quality", "Overtime", "Delay timeline"],
                    "description": "Response strategy"
                }
            },
            "impact_model": "_model_budget_pressure"
        }
    }

    # Team member capabilities for resource simulation
    TEAM_CAPABILITIES = {
        "Ryan": {"streams": ["SD", "Integration"], "velocity": 24, "critical": True},
        "Dhyanesh": {"streams": ["SD"], "velocity": 23, "critical": False},
        "Raj": {"streams": ["SD"], "velocity": 15, "critical": False},
        "Riaz": {"streams": ["EWM"], "velocity": 28, "critical": True},
        "Nayan": {"streams": ["EWM"], "velocity": 28, "critical": True},
        "Lakshmi": {"streams": ["UI"], "velocity": 14, "critical": False},
        "Jhanvi": {"streams": ["Testing"], "velocity": 17, "critical": False},
    }

    def __init__(self, query_engine=None, metrics_store=None):
        self.query_engine = query_engine
        self.metrics = metrics_store

    def get_available_scenarios(self) -> List[Dict]:
        """Get list of available scenario templates"""
        scenarios = []
        for key, template in self.SCENARIO_TEMPLATES.items():
            scenarios.append({
                "id": key,
                "name": template["name"],
                "description": template["description"],
                "parameters": list(template["parameters"].keys())
            })
        return scenarios

    def get_scenario_parameters(self, scenario_id: str) -> Dict:
        """Get parameter definitions for a scenario"""
        template = self.SCENARIO_TEMPLATES.get(scenario_id)
        if not template:
            return {}
        return template["parameters"]

    def run_simulation(self,
                       scenario_id: str,
                       parameters: Dict[str, Any],
                       num_runs: int = 1) -> SimulationResult:
        """
        Run a single simulation scenario.

        Args:
            scenario_id: ID of scenario template
            parameters: Parameter values
            num_runs: Number of Monte Carlo runs (for probabilistic)

        Returns:
            SimulationResult
        """
        template = self.SCENARIO_TEMPLATES.get(scenario_id)
        if not template:
            raise ValueError(f"Unknown scenario: {scenario_id}")

        # Get impact model method
        model_name = template["impact_model"]
        model_method = getattr(self, model_name, self._default_model)

        # Run the model
        outcomes = model_method(parameters)

        # Calculate probability and assessment
        probability = outcomes.get("probability", 0.5)
        impact = self._assess_impact(outcomes)
        recommendations = self._generate_recommendations(scenario_id, parameters, outcomes)

        return SimulationResult(
            scenario_name=template["name"],
            parameters=parameters,
            outcomes=outcomes,
            probability=probability,
            impact_assessment=impact,
            recommendations=recommendations
        )

    def run_comparison(self,
                       scenario_id: str,
                       parameter_variations: List[Dict]) -> SimulationSummary:
        """
        Run multiple variations of a scenario for comparison.

        Args:
            scenario_id: Scenario to test
            parameter_variations: List of parameter sets to compare

        Returns:
            SimulationSummary comparing all variations
        """
        results = []
        for params in parameter_variations:
            result = self.run_simulation(scenario_id, params)
            results.append(result)

        # Find best, worst, most likely
        results_sorted = sorted(results, key=lambda r: r.outcomes.get("timeline_impact_days", 0))

        best = results_sorted[0]
        worst = results_sorted[-1]
        most_likely = results_sorted[len(results_sorted) // 2]

        insights = self._generate_comparison_insights(results)

        return SimulationSummary(
            total_runs=len(results),
            scenarios_tested=[r.scenario_name for r in results],
            best_case=best,
            worst_case=worst,
            most_likely=most_likely,
            key_insights=insights
        )

    # Impact Models

    def _model_resource_departure(self, params: Dict) -> Dict:
        """Model impact of team member departure"""
        member = params.get("departing_member", "Dhyanesh")
        notice_days = params.get("notice_period_days", 14)
        replacement_days = params.get("replacement_time_days", 21)

        member_info = self.TEAM_CAPABILITIES.get(member, {})
        velocity_loss = member_info.get("velocity", 20)
        affected_streams = member_info.get("streams", [])
        is_critical = member_info.get("critical", False)

        # Calculate impacts
        gap_days = max(0, replacement_days - notice_days)
        velocity_impact = velocity_loss * (gap_days / 7)  # Lost story points

        # Timeline impact
        if is_critical:
            timeline_impact = gap_days * 1.5  # Critical roles have more impact
        else:
            timeline_impact = gap_days * 0.7

        # Cost impact (rough estimate)
        cost_impact = (replacement_days / 30) * 15000 + gap_days * 500

        return {
            "velocity_impact_points": velocity_impact,
            "timeline_impact_days": int(timeline_impact),
            "cost_impact_usd": cost_impact,
            "affected_streams": affected_streams,
            "probability": 0.3 if is_critical else 0.2,
            "risk_level": "High" if is_critical else "Medium",
            "mitigation_possible": notice_days >= 14
        }

    def _model_scope_addition(self, params: Dict) -> Dict:
        """Model impact of scope addition"""
        story_points = params.get("story_points", 30)
        stream = params.get("stream", "SD")
        cr_approved = params.get("cr_approved", True)

        # Calculate timeline impact (assuming 20 SP/week velocity)
        weeks_needed = story_points / 20
        timeline_impact = int(weeks_needed * 7)

        # Cost impact
        if cr_approved:
            # CR covers additional cost
            cost_impact = 0
            budget_impact = story_points * 800  # Revenue increase
        else:
            cost_impact = story_points * 800
            budget_impact = -cost_impact

        return {
            "timeline_impact_days": timeline_impact,
            "cost_impact_usd": cost_impact,
            "budget_impact_usd": budget_impact,
            "velocity_required": story_points,
            "probability": 0.6 if cr_approved else 0.3,
            "risk_level": "Low" if cr_approved else "High",
            "cr_recommended": not cr_approved and story_points > 20
        }

    def _model_quality_issue(self, params: Dict) -> Dict:
        """Model impact of quality issue discovery"""
        severity = params.get("severity", "Medium")
        module = params.get("affected_module", "SD Core")
        timing = params.get("discovery_timing", "Now")

        # Severity multipliers
        severity_factors = {
            "Low": {"days": 2, "cost": 5000, "probability": 0.4},
            "Medium": {"days": 5, "cost": 15000, "probability": 0.3},
            "High": {"days": 10, "cost": 35000, "probability": 0.2},
            "Critical": {"days": 21, "cost": 80000, "probability": 0.1}
        }

        # Timing multipliers
        timing_factors = {
            "Now": 1.0,
            "During UAT": 1.5,
            "Post Go-Live": 3.0
        }

        factors = severity_factors.get(severity, severity_factors["Medium"])
        timing_mult = timing_factors.get(timing, 1.0)

        timeline_impact = int(factors["days"] * timing_mult)
        cost_impact = factors["cost"] * timing_mult

        return {
            "timeline_impact_days": timeline_impact,
            "cost_impact_usd": cost_impact,
            "rework_effort_days": factors["days"],
            "probability": factors["probability"],
            "risk_level": severity,
            "affected_module": module,
            "recommended_action": "Immediate fix" if timing == "Now" else "Emergency patch"
        }

    def _model_timeline_change(self, params: Dict) -> Dict:
        """Model impact of timeline changes"""
        days_change = params.get("days_change", 0)
        milestone = params.get("affected_milestone", "Stream 2 Go-Live")

        # Positive days = more time = lower risk
        # Negative days = less time = higher risk

        if days_change > 0:
            # Extension
            quality_impact = days_change * 2  # More time for testing
            cost_impact = days_change * 3000  # Extended team cost
            risk_reduction = min(0.3, days_change * 0.02)
        else:
            # Compression
            quality_impact = days_change * 4  # Quality suffers more
            cost_impact = abs(days_change) * 5000  # Overtime costs
            risk_reduction = days_change * 0.03  # Negative = risk increase

        return {
            "timeline_impact_days": days_change,
            "quality_impact_score": quality_impact,
            "cost_impact_usd": abs(cost_impact),
            "risk_change_pct": risk_reduction * 100,
            "probability": 0.5,
            "affected_milestone": milestone,
            "recommended": days_change >= 0
        }

    def _model_budget_pressure(self, params: Dict) -> Dict:
        """Model impact of budget pressure response"""
        reduction_pct = params.get("budget_reduction_pct", 10)
        strategy = params.get("response_strategy", "Reduce scope")

        base_budget = 1850000
        reduction_amount = base_budget * reduction_pct / 100

        impacts = {
            "Reduce scope": {
                "timeline_days": -7,
                "quality_impact": -5,
                "risk_increase": 10
            },
            "Reduce quality": {
                "timeline_days": 0,
                "quality_impact": -reduction_pct,
                "risk_increase": 25
            },
            "Overtime": {
                "timeline_days": 0,
                "quality_impact": -5,
                "risk_increase": 15  # Burnout risk
            },
            "Delay timeline": {
                "timeline_days": reduction_pct * 2,
                "quality_impact": 0,
                "risk_increase": 5
            }
        }

        impact = impacts.get(strategy, impacts["Reduce scope"])

        return {
            "budget_reduction_usd": reduction_amount,
            "timeline_impact_days": impact["timeline_days"],
            "quality_impact_score": impact["quality_impact"],
            "risk_increase_pct": impact["risk_increase"],
            "probability": 0.3,
            "strategy_used": strategy,
            "sustainable": impact["risk_increase"] < 20
        }

    def _default_model(self, params: Dict) -> Dict:
        """Default model for unknown scenarios"""
        return {
            "timeline_impact_days": 7,
            "cost_impact_usd": 10000,
            "probability": 0.5,
            "risk_level": "Medium"
        }

    def _assess_impact(self, outcomes: Dict) -> str:
        """Assess overall impact from outcomes"""
        timeline = outcomes.get("timeline_impact_days", 0)
        cost = outcomes.get("cost_impact_usd", 0)
        risk = outcomes.get("risk_level", "Medium")

        if timeline > 14 or cost > 50000 or risk == "Critical":
            return "Severe impact - requires immediate executive attention"
        elif timeline > 7 or cost > 20000 or risk == "High":
            return "Significant impact - needs mitigation plan"
        elif timeline > 3 or cost > 5000:
            return "Moderate impact - monitor closely"
        else:
            return "Minor impact - manageable within current plan"

    def _generate_recommendations(self,
                                   scenario_id: str,
                                   params: Dict,
                                   outcomes: Dict) -> List[str]:
        """Generate recommendations based on simulation"""
        recommendations = []

        if scenario_id == "resource_departure":
            if outcomes.get("mitigation_possible"):
                recommendations.append("Document critical knowledge during notice period")
            recommendations.append("Identify backup resources immediately")
            if outcomes.get("is_critical"):
                recommendations.append("Consider retention incentives")

        elif scenario_id == "scope_addition":
            if outcomes.get("cr_recommended"):
                recommendations.append("Submit change request for additional budget")
            recommendations.append("Prioritize new requirements against existing backlog")

        elif scenario_id == "quality_issue":
            recommendations.append("Conduct root cause analysis")
            recommendations.append("Increase testing coverage in affected module")

        elif scenario_id == "timeline_change":
            if outcomes.get("recommended"):
                recommendations.append("Use additional time for thorough testing")
            else:
                recommendations.append("Identify scope items that can be deferred")

        elif scenario_id == "budget_pressure":
            if not outcomes.get("sustainable"):
                recommendations.append("Escalate to stakeholders - current approach not sustainable")
            recommendations.append("Review contingency allocation")

        return recommendations

    def _generate_comparison_insights(self, results: List[SimulationResult]) -> List[str]:
        """Generate insights from comparing multiple scenarios"""
        insights = []

        timeline_impacts = [r.outcomes.get("timeline_impact_days", 0) for r in results]
        cost_impacts = [r.outcomes.get("cost_impact_usd", 0) for r in results]

        avg_timeline = sum(timeline_impacts) / len(timeline_impacts) if timeline_impacts else 0
        avg_cost = sum(cost_impacts) / len(cost_impacts) if cost_impacts else 0

        insights.append(f"Average timeline impact: {avg_timeline:.0f} days")
        insights.append(f"Average cost impact: ${avg_cost:,.0f}")

        if max(timeline_impacts) - min(timeline_impacts) > 14:
            insights.append("High variance in outcomes - parameter selection is critical")

        return insights
