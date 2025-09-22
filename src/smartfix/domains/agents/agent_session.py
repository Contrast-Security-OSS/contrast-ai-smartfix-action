# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2025 Contrast Security, Inc.
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# NOTICE: This Software and the patented inventions embodied within may only be
# used as part of Contrast Security’s commercial offerings. Even though it is
# made available through public repositories, use of this Software is subject to
# the applicable End User Licensing Agreement found at
# https://www.contrastsecurity.com/enduser-terms-0317a or as otherwise agreed
# between Contrast Security and the End User. The Software may not be reverse
# engineered, modified, repackaged, sold, redistributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import List, Dict, Any, Optional


class AgentSessionStatus(Enum):
    """The final status of an agent session."""
    SUCCESS = auto()
    BUILD_FAILURE = auto()
    MAX_ATTEMPTS_REACHED = auto()
    ERROR = auto()
    IN_PROGRESS = auto()


@dataclass
class AgentEvent:
    """Represents a single interaction (prompt/response) with the LLM."""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    prompt: Optional[str] = None
    response: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSession:
    """
    Tracks the state and history of a single, complete remediation attempt.
    This acts as a "flight recorder" for the agent's work.
    """
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    status: AgentSessionStatus = AgentSessionStatus.IN_PROGRESS

    # --- Counters and Limits ---
    qa_attempts: int = 0
    max_qa_attempts: int = 6  # Default, should be overridden by config.MAX_QA_ATTEMPTS
    agent_events_count: int = 0
    max_agent_events: int = 120  # Default, should be overridden by config.MAX_EVENTS_PER_AGENT

    # --- History and Artifacts ---
    events: List[AgentEvent] = field(default_factory=list)
    build_results: List[str] = field(default_factory=list)
    final_pr_body: Optional[str] = None

    # --- Cost and Performance ---
    cost_metrics: Dict[str, Any] = field(default_factory=dict)
    # Note: cost_metrics should be populated by integrating with TokenCostAccumulator
    # from smartfix.extensions.smartfix_litellm for token usage and cost tracking

    @classmethod
    def from_config(cls, config_obj) -> 'AgentSession':
        """
        Create an AgentSession with configuration-driven limits.

        Args:
            config_obj: Configuration object with MAX_QA_ATTEMPTS and MAX_EVENTS_PER_AGENT

        Returns:
            AgentSession configured with values from config
        """
        return cls(
            max_qa_attempts=config_obj.MAX_QA_ATTEMPTS,
            max_agent_events=config_obj.MAX_EVENTS_PER_AGENT
        )

    def add_event(self, prompt: str, response: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Adds a new prompt/response event to the session."""
        event = AgentEvent(prompt=prompt, response=response, metadata=metadata or {})
        self.events.append(event)
        self.agent_events_count += 1

    def add_build_result(self, output: str) -> None:
        """Adds a failed build output to the session."""
        self.build_results.append(output)
        self.qa_attempts += 1

    def update_cost_metrics(self, agent_stats_dict: Dict[str, Any]) -> None:
        """
        Updates cost_metrics from agent statistics dictionary.

        Args:
            agent_stats_dict: Statistics dictionary from agent (e.g., from gather_accumulated_stats_dict())
        """
        try:
            # Extract telemetry values directly from the dictionary (following agent_handler.py pattern)
            total_tokens = agent_stats_dict.get("token_usage", {}).get("total_tokens", 0)
            raw_total_cost = agent_stats_dict.get("cost_analysis", {}).get("total_cost", 0.0)

            # Remove "$" prefix if present and convert to float (following agent_handler.py pattern)
            if isinstance(raw_total_cost, str) and raw_total_cost.startswith("$"):
                total_cost = float(raw_total_cost[1:])
            elif isinstance(raw_total_cost, str):
                total_cost = float(raw_total_cost)
            else:
                total_cost = raw_total_cost

            # Update cost_metrics with extracted values
            self.cost_metrics.update({
                "total_tokens": total_tokens,
                "total_cost": total_cost,
                "token_usage": agent_stats_dict.get("token_usage", {}),
                "cost_analysis": agent_stats_dict.get("cost_analysis", {}),
                "cache_efficiency": agent_stats_dict.get("cache_efficiency", {})
            })

        except (ValueError, KeyError, AttributeError) as e:
            # Fallback values if stats extraction fails
            self.cost_metrics.update({
                "total_tokens": 0,
                "total_cost": 0.0,
                "extraction_error": str(e)
            })

    def complete_session(self, status: AgentSessionStatus, pr_body: Optional[str] = None) -> None:
        """Marks the session as complete."""
        self.status = status
        self.final_pr_body = pr_body
        self.end_time = datetime.utcnow()

    @property
    def is_at_event_limit(self) -> bool:
        """Checks if the session has reached the maximum number of agent events."""
        return self.agent_events_count >= self.max_agent_events

    @property
    def is_at_qa_limit(self) -> bool:
        """Checks if the session has reached the maximum number of QA attempts."""
        return self.qa_attempts >= self.max_qa_attempts

    @property
    def duration(self) -> Optional[float]:
        """Returns the total duration of the session in seconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    @property
    def success(self) -> bool:
        """Returns True if the session completed successfully."""
        return self.status == AgentSessionStatus.SUCCESS

    @property
    def pr_body(self) -> Optional[str]:
        """Returns the final PR body content."""
        return self.final_pr_body

    @property
    def pr_title(self) -> Optional[str]:
        """Returns the PR title (can be extended later if needed)."""
        return None  # Can be implemented when PR title tracking is needed
