"""
Prompt Intelligence Engine — real-time analysis, Model DNA, anatomy detection.
"""
import re
from typing import Optional

# ---------------------------------------------------------------------------
# Model DNA
# ---------------------------------------------------------------------------
MODEL_DNA = {
    "gpt-4o": {
        "name": "GPT-4o", "provider": "openai",
        "personality": "Versatile instruction follower. Loves structured, hierarchical prompts. Excels at JSON output, code, and multi-step reasoning.",
        "strengths": ["Code generation", "JSON/structured output", "Multi-step reasoning", "Tool calling", "Complex instructions"],
        "power_techniques": [
            "Use a clear system role: 'You are an expert X with Y years of experience'",
            "Use numbered steps for complex multi-part tasks",
            "Add 'Respond ONLY with valid JSON' for structured output",
            "Use triple backticks to delimit input data: ```data```",
            "Specify output format explicitly: 'Format your response as a markdown table'",
            "Add 'Think step by step' before reasoning-heavy tasks",
        ],
        "anti_patterns": [
            {"pattern": r"please\s+be\s+(kind|nice|gentle)", "message": "Politeness framing wastes tokens — GPT-4o responds to direct instructions."},
            {"pattern": r"<(task|context|format)>", "message": "XML tags aren't optimal for GPT — use plain numbered sections or headers instead."},
        ],
        "template": "You are {role}.\n\nContext:\n{context}\n\nTask:\n{task}\n\nRequirements:\n{constraints}\n\nOutput format: {format}",
        "optimal_length": "200–800 tokens for complex tasks",
        "context_window": "128k tokens",
        "modality_tips": {
            "text": "Use plain text with numbered lists. Markdown headers work well.",
            "code": "Specify language, style guide, and error handling requirements explicitly.",
            "vision": "State the image analysis goal first, then specify desired output detail level.",
        },
    },
    "o3": {
        "name": "o3", "provider": "openai",
        "personality": "OpenAI's most powerful reasoning model. Thinks deeply before responding. Best for math, science, complex coding, and logic puzzles.",
        "strengths": ["Mathematical reasoning", "Scientific analysis", "Complex algorithm design", "Logic puzzles", "Research synthesis"],
        "power_techniques": [
            "State the PROBLEM, not the method — let o3 figure out the approach",
            "Provide constraints and success criteria rather than step-by-step instructions",
            "Use for problems where GPT-4o fails — o3 retries with different strategies",
            "Include all relevant context upfront — o3 thinks holistically",
            "Ask for reasoning: 'Show your work and explain each step'",
        ],
        "anti_patterns": [
            {"pattern": r"think\s+step\s+by\s+step", "message": "o3 already reasons deeply by design — no need to prompt for it. Just state the problem."},
            {"pattern": r"quickly|briefly|fast", "message": "o3 is designed for depth over speed. Use GPT-4o-mini for quick tasks."},
        ],
        "template": "Problem:\n{task}\n\nContext:\n{context}\n\nConstraints:\n{constraints}\n\nSuccess criteria: {format}",
        "optimal_length": "100–500 tokens — o3 amplifies concise problem statements",
        "context_window": "200k tokens",
        "modality_tips": {
            "text": "State problems precisely. Mathematical notation is understood natively.",
            "code": "Describe the algorithmic challenge. o3 will design the optimal solution.",
        },
    },
    "claude-opus-4-20250514": {
        "name": "Claude Opus 4", "provider": "anthropic",
        "personality": "Deep thinker with strong ethical reasoning. Loves XML tags. Exceptional at nuanced writing, long-document analysis, and following complex multi-part instructions precisely.",
        "strengths": ["Long document analysis", "Nuanced creative writing", "Complex multi-step instructions", "Code with detailed explanation", "Research synthesis"],
        "power_techniques": [
            "Wrap sections in XML tags: <context>, <task>, <requirements>, <format>",
            "State your intent clearly — Claude reasons about your underlying goal",
            "Use <thinking> tags to enable extended reasoning (Opus 4 supports it natively)",
            "Provide examples inside <example> tags for consistency",
            "For documents: 'Here is the text: <document>{content}</document>'",
            "Pre-fill the response: end with 'Assistant: Let me' to guide direction",
        ],
        "anti_patterns": [
            {"pattern": r"ignore (all )?previous instructions", "message": "Claude's Constitutional AI resists this. State your legitimate need directly instead."},
            {"pattern": r"^(in\s+)?\d+\s+words", "message": "Put length constraints at the END of your prompt for better compliance."},
        ],
        "template": "<context>\n{context}\n</context>\n\n<task>\n{task}\n</task>\n\n<requirements>\n{constraints}\n</requirements>\n\n<format>\n{format}\n</format>",
        "optimal_length": "300–1500 tokens — Opus thrives with rich context",
        "context_window": "200k tokens",
        "modality_tips": {
            "text": "XML tags for every section. Claude's parsing of XML is near-perfect.",
            "code": "Wrap code blocks in <code lang='python'>. Specify test cases required.",
            "vision": "Use <image_goal> to state analysis purpose. Specify output: JSON, markdown, prose.",
        },
    },
    "claude-sonnet-4-20250514": {
        "name": "Claude Sonnet 4", "provider": "anthropic",
        "personality": "The ideal balance of intelligence and speed. Best for everyday production tasks — writing, coding, analysis — with Claude's signature quality.",
        "strengths": ["Fast high-quality responses", "Writing and editing", "Summarization", "Q&A", "Code review"],
        "power_techniques": [
            "XML tags work well: <task>, <context>",
            "Add 'Be concise' or 'Be comprehensive' to calibrate length",
            "Specify audience: 'Explain this to a senior software engineer'",
            "For formatting: 'Structure as: Overview, Steps, Example, Gotchas'",
        ],
        "anti_patterns": [
            {"pattern": r"(comprehensive|exhaustive)\s+analysis", "message": "For exhaustive analysis, use Claude Opus 4 — Sonnet is optimized for speed/quality balance."},
        ],
        "template": "<context>{context}</context>\n\n<task>{task}</task>\n\n<format>{format}</format>",
        "optimal_length": "100–600 tokens for best speed/quality ratio",
        "context_window": "200k tokens",
        "modality_tips": {
            "text": "Concise XML tags. Sonnet is fast — avoid over-engineering prompts.",
            "code": "State language and expected output format explicitly.",
            "vision": "State specific question about the image clearly.",
        },
    },
    "gemini-2.5-pro": {
        "name": "Gemini 2.5 Pro", "provider": "google",
        "personality": "Google's flagship. Native 1M token context, multi-modal (text/vision/audio/video), and deep thinking mode. Best for research, long-doc analysis, and complex multi-modal tasks.",
        "strengths": ["1M token context", "Multi-modal (text+vision+audio+video)", "Deep reasoning with thinking mode", "Code generation", "Factual grounding"],
        "power_techniques": [
            "Enable thinking: add 'Think carefully before answering'",
            "Grounding: 'Based ONLY on the provided document, answer...'",
            "Use Markdown naturally — ## headings, **bold**, tables",
            "For long context: 'Here is the codebase. Focus ONLY on auth.py'",
            "Add 'Respond in {language}' for multilingual tasks",
            "For multi-modal: describe goal, then provide media, then ask question",
        ],
        "anti_patterns": [
            {"pattern": r"<(task|context|format)>", "message": "Gemini prefers Markdown (## headings) over XML tags — remove angle brackets."},
        ],
        "template": "## Context\n{context}\n\n## Task\n{task}\n\n## Requirements\n{constraints}\n\n## Output Format\n{format}",
        "optimal_length": "Flexible — Gemini 2.5 Pro handles up to 1M tokens natively",
        "context_window": "1,000,000 tokens",
        "modality_tips": {
            "text": "Clean Markdown headers. Gemini understands document structure naturally.",
            "code": "Specify framework versions and add 'with inline comments' for explainability.",
            "vision": "Describe image type → state your question → specify output format.",
            "audio": "Ask for timestamps. Specify: transcription, sentiment, or action items.",
            "video": "Specify timestamp range. Ask for: summary, key moments, or frame analysis.",
        },
    },
    "gemini-2.5-flash": {
        "name": "Gemini 2.5 Flash", "provider": "google",
        "personality": "Fastest Gemini. Built for high-throughput classification, extraction, and quick Q&A at minimal cost.",
        "strengths": ["Extreme speed", "Cost efficiency ($0.075/M tokens)", "Classification", "Quick summaries", "Batch processing"],
        "power_techniques": [
            "Keep prompts under 200 tokens for maximum speed",
            "Add 'Answer in one sentence' or 'Answer in 3 bullet points'",
            "Use Flash for filtering, Pro for deep analysis (chain them)",
            "Classification: 'Label as: A, B, or C. Respond ONLY with the label.'",
        ],
        "anti_patterns": [
            {"pattern": r"(comprehensive|detailed|thorough|deep|exhaustive)", "message": "Use Gemini 2.5 Pro for depth — Flash is optimized for speed, not exhaustive analysis."},
        ],
        "template": "Task: {task}\n\nContext: {context}\n\nFormat: {format}",
        "optimal_length": "50–200 tokens for maximum throughput",
        "context_window": "1,000,000 tokens",
        "modality_tips": {
            "text": "Short, direct prompts. Single clear ask per call.",
            "vision": "Simple image questions. Use Pro for complex visual analysis.",
        },
    },
    "ollama/llama3.3": {
        "name": "Llama 3.3 (Local)", "provider": "ollama",
        "personality": "Meta's open-weight champion running 100% locally. No data leaves your machine. Excellent instruction following for a local model.",
        "strengths": ["Complete data privacy", "Zero API cost", "Offline use", "Code generation", "Good instruction following"],
        "power_techniques": [
            "Use Llama chat format: clear 'User:' and 'Assistant:' turns",
            "Be explicit — smaller models need more guidance than cloud models",
            "Avoid long preambles — get to the task in the first sentence",
            "Add 'Think step by step' for reasoning tasks",
            "Add 'Respond ONLY in English' to prevent language mixing",
            "Break large tasks into smaller sequential prompts",
        ],
        "anti_patterns": [
            {"pattern": r".{3000,}", "message": "Very long prompts degrade local model quality. Split into smaller focused tasks."},
            {"pattern": r"(entire codebase|full document|complete analysis)", "message": "Local models have limited reliable context. Break into focused chunks."},
        ],
        "template": "You are {role}.\n\n{context}\n\nTask: {task}\n\nRequirements: {constraints}\n\nFormat: {format}",
        "optimal_length": "50–300 tokens for reliable output quality",
        "context_window": "128k tokens (varies by quantization)",
        "modality_tips": {
            "text": "Direct instructions. No XML. Plain numbered lists work best.",
            "code": "Specify language. Break complex code into smaller functions one at a time.",
        },
    },
}

