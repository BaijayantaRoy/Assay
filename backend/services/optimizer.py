"""
Auto-Optimizer Engine (DSPy-inspired)

This service takes a draft prompt and a set of input/output examples (or an evaluation function),
and uses an evolutionary algorithm (via LLM) to mutate, test, and find the optimal prompt instructions.
"""
import asyncio
from typing import List, Dict, Any
from pydantic import BaseModel
import re

from .llm_service import run_llm

class OptimizationResult(BaseModel):
    original_prompt: str
    best_prompt: str
    score: float
    iterations: int
    history: List[Dict[str, Any]]


async def _evaluate_prompt(prompt: str, test_cases: List[Dict[str, str]], model: str) -> float:
    """
    Evaluates a prompt against a set of test cases.
    Returns a score from 0.0 to 1.0.
    In a real scenario, this would use a semantic similarity or LLM-as-a-judge score.
    For this implementation, we use an LLM-as-a-judge to score out of 10.
    """
    total_score = 0.0
    
    # Run all test cases in parallel
    async def _run_and_score(tc):
        # 1. Generate output with the candidate prompt
        gen_result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_llm(model, prompt, tc.get("inputs", {}))
        )
        output = gen_result.get("response", "")
        
        # 2. Score output against expected criteria using an LLM Judge
        judge_prompt = f"""
You are an expert evaluator. Score the actual output against the expected output criteria.
Give a score from 0.0 to 1.0 where 1.0 is a perfect match/perfect quality, and 0.0 is completely wrong.
Reply with ONLY the numeric score.

EXPECTED CRITERIA:
{tc.get("expected", "High quality, accurate response")}

ACTUAL OUTPUT:
{output}
"""
        judge_res = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_llm("gpt-6.1-sol", judge_prompt)
        )
        
        try:
            score_str = re.search(r"0\.\d+|1\.0|0|1", judge_res.get("response", "")).group()
            return float(score_str)
        except Exception:
            return 0.5

    tasks = [_run_and_score(tc) for tc in test_cases]
    scores = await asyncio.gather(*tasks)
    
    if not scores: return 0.0
    return sum(scores) / len(scores)


async def generate_mutations(current_prompt: str, history: str, num_mutations: int = 3) -> List[str]:
    """Uses an LLM to generate variations of the prompt to try and improve it."""
    mutation_prompt = f"""
You are an expert prompt engineer. I am trying to optimize a prompt.
Here is the current prompt:
<prompt>
{current_prompt}
</prompt>

Here is the history of previous attempts and their feedback:
<history>
{history}
</history>

Generate {num_mutations} DIFFERENT, improved variations of this prompt. 
Try different strategies: 
1. Add step-by-step reasoning (Chain of Thought)
2. Clarify constraints and output formats
3. Add a persona or change the tone

Output ONLY the raw variations separated by this exact delimiter: "===VARIATION_SPLIT==="
"""
    res = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: run_llm("gpt-6.1-sol", mutation_prompt, params={"temperature": 0.8})
    )
    
    content = res.get("response", "")
    variations = [v.strip() for v in content.split("===VARIATION_SPLIT===") if v.strip()]
    # Ensure we don't return empty lists if parsing fails
    if not variations:
        variations = [current_prompt + "\n\nThink step by step."]
    return variations[:num_mutations]


async def optimize_prompt(
    draft_prompt: str, 
    test_cases: List[Dict[str, str]], 
    target_model: str = "gpt-6.1-sol",
    max_iterations: int = 3
) -> OptimizationResult:
    """
    The main DSPy-style optimization loop.
    1. Score baseline.
    2. Generate mutations.
    3. Score mutations.
    4. Keep the best. Repeat.
    """
    best_prompt = draft_prompt
    best_score = await _evaluate_prompt(draft_prompt, test_cases, target_model)
    
    history_log = [{"prompt": draft_prompt, "score": best_score, "iteration": 0}]
    history_text = f"Baseline Score: {best_score:.2f}\n"

    if best_score >= 0.95:
        # Already perfect
        return OptimizationResult(
            original_prompt=draft_prompt, best_prompt=best_prompt,
            score=best_score, iterations=0, history=history_log
        )

    for i in range(1, max_iterations + 1):
        mutations = await generate_mutations(best_prompt, history_text, num_mutations=3)
        
        # Evaluate mutations in parallel
        eval_tasks = [_evaluate_prompt(m, test_cases, target_model) for m in mutations]
        scores = await asyncio.gather(*eval_tasks)
        
        for idx, score in enumerate(scores):
            history_log.append({"prompt": mutations[idx], "score": score, "iteration": i})
            
            if score > best_score:
                best_score = score
                best_prompt = mutations[idx]
                
        history_text += f"\nIteration {i} Best Score: {best_score:.2f}"
        
        if best_score >= 0.95:
            break

    return OptimizationResult(
        original_prompt=draft_prompt,
        best_prompt=best_prompt,
        score=best_score,
        iterations=max_iterations,
        history=history_log
    )
