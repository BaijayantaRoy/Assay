"""
Intelligence Router:
  GET  /intelligence/models          — All Model DNA profiles
  GET  /intelligence/models/{id}     — Single model DNA
  POST /intelligence/analyze         — Real-time prompt scoring
  POST /intelligence/adapt           — Reformat prompt for target model (uses LLM)
  GET  /intelligence/anatomy-guide   — All anatomy block definitions
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ...database import get_session
from ...services.prompt_intelligence import analyze_prompt, get_model_dna, MODEL_DNA, ANATOMY_BLOCKS

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/models")
def list_model_dna():
    """Return DNA profiles for all supported models."""
    return [
        {
            "id": k,
            "name": v["name"],
            "provider": v["provider"],
            "personality": v["personality"],
            "strengths": v["strengths"],
            "power_techniques": v["power_techniques"],
            "optimal_length": v["optimal_length"],
            "context_window": v["context_window"],
            "modality_tips": v.get("modality_tips", {}),
            "template": v["template"],
        }
        for k, v in MODEL_DNA.items()
    ]


@router.get("/models/{model_id:path}")
def get_single_model_dna(model_id: str):
    """Return full DNA for a specific model."""
    dna = get_model_dna(model_id)
    return {**dna, "id": model_id}


@router.post("/analyze")
def analyze(body: dict):
    """
    Analyze a prompt and return scores + suggestions.
    Body: { "content": "...", "model": "gpt-4o" }
    """
    content = body.get("content", "")
    model = body.get("model", "gpt-4o")
    if not content.strip():
        raise HTTPException(status_code=400, detail="content is required")
    return analyze_prompt(content, model)


@router.post("/adapt")
async def adapt_prompt(body: dict):
    """
    Reformat a prompt for a target model using LLM.
    Body: { "content": "...", "source_model": "gpt-4o", "target_model": "claude-opus-4-20250514" }
    """
    content = body.get("content", "")
    source = body.get("source_model", "gpt-4o")
    target = body.get("target_model", "claude-sonnet-4-20250514")

    if not content.strip():
        raise HTTPException(status_code=400, detail="content is required")

    source_dna = get_model_dna(source)
    target_dna = get_model_dna(target)

    adapt_prompt_text = f"""You are an expert prompt engineer specializing in cross-model prompt optimization.

Convert the following prompt from {source_dna['name']}-optimized format to {target_dna['name']}-optimized format.

Source model ({source_dna['name']}) characteristics:
{source_dna['personality']}

Target model ({target_dna['name']}) characteristics:
{target_dna['personality']}

Target model power techniques:
{chr(10).join(f"- {t}" for t in target_dna['power_techniques'])}

Target model template pattern:
{target_dna['template']}

Original prompt to convert:
---
{content}
---

Rules:
1. Preserve ALL the original intent and information
2. Apply the target model's preferred formatting (XML tags for Claude, ## headers for Gemini, plain text for GPT)
3. Add any structural elements the target model responds best to
4. Do NOT add new instructions or change the task
5. Return ONLY the converted prompt, nothing else"""

    try:
        from ...services.llm_service import run_llm
        result = run_llm(
            model=target,
            content=adapt_prompt_text,
            variables={},
            params={"temperature": 0.3, "max_tokens": 2048},
        )
        return {
            "adapted_prompt": result["response"],
            "source_model": source_dna["name"],
            "target_model": target_dna["name"],
            "tokens_used": result["total_tokens"],
            "cost_usd": result["estimated_cost_usd"],
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Adaptation failed: {str(e)}")


@router.get("/anatomy-guide")
def anatomy_guide():
    """Return all anatomy block definitions for the UI guide."""
    return [
        {
            "id": bid,
            "label": b["label"],
            "color": b["color"],
            "importance": b["importance"],
            "description": f"Defines the {b['label'].lower()} section of your prompt.",
            "example": b["example"],
        }
        for bid, b in ANATOMY_BLOCKS.items()
    ]
