"""Library Router — Starter Prompts + Prompt Intelligence Engine (PIE)"""
from fastapi import APIRouter, Query
from typing import List, Optional
import re

router = APIRouter(prefix="/library", tags=["library"])

# ---------------------------------------------------------------------------
# Starter Prompts Data
# ---------------------------------------------------------------------------
STARTER_PROMPTS = [
    # MEMORY
    {"slug":"mem-conversation","category":"memory","category_label":"🧠 Memory","title":"Conversation History Injection","description":"Maintain context across long conversations.","tags":["memory","context"],"modality":"text","content":"You are a helpful assistant with memory of our conversation.\n\n<conversation_history>\n{{conversation_history}}\n</conversation_history>\n\nUser: {{user_message}}"},
    {"slug":"mem-persona","category":"memory","category_label":"🧠 Memory","title":"Persistent Persona Memory","description":"Keep the AI's persona consistent across sessions.","tags":["memory","persona"],"modality":"text","content":"You are {{persona_name}}, a {{persona_description}}.\n\nPrevious session context:\n{{session_context}}\n\nContinue being {{persona_name}}. Respond to: {{user_input}}"},
    {"slug":"mem-rolling-summary","category":"memory","category_label":"🧠 Memory","title":"Rolling Summary Memory","description":"Summarize conversation to fit context window.","tags":["memory","summarization"],"modality":"text","content":"Previous conversation summary:\n{{rolling_summary}}\n\nRecent messages:\n{{recent_messages}}\n\nUser: {{user_message}}\n\nBefore answering, update the summary internally."},

    # VIBE CODING
    {"slug":"vibe-component","category":"vibe_coding","category_label":"🎨 Vibe Coding","title":"React Component (Glassmorphism)","description":"Generate a stunning glassmorphism React component.","tags":["react","ui","glassmorphism"],"modality":"text","content":"Create a React component for {{component_name}}.\n\nDesign vibe: glassmorphism — frosted glass panels, subtle blur backdrop, soft gradients.\nColor palette: {{color_palette}}\nFunctionality: {{functionality}}\n\nUse Tailwind CSS. Include hover animations and smooth transitions. Make it stunning."},
    {"slug":"vibe-fullstack","category":"vibe_coding","category_label":"🎨 Vibe Coding","title":"Full-Stack Feature Plan","description":"Plan a complete feature from DB to UI.","tags":["fullstack","architecture"],"modality":"text","content":"Plan the full implementation of {{feature_name}} for a {{stack}} application.\n\nInclude:\n1. Database schema\n2. API endpoints\n3. Frontend components\n4. State management\n5. Edge cases to handle\n\nBe specific and production-ready."},
    {"slug":"vibe-debug","category":"vibe_coding","category_label":"🎨 Vibe Coding","title":"Expert Bug Investigator","description":"Deep-dive bug analysis for any codebase.","tags":["debug","coding"],"modality":"text","content":"You are a senior {{language}} engineer. Investigate this bug:\n\nCode:\n```{{language}}\n{{code}}\n```\n\nError: {{error_message}}\n\nProvide: root cause, fix, and how to prevent this class of bug in future."},
    {"slug":"vibe-cursor","category":"vibe_coding","category_label":"🎨 Vibe Coding","title":"Cursor/Windsurf Agent Task","description":"Optimized prompt for AI coding agent tools.","tags":["cursor","windsurf","agent"],"modality":"text","content":"Task: {{task_description}}\n\nContext:\n- Stack: {{stack}}\n- File(s) to modify: {{files}}\n- Constraints: {{constraints}}\n\nImplement this completely. Write production-quality code. Add comments for non-obvious logic."},

    # VISION
    {"slug":"vision-image-analysis","category":"vision","category_label":"👁️ Vision","title":"Detailed Image Analysis","description":"Comprehensive image description and analysis.","tags":["vision","image","analysis"],"modality":"vision","content":"Analyze this image in detail:\n\n1. **What is shown**: Describe the main subjects and scene\n2. **Details**: Colors, textures, spatial relationships\n3. **Context**: What situation or setting does this depict?\n4. **Notable elements**: Anything unusual or significant\n5. **Interpretation**: What message or purpose does this image convey?\n\nFocus on: {{focus_area}}"},
    {"slug":"vision-ocr","category":"vision","category_label":"👁️ Vision","title":"Document OCR & Structure","description":"Extract and structure text from images.","tags":["vision","ocr","document"],"modality":"vision","content":"Extract all text from this image. Preserve the original structure:\n\n- Maintain headings, bullet points, and formatting\n- Note tables with their alignment\n- Flag any text that is unclear with [unclear]\n- Output in clean markdown\n\nAdditional task: {{additional_task}}"},
    {"slug":"vision-chart","category":"vision","category_label":"👁️ Vision","title":"Chart & Graph Interpreter","description":"Extract insights from charts and graphs.","tags":["vision","chart","data"],"modality":"vision","content":"Analyze this chart/graph:\n\n1. **Chart type**: What kind of visualization is this?\n2. **Data summary**: Key numbers, trends, and patterns\n3. **Key insight**: The single most important takeaway\n4. **Anomalies**: Anything unexpected in the data\n5. **Recommendation**: What action does this data suggest?\n\nContext: {{context}}"},

    # AGENT
    {"slug":"agent-react","category":"agent","category_label":"🤖 Agent","title":"ReAct Agent Framework","description":"Reason-Act loop for complex multi-step tasks.","tags":["agent","react","reasoning"],"modality":"text","content":"You are an AI agent solving: {{task}}\n\nAvailable tools: {{tools}}\n\nUse this format:\nThought: [your reasoning about what to do]\nAction: [tool name and input]\nObservation: [result]\n... (repeat as needed)\nFinal Answer: [your complete answer]\n\nBegin:"},
    {"slug":"agent-plan-execute","category":"agent","category_label":"🤖 Agent","title":"Plan-Execute Agent","description":"Create a plan then execute each step.","tags":["agent","planning"],"modality":"text","content":"Task: {{task}}\n\nStep 1 — PLAN: Break this into concrete sub-tasks.\nStep 2 — EXECUTE: Work through each sub-task systematically.\nStep 3 — VERIFY: Check your output meets the original task.\n\nResources available: {{resources}}\nConstraints: {{constraints}}"},
    {"slug":"agent-multi-agent","category":"agent","category_label":"🤖 Agent","title":"Multi-Agent Orchestrator","description":"Coordinate multiple specialist agents.","tags":["agent","orchestration","multi-agent"],"modality":"text","content":"You are the orchestrator managing these specialist agents:\n{{agent_descriptions}}\n\nUser task: {{task}}\n\nDecompose the task, assign to appropriate agents, and synthesize results. Show your delegation decisions."},

    # SYSTEM PROMPTS
    {"slug":"sys-expert","category":"system","category_label":"⚙️ System Prompts","title":"Domain Expert Persona","description":"Transform the AI into a domain specialist.","tags":["system","persona","expert"],"modality":"text","content":"You are a world-class expert in {{domain}} with {{years}} years of experience.\n\nYour communication style: {{style}}\nYour primary goal: Help the user with {{primary_goal}}\n\nAlways cite reasoning. Acknowledge uncertainty. Suggest follow-up questions."},
    {"slug":"sys-assistant","category":"system","category_label":"⚙️ System Prompts","title":"Custom Assistant Blueprint","description":"Build a fully-configured AI assistant.","tags":["system","assistant","custom"],"modality":"text","content":"You are {{assistant_name}}, an AI assistant for {{company}}.\n\nPrimary role: {{role}}\nTone: {{tone}}\nAlways do: {{always_do}}\nNever do: {{never_do}}\nEscalate to human when: {{escalation_triggers}}"},

    # CHAIN-OF-THOUGHT
    {"slug":"cot-math","category":"chain_of_thought","category_label":"🔗 Chain of Thought","title":"Mathematical Reasoning","description":"Step-by-step math problem solving.","tags":["cot","math","reasoning"],"modality":"text","content":"Solve this problem step by step:\n\n{{problem}}\n\nShow all work. Check your answer. If you make an assumption, state it explicitly."},
    {"slug":"cot-logic","category":"chain_of_thought","category_label":"🔗 Chain of Thought","title":"Logical Deduction","description":"Systematic logic and deduction framework.","tags":["cot","logic","deduction"],"modality":"text","content":"Apply rigorous logical reasoning to:\n\n{{problem}}\n\nGiven information: {{given}\nWhat we need to find: {{goal}}\n\nStep through the logic. Identify valid inferences. State your conclusion with confidence level."},
    {"slug":"cot-decision","category":"chain_of_thought","category_label":"🔗 Chain of Thought","title":"Decision Analysis Framework","description":"Structured pros/cons and decision making.","tags":["cot","decision","analysis"],"modality":"text","content":"Help me decide: {{decision}\n\nContext: {{context}}\nConstraints: {{constraints}}\nValues that matter most: {{values}}\n\nAnalyze all options. Weight pros and cons. Give a clear recommendation with reasoning."},

    # RAG
    {"slug":"rag-document-qa","category":"rag","category_label":"📚 RAG","title":"Document Q&A","description":"Answer questions grounded in provided documents.","tags":["rag","qa","grounding"],"modality":"text","content":"Use only the following documents to answer the question. If the answer isn't in the documents, say so.\n\n<documents>\n{{documents}}\n</documents>\n\nQuestion: {{question}}\n\nCite which document(s) support your answer."},
    {"slug":"rag-summarize-cite","category":"rag","category_label":"📚 RAG","title":"Summarize with Citations","description":"Summarize documents with source attribution.","tags":["rag","summarization","citations"],"modality":"text","content":"Summarize the following documents:\n\n<documents>\n{{documents}}\n</documents>\n\nRequirements:\n- Group related information\n- Cite source for each claim [Doc X]\n- Highlight contradictions between sources\n- Length: {{length}}"},

    # META-PROMPTS
    {"slug":"meta-improve","category":"meta","category_label":"✨ Meta-Prompts","title":"Prompt Improver","description":"Analyze and enhance any prompt automatically.","tags":["meta","improve","optimize"],"modality":"text","content":"You are a prompt engineering expert. Improve this prompt:\n\n<original_prompt>\n{{prompt}}\n</original_prompt>\n\nTarget model: {{target_model}}\nGoal: {{goal}}\n\nProvide:\n1. Issues with the original\n2. Improved version\n3. Explanation of changes"},
    {"slug":"meta-translate","category":"meta","category_label":"✨ Meta-Prompts","title":"Cross-Model Prompt Translator","description":"Convert a prompt optimized for one model to another.","tags":["meta","translate","models"],"modality":"text","content":"Convert this {{source_model}} prompt to work best with {{target_model}}:\n\n<prompt>\n{{prompt}}\n</prompt>\n\nAccount for {{target_model}}'s strengths and preferred formatting. Keep the intent identical."},
    {"slug":"meta-few-shot","category":"meta","category_label":"✨ Meta-Prompts","title":"Few-Shot Example Generator","description":"Auto-generate few-shot examples for any task.","tags":["meta","few-shot","examples"],"modality":"text","content":"Generate {{n}} diverse few-shot examples for this task:\n\nTask: {{task_description}}\nInput format: {{input_format}}\nOutput format: {{output_format}}\n\nEnsure examples cover edge cases and variety."},
]