ANATOMY_BLOCKS = {
    "role":     {"label": "Role / Persona",       "patterns": [r"you\s+are\s+(a|an|the)", r"act\s+as", r"your\s+role\s+is"], "color": "violet", "importance": "critical", "example": "You are an expert Python developer with 10 years of experience."},
    "context":  {"label": "Context / Background", "patterns": [r"context:", r"background:", r"given\s+that", r"here\s+is\s+(the|a)", r"<context>", r"##\s*context"], "color": "blue", "importance": "high", "example": "The user is a beginner with no coding experience."},
    "task":     {"label": "Task / Objective",     "patterns": [r"(please\s+)?(write|create|generate|analyze|explain|summarize|translate|review|build)", r"task:", r"<task>", r"your\s+(job|goal)\s+is", r"##\s*task"], "color": "emerald", "importance": "critical", "example": "Write a Python function that validates email addresses."},
    "constraints": {"label": "Constraints / Rules", "patterns": [r"do\s+not", r"don'?t", r"avoid", r"never", r"must\s+(not|always|be)", r"requirements?:"], "color": "amber", "importance": "medium", "example": "Do not use external libraries. Keep under 20 lines."},
    "format":   {"label": "Output Format",        "patterns": [r"format:", r"output\s+(as|in|format)", r"respond\s+(as|in|with)\s+(a|an|json|markdown|list|table)", r"use\s+(json|markdown|bullet|numbered)", r"<format>", r"##\s*(output|format)"], "color": "orange", "importance": "high", "example": "Respond in JSON with keys: name, email, valid."},
    "examples": {"label": "Few-Shot Examples",    "patterns": [r"for\s+example", r"e\.g\.", r"example\s*:", r"input\s*:\s*[\"\']", r"<example>"], "color": "cyan", "importance": "medium", "example": "Example: Input: 'hello' → Output: 'HELLO'"},
    "cot":      {"label": "Chain-of-Thought",     "patterns": [r"think\s+step\s+by\s+step", r"let['']?s?\s+think", r"reason\s+(through|about)", r"break\s+(it\s+)?down"], "color": "pink", "importance": "medium", "example": "Think step by step before giving your final answer."},
    "audience": {"label": "Target Audience",      "patterns": [r"for\s+a\s+(beginner|expert|child|developer|non.technical)", r"(explain\s+to|write\s+for)\s+a", r"assuming\s+the\s+(reader|user)\s+(is|has)"], "color": "teal", "importance": "low", "example": "Explain this to a non-technical product manager."},
}

