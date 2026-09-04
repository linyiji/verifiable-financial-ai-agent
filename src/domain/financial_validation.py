"""Versioned financial formula policy metadata shared by independent boundaries."""

REVENUE_GROWTH_FORMULA_ID = "revenue_growth_v1"
REVENUE_GROWTH_FORMULA_EXPRESSION = "(current_revenue - prior_revenue) / prior_revenue"
REVENUE_GROWTH_PRECONDITION = "prior_revenue > 0"
REVENUE_GROWTH_VALIDATION_REASON = "REVENUE_GROWTH_PRIOR_REVENUE_MUST_BE_POSITIVE"