CATEGORIES = [
    {"id": "memory",         "label": "🧠 Memory Starters",  "description": "Conversation history, persona persistence, rolling summaries"},
    {"id": "vibe_coding",    "label": "🎨 Vibe Coding",      "description": "AI-powered coding: components, debugging, full-stack planning"},
    {"id": "vision",         "label": "👁️ Vision",           "description": "Image analysis, OCR, chart interpretation"},
    {"id": "agent",          "label": "🤖 Agent",            "description": "ReAct, Plan-Execute, multi-agent orchestration"},
    {"id": "system",         "label": "⚙️ System Prompts",  "description": "Expert personas, custom assistant blueprints"},
    {"id": "chain_of_thought","label": "🔗 Chain of Thought","description": "Math, logic, decision analysis"},
    {"id": "rag",            "label": "📚 RAG",              "description": "Document Q&A, summarization with citations"},
    {"id": "meta",           "label": "✨ Meta-Prompts",     "description": "Improve prompts, translate between models, generate examples"},
]

# ---------------------------------------------------------------------------
# Model DNA — Coaching Tips Per Model
# ---------------------------------------------------------------------------
MODEL_DNA = {
    "gpt-4o": {
        "model": "GPT-4o", "provider": "OpenAI",
        "thinking_style": "Structured and systematic. Excellent at JSON output, function calling, and multi-step reasoning.",
        "strengths": ["JSON mode", "Tool use", "Code generation", "Instruction following"],
        "format_tips": [
            "Use system messages for role/persona definition",
            "Request JSON output explicitly: 'Respond in JSON format: {fields}'",
            "Chain reasoning with 'Step 1:... Step 2:...' structure",
            "Use markdown headers for complex responses",
        ],
        "anti_patterns": [
            "Avoid very long single-paragraph prompts — use bullets",
            "Don't bury the main task at the end — lead with it",
            "Avoid ambiguous pronouns — be explicit about subjects",
        ],
        "best_for": ["API integrations", "Structured data extraction", "Code generation", "Multi-tool agents"],
        "example_opener": "You are a [role]. Your task is to [task]. Output format: [format].",
    },
    "gpt-4o-mini": {
        "model": "GPT-4o Mini", "provider": "OpenAI",
        "thinking_style": "Fast and cost-efficient. Great for classification, extraction, and simple generation.",
        "strengths": ["Speed", "Cost efficiency", "Classification", "Short-form generation"],
        "format_tips": [
            "Keep prompts concise — less than 500 tokens for best results",
            "One clear task per prompt",
            "Use explicit output constraints: 'in 3 sentences or less'",
        ],
        "anti_patterns": [
            "Avoid complex multi-step reasoning tasks",
            "Don't rely on it for nuanced creative writing",
            "Avoid very long context windows",
        ],
        "best_for": ["Classification", "Keyword extraction", "Simple Q&A", "High-volume tasks"],
        "example_opener": "Classify the following as [categories]. Text: [text]. Answer with only the category name.",
    },
    "o3": {
        "model": "o3", "provider": "OpenAI",
        "thinking_style": "Deep internal reasoning before responding. Excels at hard problems requiring extended thinking.",
        "strengths": ["Complex reasoning", "Math", "Science", "Coding challenges"],
        "format_tips": [
            "State the problem clearly — o3 will reason internally",
            "Don't over-specify reasoning steps — let it think",
            "Ask for the answer + brief explanation, not a full trace",
            "Works best on genuinely hard, non-trivial problems",
        ],
        "anti_patterns": [
            "Don't use for simple tasks — overkill and slow",
            "Avoid asking it to 'think step by step' — it does internally",
            "Don't pad with unnecessary context",
        ],
        "best_for": ["PhD-level problems", "Competition math", "Complex code challenges", "Research tasks"],
        "example_opener": "Problem: [problem statement]. Provide the solution and a brief explanation.",
    },
    "claude-opus-4-20250514": {
        "model": "Claude Opus 4", "provider": "Anthropic",
        "thinking_style": "Nuanced, careful, and safety-aware. Loves structured XML tags and explicit thinking prompts.",
        "strengths": ["Long documents", "Nuanced writing", "Complex reasoning", "Instruction adherence"],
        "format_tips": [
            "Use XML tags to structure context: <context>, <task>, <format>",
            "Add 'Think carefully before responding' for complex tasks",
            "Use <thinking> tags to elicit extended reasoning",
            "Claude respects explicit constraints — state them clearly",
            "For long docs, put instructions AFTER the document",
        ],
        "anti_patterns": [
            "Avoid ambiguous instructions — Claude will ask for clarification",
            "Don't use aggressive or manipulative framing",
            "Avoid instructions that conflict with safety guidelines",
        ],
        "best_for": ["Legal/medical document analysis", "Complex writing", "Nuanced reasoning", "Long-context tasks"],
        "example_opener": "<task>\n[Your task here]\n</task>\n\n<context>\n[Background information]\n</context>\n\n<format>\n[Desired output format]\n</format>",
    },
    "claude-sonnet-4-20250514": {
        "model": "Claude Sonnet 4", "provider": "Anthropic",
        "thinking_style": "Balanced intelligence and speed. Best all-around Claude for most production tasks.",
        "strengths": ["Balanced speed/quality", "Code", "Analysis", "Creative writing"],
        "format_tips": [
            "XML tags work well: <document>, <instructions>, <output>",
            "Explicit role assignment: 'You are a senior [role]...'",
            "Request specific output length: 'in approximately X words'",
        ],
        "anti_patterns": [
            "Avoid over-constraining creative tasks",
            "Don't use vague action verbs — be specific",
        ],
        "best_for": ["Production APIs", "Code review", "Writing assistance", "Data analysis"],
        "example_opener": "You are a [role].\n\n<task>\n[Task description]\n</task>",
    },
    "gemini-2.5-pro": {
        "model": "Gemini 2.5 Pro", "provider": "Google",
        "thinking_style": "Multimodal-native, excellent at grounding, web search, and extended context.",
        "strengths": ["1M context window", "Multimodal", "Grounding", "Extended thinking"],
        "format_tips": [
            "Leverage the 1M context — include full documents directly",
            "Use 'thinking' mode for complex reasoning: enable in API",
            "Request grounding for factual queries",
            "Excellent at code across many languages",
            "Great for cross-document analysis",
        ],
        "anti_patterns": [
            "Don't limit context unnecessarily — it handles large inputs well",
            "Avoid expecting ChatGPT-style JSON mode — use explicit format instructions",
        ],
        "best_for": ["Large document analysis", "Multimodal tasks", "Long-context reasoning", "Research"],
        "example_opener": "Analyze the following [content type] and [task]. Focus on [aspects].",
    },
    "gemini-2.5-flash": {
        "model": "Gemini 2.5 Flash", "provider": "Google",
        "thinking_style": "Fast, cheap, and still capable. Great for high-volume production use.",
        "strengths": ["Speed", "Cost", "Multimodal", "Large batches"],
        "format_tips": [
            "Concise prompts yield fast results",
            "Specify output format explicitly",
            "Works well with structured extraction tasks",
        ],
        "anti_patterns": [
            "Not ideal for deep nuanced reasoning",
            "Avoid very complex multi-step chains",
        ],
        "best_for": ["High-volume classification", "Summarization", "Fast extraction", "Image captioning"],
        "example_opener": "Task: [task]. Input: [input]. Output format: [format].",
    },
}

