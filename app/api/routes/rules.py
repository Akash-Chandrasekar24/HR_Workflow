import json
import structlog
from pathlib import Path
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from app.core.config import settings
from app.services.rule_engine import RuleEngineService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/rules", tags=["Job Rules Configuration"])
rule_engine = RuleEngineService()


class MandatoryRuleSchema(BaseModel):
    field: str = Field(..., description="total_years_experience, skills, or education")
    value: Any = Field(..., description="Target minimum value or required skill name")
    type: str = Field(..., description="min_value, skill_present, or degree_present")
    label: str = Field(..., description="Human readable label for dashboard display")


class WeightedCategorySchema(BaseModel):
    category: str = Field(..., description="Category display name")
    weight: float = Field(..., description="Points weightage out of 100")
    keywords: List[str] = Field(..., description="Keywords searched in candidate profile")


class ThresholdsSchema(BaseModel):
    shortlist: float = Field(80.0, description="Minimum score to shortlist")
    review: float = Field(60.0, description="Minimum score for HR review")


class JobRoleRuleSchema(BaseModel):
    title: str = Field(..., description="Job Role Title")
    mandatory: List[MandatoryRuleSchema]
    weighted: List[WeightedCategorySchema]
    thresholds: ThresholdsSchema


@router.get("", summary="Get all active job screening rules & thresholds")
async def get_all_rules():
    """Returns current active job rules JSON configuration."""
    rules_path = settings.rules_absolute_path
    if not rules_path.exists():
        return {}
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Error reading job rules file", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to load job rules configuration")


@router.get("/{job_role}", summary="Get screening rules for specific job role")
async def get_role_rule(job_role: str):
    """Retrieves rules for a single job role."""
    rules = await get_all_rules()
    normalized = rule_engine.normalize_role_code(job_role)
    if normalized not in rules:
        raise HTTPException(status_code=404, detail=f"Job role '{job_role}' not found")
    return {
        "status": "SUCCESS",
        "job_role": normalized,
        "rules": rules[normalized]
    }



@router.put("/{job_role}", summary="Update screening rules & thresholds for a job role")
async def update_role_rule(job_role: str, updated_rule: JobRoleRuleSchema):
    """
    Dynamically updates mandatory rules, weighted scoring categories, and thresholds for HR.
    Saves directly to app/config/job_rules.json with hot-reloading.
    """
    rules = await get_all_rules()
    role_key = job_role.strip().upper().replace(" ", "_")
    
    rules[role_key] = updated_rule.model_dump()

    # Save to JSON file
    rules_path = settings.rules_absolute_path
    try:
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        with open(rules_path, "w", encoding="utf-8") as f:
            json.dump(rules, f, indent=2)
        
        # Hot-reload engine
        rule_engine.rules = rules
        logger.info("Updated job screening rules", job_role=role_key)
        return {
            "status": "SUCCESS",
            "message": f"Successfully updated screening criteria for {updated_rule.title}",
            "job_role": role_key,
            "rule": rules[role_key]
        }
    except Exception as e:
        logger.error("Failed to write updated job rules to disk", error=str(e))
        raise HTTPException(status_code=500, detail=f"Could not save rules configuration: {str(e)}")
