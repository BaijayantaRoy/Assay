from sqlmodel import Session, select
from uuid import UUID
from datetime import datetime, timezone
import json
# import openai # Uncomment when API key is available

from ..models import PromptVersion, EvaluationRun, EvaluationResult # Assuming we add Result to models
# We need to add TestSuite and TestCase to models first if not already there.

# Mock LLM Call
def mock_llm_call(prompt_text: str, config: dict):
    """Simulate an LLM response."""
    return f"Mock response to: {prompt_text[:20]}..."

def run_evaluation(run_id: UUID, session: Session):
    """
    Execute the evaluation run.
    In a real app, this would be a Celery task.
    """
    run = session.get(EvaluationRun, run_id)
    if not run:
        return

    run.status = "running"
    session.add(run)
    session.commit()

    try:
        # Fetch Prompt Version
        version = session.get(PromptVersion, run.prompt_version_id)
        
        # Fetch Test Suite (TODO: Add TestSuite model)
        # For now, let's assume we pass inputs directly or have a simple list
        # We need to implement TestSuite models first.
        
        # Mocking test cases for MVP
        test_inputs = [{"query": "Hello"}, {"query": "Pricing?"}]
        
        score_sum = 0
        
        for i, inputs in enumerate(test_inputs):
            # 1. Replace variables
            prompt_text = version.content
            for key, value in inputs.items():
                prompt_text = prompt_text.replace(f"{{{{{key}}}}}", str(value))
            
            # 2. Call LLM
            output = mock_llm_call(prompt_text, version.config)
            
            # 3. Score (Mock Judge)
            score = 0.9 # Mock score
            score_sum += score
            
            # 4. Save Result (TODO: Add EvaluationResult model to DB)
            # result = EvaluationResult(run_id=run.id, input=inputs, output=output, score=score)
            # session.add(result)
        
        run.status = "completed"
        run.score = score_sum / len(test_inputs)
        run.completed_at = datetime.now(timezone.utc)
        session.add(run)
        session.commit()
        
    except Exception as e:
        print(f"Eval Failed: {e}")
        run.status = "failed"
        session.add(run)
        session.commit()
