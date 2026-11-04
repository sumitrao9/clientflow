"""ClientFlow Semantic Diff - Invoice/Client financial intent"""
from dataclasses import dataclass, field
from typing import List, Optional
from shared.semantic_diff.semantic import SemanticDiffer, SemanticChange

@dataclass
class ClientFlowSemanticChange:
    """Financial-aware semantic change for invoicing."""
    type: str  # navigation, invoice_update, payment_recorded, client_update, line_item_change, status_change
    significance: float
    elements_affected: List[str]
    description: str
    agent_action_hint: Optional[str] = None
    financial_impact: Optional[str] = None  # "amount_changed", "balance_updated", "status_changed"

class ClientFlowSemanticDiffer:
    """Semantic diff for invoicing domain - understands financial intent."""
    
    def __init__(self):
        from shared.semantic_diff.semantic import SemanticDiffer
        self.differ = SemanticDiffer()
        self.differ.set_domain("invoicing")
    
    def compute_financial_diff(self, previous, current) -> list:
        """Compute semantically meaningful financial changes."""
        return self.differ.compute_semantic_diff(previous, current)
    
    def classify_financial_change(self, change) -> dict:
        """Classify change with financial context."""
        return {
            "type": change.type,
            "significance": change.significance,
            "financial_impact": self._assess_financial_impact(change),
            "action_hint": change.agent_action_hint,
        }
    
    def _assess_financial_impact(self, change) -> str:
        if change.type == "form_update":
            return "amount_or_field_changed"
        elif change.type == "interaction":
            return "payment_or_action_recorded"
        elif change.type == "navigation":
            return "page_transition"
        return "content_updated"