# Fallback DNA for unlisted models
DEFAULT_DNA = {
    "thinking_style": "General-purpose LLM. Clear, specific instructions yield best results.",
    "strengths": ["Text generation", "Q&A", "Summarization", "Instruction following"],
    "format_tips": [
        "Be specific about what you want",
        "Specify output format explicitly",
        "Include examples of desired output",
        "Set role with 'You are a...' opener",
    ],
    "anti_patterns": [
        "Avoid vague instructions",
        "Don't bury the main task",
        "Avoid conflicting instructions",
    ],
    "best_for": ["General tasks"],
    "example_opener": "You are a [role]. [Task]. Output: [format].",
}

# ---------------------------------------------------------------------------
# Prompt Intelligence Engine (PIE) — client-side analysis logic in Python
# ---------------------------------------------------------------------------

def analyze_prompt(content: str, model_id: Optional[str] = None) -> dict:
    """Analyze a prompt and return scores + actionable suggestions."""
    issues = []
    tips = []
    score_components = {}

    words = content.split()
    word_count = len(words)
    char_count = len(content)
    sentence_count = max(1, content.count('.') + content.count('!') + content.count('?'))
    has_variables = bool(re.search(r'\{\{[^}]+\}\}', content))
    variable_names = re.findall(r'\{\{([^}]+)\}\}', content)

    # ── Clarity Score ──────────────────────────────────────────────────────
    clarity = 70
    if word_count < 10:
        clarity -= 30
        issues.append({"type": "error", "text": "Prompt is too short — add more context and detail."})
    elif word_count < 25:
        clarity -= 10
        issues.append({"type": "warning", "text": "Prompt is brief — consider adding more context."})

    vague_words = ["something", "stuff", "things", "maybe", "kind of", "sort of", "etc", "and so on"]
    vague_found = [w for w in vague_words if w in content.lower()]
    if vague_found:
        clarity -= 5 * len(vague_found)
        issues.append({"type": "warning", "text": f"Vague language detected: {', '.join(vague_found)}. Be specific."})

    action_verbs = ["analyze", "write", "generate", "summarize", "classify", "extract", "translate",
                    "create", "explain", "list", "compare", "evaluate", "identify", "describe", "convert"]
    has_action = any(v in content.lower() for v in action_verbs)
    if not has_action:
        clarity -= 15
        issues.append({"type": "warning", "text": "No clear action verb found. Start with: Analyze, Write, Generate, Summarize, etc."})
    else:
        clarity += 5

    score_components["clarity"] = max(0, min(100, clarity))

    # ── Specificity Score ─────────────────────────────────────────────────
    specificity = 60
    if has_variables:
        specificity += 15
        tips.append({"type": "success", "text": f"✓ Uses {len(variable_names)} variable(s): {', '.join(variable_names)}"})
    if any(kw in content.lower() for kw in ["format:", "output:", "json", "markdown", "bullet", "numbered", "table"]):
        specificity += 15
        tips.append({"type": "success", "text": "✓ Output format is specified."})
    else:
        specificity -= 10
        issues.append({"type": "tip", "text": "Specify output format: 'Output as JSON', 'Use markdown', 'Return a numbered list', etc."})
    if any(kw in content.lower() for kw in ["example:", "for example", "e.g.", "such as", "input:", "output:"]):
        specificity += 10
    score_components["specificity"] = max(0, min(100, specificity))

    # ── Structure Score ───────────────────────────────────────────────────
    structure = 50
    if any(tag in content for tag in ["<task>", "<context>", "<format>", "<document>", "<instructions>"]):
        structure += 30
        tips.append({"type": "success", "text": "✓ XML tags used — excellent for Claude models."})
    if '\n' in content:
        structure += 10
    if any(kw in content for kw in ["1.", "2.", "3.", "•", "-", "*"]):
        structure += 10
    if word_count > 50 and '\n' not in content:
        structure -= 20
        issues.append({"type": "warning", "text": "Long prompt with no line breaks — use newlines and sections for clarity."})
    score_components["structure"] = max(0, min(100, structure))

    # ── Token Efficiency Score ────────────────────────────────────────────
    efficiency = 100
    filler_phrases = ["please note that", "it is important to", "as you know", "needless to say",
                      "it goes without saying", "in other words", "to be honest"]
    fillers_found = [f for f in filler_phrases if f in content.lower()]
    if fillers_found:
        efficiency -= 10 * len(fillers_found)
        issues.append({"type": "tip", "text": f"Filler phrases detected: '{fillers_found[0]}'. Remove for token efficiency."})
    if word_count > 500:
        efficiency -= 15
        issues.append({"type": "info", "text": f"Prompt is {word_count} words. Consider if all context is necessary."})
    score_components["efficiency"] = max(0, min(100, efficiency))

    # ── Model Compatibility Score ─────────────────────────────────────────
    compatibility = 75
    compat_notes = []
    if model_id:
        if "claude" in model_id:
            if "<task>" in content or "<context>" in content:
                compatibility += 20
                compat_notes.append("✓ XML tags — Claude loves this structure.")
            else:
                compatibility -= 10
                compat_notes.append("💡 Add XML tags <task>, <context> for Claude.")
        elif "gpt" in model_id or "o3" in model_id:
            if "json" in content.lower() or "JSON" in content:
                compatibility += 15
                compat_notes.append("✓ JSON output spec — great for GPT models.")
            if "step" in content.lower():
                compatibility += 10
                compat_notes.append("✓ Step-by-step instruction — works well with GPT.")
        elif "gemini" in model_id:
            if word_count > 200:
                compatibility += 10
                compat_notes.append("✓ Rich context — Gemini handles large inputs well.")
    score_components["model_compatibility"] = max(0, min(100, compatibility))
    if compat_notes:
        for note in compat_notes:
            tips.append({"type": "info", "text": note})

    # ── Overall Score ─────────────────────────────────────────────────────
    overall = int(
        score_components["clarity"] * 0.30 +
        score_components["specificity"] * 0.25 +
        score_components["structure"] * 0.20 +
        score_components["efficiency"] * 0.15 +
        score_components["model_compatibility"] * 0.10
    )

    # Grade
    if overall >= 85:
        grade, grade_label = "A", "Excellent"
    elif overall >= 70:
        grade, grade_label = "B", "Good"
    elif overall >= 55:
        grade, grade_label = "C", "Needs Work"
    else:
        grade, grade_label = "D", "Poor"

    return {
        "overall_score": overall,
        "grade": grade,
        "grade_label": grade_label,
        "scores": score_components,
        "issues": issues,
        "tips": tips,
        "stats": {
            "word_count": word_count,
            "char_count": char_count,
            "sentence_count": sentence_count,
            "variable_count": len(variable_names),
            "variables": variable_names,
            "has_xml_tags": "<task>" in content or "<context>" in content,
            "has_output_format": any(kw in content.lower() for kw in ["format:", "output:", "json", "markdown"]),
        }
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/categories")
def get_categories():
    return CATEGORIES


@router.get("/prompts")
def get_starter_prompts(category: Optional[str] = Query(None)):
    if category:
        return [p for p in STARTER_PROMPTS if p["category"] == category]
    return STARTER_PROMPTS


@router.get("/prompts/{slug}")
def get_starter_prompt(slug: str):
    for p in STARTER_PROMPTS:
        if p["slug"] == slug:
            return p
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Prompt not found")


@router.post("/analyze")
def analyze(body: dict):
    content = body.get("content", "")
    model_id = body.get("model_id")
    return analyze_prompt(content, model_id)


@router.get("/model-dna/{model_id:path}")
def get_model_dna(model_id: str):
    dna = MODEL_DNA.get(model_id, DEFAULT_DNA)
    return {"model_id": model_id, **dna}