VAGUE_WORDS = ["something", "stuff", "thing", "etc", "whatever", "maybe", "perhaps", "kind of", "sort of", "somehow", "various", "several"]
FILLER_PHRASES = ["please note that", "it is important to", "as you know", "needless to say", "in order to", "due to the fact that", "at this point in time"]


def analyze_prompt(content: str, model_id: str = "gpt-4o") -> dict:
    if not content or not content.strip():
        return {"error": "Empty prompt"}

    cl = content.lower()
    words = content.split()
    dna = MODEL_DNA.get(model_id) or next((v for k, v in MODEL_DNA.items() if model_id.startswith(k.split("/")[0])), MODEL_DNA["gpt-4o"])

    # Anatomy
    anatomy = {bid: any(re.search(p, cl) for p in b["patterns"]) for bid, b in ANATOMY_BLOCKS.items()}
    critical_missing = [bid for bid, b in ANATOMY_BLOCKS.items() if b["importance"] == "critical" and not anatomy[bid]]

    # Clarity
    vague_found = [w for w in VAGUE_WORDS if w in cl]
    clarity = 60
    clarity += 20 if anatomy["task"] else -20
    clarity += 15 if anatomy["format"] else 0
    clarity += 10 if anatomy["role"] else 0
    clarity -= len(vague_found) * 8
    clarity -= 25 if len(words) < 8 else 0
    clarity = max(0, min(100, clarity))

    # Specificity
    spec = 40
    spec += 20 if anatomy["constraints"] else 0
    spec += 25 if anatomy["examples"] else 0
    spec += 15 if anatomy["format"] else 0
    spec += 10 if anatomy["audience"] else 0
    spec -= 10 if re.match(r"^(write|create|make|generate)\s+a\s+", cl) else 0
    spec = max(0, min(100, spec))

    # Token efficiency
    filler_found = [p for p in FILLER_PHRASES if p in cl]
    token_eff = max(0, 100 - len(filler_found) * 15)

    # Model fit
    model_fit = 65
    anti_hits = []
    for ap in dna.get("anti_patterns", []):
        if re.search(ap["pattern"], cl):
            anti_hits.append({"message": ap["message"]})
            model_fit -= 15
    if model_id.startswith("claude") and "<task>" in cl:
        model_fit += 20
    if model_id.startswith("gemini") and "##" in content:
        model_fit += 15
    if "ollama" in model_id and len(words) < 80:
        model_fit += 15
    model_fit = max(0, min(100, model_fit))

    overall = int(clarity * 0.3 + spec * 0.3 + model_fit * 0.25 + token_eff * 0.15)

    suggestions = []
    if not anatomy["role"]:
        suggestions.append({"priority": "high", "block": "role", "message": "Add a role to set expertise and tone.", "example": "You are an expert {role} with deep experience in {domain}."})
    if not anatomy["format"]:
        suggestions.append({"priority": "medium", "block": "format", "message": "Specify output format for consistent results.", "example": "Respond in JSON / Use bullet points / Format as markdown table."})
    if not anatomy["examples"] and len(words) > 40:
        suggestions.append({"priority": "low", "block": "examples", "message": "Add 1–2 few-shot examples to dramatically improve accuracy."})
    if vague_found:
        suggestions.append({"priority": "high", "message": f"Replace vague words ({', '.join(vague_found[:3])}) with specific terms."})
    if filler_found:
        suggestions.append({"priority": "medium", "message": f"Remove filler phrases to improve clarity ({', '.join(filler_found[:2])})."})

    return {
        "scores": {"overall": overall, "clarity": clarity, "specificity": spec, "model_fit": model_fit, "token_efficiency": token_eff},
        "anatomy": anatomy,
        "critical_missing": critical_missing,
        "anti_patterns": anti_hits,
        "suggestions": suggestions,
        "vague_words": vague_found,
        "word_count": len(words),
        "estimated_tokens": max(1, len(content) // 4),
        "model_dna": {"name": dna["name"], "personality": dna["personality"], "power_techniques": dna["power_techniques"], "optimal_length": dna["optimal_length"], "template": dna["template"]},
    }


def get_model_dna(model_id: str) -> dict:
    if model_id in MODEL_DNA:
        return MODEL_DNA[model_id]
    for k, v in MODEL_DNA.items():
        if model_id.startswith(k.split("/")[0]):
            return v
    return MODEL_DNA["gpt-4o"]
