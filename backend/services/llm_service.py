"""
LLM Service — Real multi-provider execution with token counting and cost estimation.

Supported providers (model list checked 2026-10-08):
  - OpenAI    : gpt-6-astra, gpt-6.1-sol, gpt-6-luna
  - Anthropic : claude-opus-5-5, claude-sonnet-5-5, claude-haiku-5-5
  - Google    : gemini-3.1-pro-preview, gemini-3.8-flash
  - Ollama    : any locally-running model (gemma4, qwen3.5, llama3.1, etc.)
"""

import os
import time
import re
from typing import Optional

from sqlmodel import Session
from ..database import engine
from ..models import LLMModel

def _get_provider(model_id: str) -> str:
    key = "ollama" if model_id.startswith("ollama/") else model_id
    with Session(engine) as session:
        model = session.get(LLMModel, key)
        if model:
            return model.provider

    if model_id.startswith("ollama/"):
        return "ollama"
    if model_id.startswith("gpt-") or model_id.startswith("o3"):
        return "openai"
    if model_id.startswith("claude-"):
        return "anthropic"
    if model_id.startswith("gemini-"):
        return "google"
    if model_id.startswith("deepseek"):
        return "deepseek"
    if model_id.startswith("qwen"):
        return "alibaba"
    if model_id.startswith("ernie"):
        return "baidu"
    if model_id.startswith("mistral"):
        return "mistral"
    if model_id.startswith("falcon"):
        return "tii"
    if model_id.startswith("krutrim"):
        return "krutrim"
    return "openai"


def _estimate_cost(model_id: str, prompt_tokens: int, completion_tokens: int) -> float:
    key = "ollama" if model_id.startswith("ollama/") else model_id
    with Session(engine) as session:
        model = session.get(LLMModel, key)
        if model:
            return round(
                (prompt_tokens / 1_000_000) * model.input_cost_per_m
                + (completion_tokens / 1_000_000) * model.output_cost_per_m,
                8,
            )
    return 0.0


def _count_tokens_approx(text: str) -> int:
    """Rough token count without API call (1 token ≈ 4 chars)."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def _render_prompt(content: str, variables: dict) -> str:
    """Substitute {{variable}} placeholders."""
    rendered = content
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
    return rendered


# ---------------------------------------------------------------------------
# Provider-specific runners
# ---------------------------------------------------------------------------

def _run_openai(model: str, prompt: str, params: dict) -> dict:
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set. Add it in Settings.")
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=params.get("temperature", 0.7),
        max_tokens=params.get("max_tokens", 1024),
        top_p=params.get("top_p", 1.0),
    )
    msg = response.choices[0].message.content or ""
    usage = response.usage
    return {
        "response": msg,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
    }


def _run_anthropic(model: str, prompt: str, params: dict) -> dict:
    import anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set. Add it in Settings.")
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=params.get("max_tokens", 1024),
        temperature=params.get("temperature", 0.7),
        messages=[{"role": "user", "content": prompt}],
    )
    content = message.content[0].text if message.content else ""
    usage = message.usage
    return {
        "response": content,
        "prompt_tokens": usage.input_tokens,
        "completion_tokens": usage.output_tokens,
    }


def _run_google(model: str, prompt: str, params: dict) -> dict:
    import google.generativeai as genai
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not set. Add it in Settings.")
    genai.configure(api_key=api_key)
    gen_config = genai.GenerationConfig(
        temperature=params.get("temperature", 0.7),
        max_output_tokens=params.get("max_tokens", 1024),
        top_p=params.get("top_p", 1.0),
    )
    gmodel = genai.GenerativeModel(model_name=model, generation_config=gen_config)
    resp = gmodel.generate_content(prompt)
    text = resp.text or ""
    # Google returns token counts in usage_metadata
    usage = resp.usage_metadata
    prompt_tokens = getattr(usage, "prompt_token_count", _count_tokens_approx(prompt))
    completion_tokens = getattr(usage, "candidates_token_count", _count_tokens_approx(text))
    return {
        "response": text,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }


def _run_ollama(model: str, prompt: str, params: dict) -> dict:
    """Call a locally-running Ollama instance."""
    import httpx
    # model might be "ollama/llama3.3" — strip prefix
    ollama_model = model.replace("ollama/", "")
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    payload = {
        "model": ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": params.get("temperature", 0.7),
            "num_predict": params.get("max_tokens", 1024),
        },
    }
    resp = httpx.post(f"{ollama_url}/api/generate", json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    text = data.get("response", "")
    prompt_tokens = data.get("prompt_eval_count", _count_tokens_approx(prompt))
    completion_tokens = data.get("eval_count", _count_tokens_approx(text))
    return {
        "response": text,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def run_llm(
    model: str,
    content: str,
    variables: Optional[dict] = None,
    params: Optional[dict] = None,
) -> dict:
    """
    Run a prompt through the specified LLM model.

    Returns:
        {
            rendered_prompt, response, model,
            prompt_tokens, completion_tokens, total_tokens,
            estimated_cost_usd, latency_ms
        }
    """
    variables = variables or {}
    params = params or {}
    rendered = _render_prompt(content, variables)
    provider = _get_provider(model)

    start = time.time()
    try:
        if provider == "openai":
            result = _run_openai(model, rendered, params)
        elif provider == "anthropic":
            result = _run_anthropic(model, rendered, params)
        elif provider == "google":
            result = _run_google(model, rendered, params)
        elif provider == "ollama":
            result = _run_ollama(model, rendered, params)
        elif provider in ["deepseek", "alibaba", "mistral", "tii", "krutrim"]:
            # Treat OpenAI-compatible APIs as openai for now (they use the same library standard)
            # A real implementation would pass a custom base_url
            result = _run_openai(model, rendered, params)
        elif provider == "baidu":
            # Mock Ernie fallback
            result = _run_openai(model, rendered, params)
        else:
            raise ValueError(f"Unknown provider for model: {model}")
    except Exception as e:
        raise RuntimeError(str(e))

    latency_ms = int((time.time() - start) * 1000)
    prompt_tokens = result["prompt_tokens"]
    completion_tokens = result["completion_tokens"]
    total_tokens = prompt_tokens + completion_tokens
    cost = _estimate_cost(model, prompt_tokens, completion_tokens)

    return {
        "rendered_prompt": rendered,
        "response": result["response"],
        "model": model,
        "provider": provider,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": cost,
        "latency_ms": latency_ms,
    }
