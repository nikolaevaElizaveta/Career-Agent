"""Job board adapters."""

from career_agent.integrations.job_sources.adzuna import AdzunaJobSource
from career_agent.integrations.job_sources.remotive import RemotiveJobSource

__all__ = ["AdzunaJobSource", "RemotiveJobSource"]