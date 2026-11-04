"""ClientFlow Budget & Healing Tests"""
import pytest
from clientflow.budget.adaptive import ClientFlowAdaptiveBudget
from clientflow.budget.healing import ClientFlowHealingEngine
from clientflow.budget.semantic import ClientFlowSemanticDiffer
from shared.token_budget.budget import Budget, Profile
from shared.token_budget.adaptive import AdaptiveBudget, SessionTokenOptimizer

class TestClientFlowBudget:
    """Test ClientFlow adaptive budget system."""
    
    def test_adaptive_budget_creation(self):
        budget = ClientFlowAdaptiveBudget()
        assert budget.base_budget.max_tokens == 1200
        assert budget.adaptive is not None
        assert budget.optimizer is not None
    
    def test_get_budget_for_endpoint(self):
        budget = ClientFlowAdaptiveBudget()
        result = budget.get_budget_for_endpoint("/api/invoices/", "GET")
        
        assert "max_tokens" in result
        assert "profile" in result
        assert result["max_tokens"] >= 500
        assert result["profile"] in ["minimal", "balanced", "full"]
    
    def test_record_request(self):
        budget = ClientFlowAdaptiveBudget()
        budget.record_request("/api/invoices/", "GET", 500, True)
        budget.record_request("/api/invoices/", "POST", 800, True)
        
        report = budget.get_budget_report()
        assert "adaptive_budgets" in report
        assert "optimizer_report" in report
    
    def test_budget_learning(self):
        budget = ClientFlowAdaptiveBudget()
        # Simulate multiple requests
        for i in range(15):
            budget.record_request("/api/invoices/", "GET", 600 + i * 10, True)
        
        report = budget.get_budget_report()
        # Should have learned a budget
        assert "clientflow:/api/invoices/:get" in budget.adaptive.site_budgets


class TestClientFlowSemanticDiff:
    """Test ClientFlow semantic diff for invoicing."""
    
    def test_invoicing_domain(self):
        differ = ClientFlowSemanticDiffer()
        assert differ.differ.domain == "invoicing"
        assert "FINANCIAL_ROLES" in differ.differ.roles
    
    def test_financial_impact_classification(self):
        differ = ClientFlowSemanticDiffer()
        # Test financial impact classification
        assert differ._assess_financial_impact(
            type("obj", (), {"type": "form_update"})()
        ) == "amount_or_field_changed"
        
        assert differ._assess_financial_impact(
            type("obj", (), {"type": "interaction"})()
        ) == "payment_or_action_recorded"


class TestClientFlowHealing:
    """Test ClientFlow healing engine."""
    
    def test_healing_engine_creation(self):
        engine = ClientFlowHealingEngine()
        assert engine.store is not None
        assert engine.cross_kb is not None
        assert engine.healer is not None
    
    def test_cross_project_registration(self):
        engine = ClientFlowHealingEngine()
        assert engine.cross_kb.project_types.get("clientflow") == "django"
