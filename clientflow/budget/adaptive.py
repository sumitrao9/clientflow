"""ClientFlow Adaptive Budget - Invoice/API token optimization"""
from dataclasses import dataclass
from typing import Dict, Optional
from shared.token_budget.adaptive import AdaptiveBudget, SessionTokenOptimizer
from shared.token_budget.budget import Budget, Profile

@dataclass
class ClientFlowAdaptiveBudget:
    """ClientFlow-specific adaptive budget for invoicing API."""
    
    base_budget: Budget = Budget(max_tokens=1200, profile="balanced")
    adaptive: 'AdaptiveBudget' = None
    optimizer: 'SessionTokenOptimizer' = None
    
    def __post_init__(self):
        from shared.token_budget.adaptive import AdaptiveBudget, SessionTokenOptimizer
        self.adaptive = AdaptiveBudget(self.base_budget.max_tokens, self.base_budget.profile)
        self.optimizer = SessionTokenOptimizer()
    
    def get_budget_for_endpoint(self, endpoint: str, method: str) -> dict:
        """Get adaptive budget for specific API endpoint."""
        context = f"clientflow:{endpoint}"
        action = method.lower()
        
        # Check adaptive budget
        budget_tokens = self.adaptive.get_site_budget(f"clientflow:{endpoint}", action)
        
        # Get recommended profile
        profile = self.optimizer.recommend_profile(f"clientflow:{endpoint}", action)
        
        return {
            "max_tokens": budget_tokens,
            "profile": profile,
            "hard_fail": False,
        }
    
    def record_request(self, endpoint: str, method: str, tokens_used: int, success: bool):
        """Record API request for learning."""
        self.adaptive.record_usage(f"clientflow:{endpoint}", method.lower(), 
                                   tokens_used, "balanced")
        self.optimizer.record_action(f"clientflow:{endpoint}", method.lower(),
                                     "balanced", tokens_used, success)
    
    def get_budget_report(self) -> dict:
        return {
            "adaptive_budgets": self.adaptive.site_budgets,
            "optimizer_report": self.optimizer.get_session_report(),
        }
