"""
Advanced 2026 Features Router
POST /advanced/optimize  — Run DSPy-style Auto-Optimizer
POST /advanced/synthetic — Generate Synthetic Eval Dataset
"""
from fastapi import APIRouter
from ...services.optimizer import optimize_prompt
from ...services.synthetic_data import generate_test_suite

router = APIRouter(prefix="/advanced", tags=["advanced"])

@router.post("/optimize")
async def run_optimization(body: dict):
    """
    body: { draft_prompt: str, test_cases: list[dict], target_model: str, max_iterations: int }
    """
    draft = body.get("draft_prompt", "")
    cases = body.get("test_cases", [])
    model = body.get("target_model", "gpt-4o")
    iters = body.get("max_iterations", 3)
    
    if not cases:
        # Generate some quick synthetic cases if none provided
        cases = await generate_test_suite(draft, num_cases=2)
        
    res = await optimize_prompt(draft, cases, model, iters)
    return res.dict()

@router.post("/synthetic")
async def generate_synthetic_data(body: dict):
    """
    body: { prompt_content: str, num_cases: int }
    """
    prompt = body.get("prompt_content", "")
    num = body.get("num_cases", 5)
    cases = await generate_test_suite(prompt, num)
    return {"cases": cases}
