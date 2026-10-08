"""
Synthetic Dataset Generator
Instantly generates edge cases, adversarial inputs, and varied test suites 
to evaluate prompts rigorously without manual data entry.
"""
import json
import asyncio
from typing import List, Dict
from .llm_service import run_llm

async def generate_test_suite(prompt_content: str, num_cases: int = 5) -> List[Dict[str, str]]:
    """
    Analyzes the prompt and generates a structured JSON array of test cases.
    It attempts to extract required variables from the prompt and provides diverse inputs.
    """
    generator_prompt = f"""
You are an expert QA engineer for Large Language Models.
Analyze the following prompt and generate exactly {num_cases} highly diverse test cases to evaluate it.

PROMPT TO ANALYZE:
<prompt>
{prompt_content}
</prompt>

REQUIREMENTS FOR TEST CASES:
1. Standard/Happy path case
2. Edge case (e.g., extremely short/long input, weird formatting)
3. Adversarial case (attempting to break instructions or prompt inject)
4. Out-of-domain case (asking something irrelevant)
5. Complex/Nuanced case

Determine what variables the prompt expects (e.g., if it says "Summarize this {{text}}", the variable is "text").

OUTPUT FORMAT:
Return a raw JSON array of objects. Do not wrap in Markdown blocks.
Each object must have:
- "name": A short description of the test case
- "inputs": A dictionary of the variables needed by the prompt
- "expected": A string describing what a successful output should look like

Example Output:
[
  {{
    "name": "Happy Path - Standard Article",
    "inputs": {{"text": "A standard 500 word article about AI..."}},
    "expected": "A concise 3 bullet point summary."
  }}
]
"""
    
    res = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: run_llm("gpt-6.1-sol", generator_prompt, params={"temperature": 0.7})
    )
    
    content = res.get("response", "").strip()
    
    # Strip markdown if present
    if content.startswith("```json"):
        content = content[7:-3].strip()
    elif content.startswith("```"):
        content = content[3:-3].strip()
        
    try:
        cases = json.loads(content)
        if isinstance(cases, list) and len(cases) > 0:
            return cases
    except json.JSONDecodeError:
        pass
        
    # Fallback if generation failed
    return [{
        "name": "Fallback Test Case",
        "inputs": {"input": "Hello world"},
        "expected": "A valid response based on instructions."
    }]
