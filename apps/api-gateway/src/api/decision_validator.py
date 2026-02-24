"""
Decision Validator API Endpoints
决策验证器API端点

Phase 3: 稳定性加固期 (Stability Reinforcement Period)
Provides REST API for dual validation of AI decisions
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from src.services.decision_validator import DecisionValidator, ValidationResult
from src.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter(prefix="/api/v1/validator", tags=["decision_validator"])


# Request/Response Models
class DecisionTypeEnum(str, Enum):
    """Decision type enum"""
    INVENTORY_PURCHASE = "inventory_purchase"
    PRICE_ADJUSTMENT = "price_adjustment"
    STAFF_SCHEDULE = "staff_schedule"
    MENU_OPTIMIZATION = "menu_optimization"
    PROMOTION_PLAN = "promotion_plan"
    SUPPLIER_SELECTION = "supplier_selection"
    COST_CONTROL = "cost_control"
    EXPANSION_PLAN = "expansion_plan"


class ValidateDecisionRequest(BaseModel):
    """Validate decision request"""
    store_id: str
    decision_type: DecisionTypeEnum
    ai_suggestion: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None


class ValidationResultEnum(str, Enum):
    """Validation result enum"""
    APPROVED = "approved"
    REJECTED = "rejected"
    WARNING = "warning"


# API Endpoints
@router.post("/validate")
async def validate_decision(
    request: ValidateDecisionRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Validate AI decision using dual validation
    使用双重验证验证AI决策

    Validation process:
    1. AI直觉 (AI Intuition): AI confidence score
    2. 规则引擎逻辑 (Rules Engine Logic): 5 validation rules
       - Budget check
       - Inventory capacity
       - Historical consumption
       - Supplier availability
       - Profit margin

    Returns:
    - result: APPROVED/REJECTED/WARNING
    - confidence: Overall confidence score (0-1)
    - violations: List of rule violations
    - recommendations: Suggested modifications
    """
    try:
        validator = DecisionValidator()
        context = {
            "store_id": request.store_id,
            "decision_type": request.decision_type.value,
            **(request.context or {})
        }
        validation_result = await validator.validate_decision(
            decision=request.ai_suggestion,
            context=context
        )

        return {
            "success": True,
            "store_id": request.store_id,
            "decision_type": request.decision_type.value,
            "validation": {
                "result": validation_result["result"],
                "confidence": 1.0 if not validation_result["critical_failures"] else max(0.0, 1.0 - len(validation_result["critical_failures"]) * 0.2),
                "violations": [f["reason"] for f in validation_result["critical_failures"]],
                "recommendations": [w["reason"] for w in validation_result["warnings"]],
                "validated_at": validation_result["timestamp"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate/batch")
async def validate_batch_decisions(
    requests: List[ValidateDecisionRequest],
    db: AsyncSession = Depends(get_db)
):
    """
    Validate multiple AI decisions in batch
    批量验证多个AI决策

    Useful for validating a set of related decisions together
    """
    try:
        validator = DecisionValidator()
        results = []

        for req in requests:
            context = {
                "store_id": req.store_id,
                "decision_type": req.decision_type.value,
                **(req.context or {})
            }
            validation_result = await validator.validate_decision(
                decision=req.ai_suggestion,
                context=context
            )

            results.append({
                "store_id": req.store_id,
                "decision_type": req.decision_type.value,
                "result": validation_result["result"],
                "confidence": 1.0 if not validation_result["critical_failures"] else max(0.0, 1.0 - len(validation_result["critical_failures"]) * 0.2),
                "violations": [f["reason"] for f in validation_result["critical_failures"]]
            })

        # Summary statistics
        approved = sum(1 for r in results if r["result"] == "approved")
        rejected = sum(1 for r in results if r["result"] == "rejected")
        warnings = sum(1 for r in results if r["result"] == "warning")

        return {
            "success": True,
            "total": len(results),
            "summary": {
                "approved": approved,
                "rejected": rejected,
                "warnings": warnings
            },
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rules")
async def get_validation_rules(db: AsyncSession = Depends(get_db)):
    """
    Get all validation rules
    获取所有验证规则

    Returns list of available validation rules with descriptions
    """
    try:
        validator = DecisionValidator()
        rules_info = []

        for rule in validator.rules.values():
            rules_info.append({
                "name": rule.name,
                "description": getattr(rule, "description", "No description available")
            })

        return {
            "success": True,
            "total_rules": len(rules_info),
            "rules": rules_info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/anomaly/detect")
async def detect_anomaly(
    store_id: str,
    metric_name: str,
    current_value: float,
    db: AsyncSession = Depends(get_db)
):
    """
    Detect anomaly in metric value
    检测指标值异常

    Uses z-score method with 3σ threshold
    """
    try:
        validator = DecisionValidator()
        is_anomaly = validator.detect_anomaly(store_id, metric_name, current_value)

        return {
            "success": True,
            "store_id": store_id,
            "metric_name": metric_name,
            "current_value": current_value,
            "is_anomaly": is_anomaly,
            "threshold": "3σ (99.7% confidence)"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))