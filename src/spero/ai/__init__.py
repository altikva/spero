# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: The AI layer (Phase 3).

"""The AI layer (Phase 3).

Sequenced: predictive (disk-fill, flapping) -> LLM root-cause and incident
summaries -> natural-language ops queries -> policy-gated agentic remediation.
All provider-pluggable; Claude is the default backend, NullLLM the no-key fallback.
"""

from spero.ai.approver import AIApprover
from spero.ai.diagnose import diagnose_failure, incident_summary
from spero.ai.llm import AnthropicLLM, LLMClient, NullLLM
from spero.ai.predict import detect_flapping, forecast_threshold_crossing, parse_pct
from spero.ai.query import nl_query

__all__ = [
    "AIApprover",
    "AnthropicLLM",
    "LLMClient",
    "NullLLM",
    "detect_flapping",
    "diagnose_failure",
    "forecast_threshold_crossing",
    "incident_summary",
    "nl_query",
    "parse_pct",
]
