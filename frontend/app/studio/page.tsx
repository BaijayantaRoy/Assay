"use client";
import React, { useState } from "react";
import {
  Wand2, Plus, Trash2, Copy, Check,
  User, FileText, Target, AlignLeft, ShieldOff, BookOpen, Brain,
  Eye, MessageSquare, ChevronDown, ChevronUp, Code2, Save
} from "lucide-react";
import { useToast } from "@/components/toast-provider";
import { createPrompt } from "@/lib/v1";

// ── Block Types ─────────────────────────────────────────────────────────────
type BlockType = "role" | "context" | "task" | "format" | "constraints" | "examples" | "cot" | "vision" | "memory" | "custom";

interface Block {
  id: string;
  type: BlockType;
  content: string;
  collapsed: boolean;
}

const BLOCK_META: Record<BlockType, { label: string; icon: React.ReactNode; color: string; placeholder: string; tip: string }> = {
  role:        { label: "Role / Persona",     icon: <User className="w-4 h-4" />,         color: "from-violet-500 to-purple-600",  placeholder: "You are a senior software engineer with 10 years of experience in...", tip: "Define WHO the AI should be. A specific persona dramatically improves output quality." },
  context:     { label: "Context",            icon: <FileText className="w-4 h-4" />,      color: "from-blue-500 to-cyan-600",      placeholder: "Background information the AI needs to know:\n- The user is...\n- The codebase uses...", tip: "Provide relevant background. Only include context that changes the answer." },
  task:        { label: "Task",               icon: <Target className="w-4 h-4" />,        color: "from-emerald-500 to-green-600",  placeholder: "Your task is to analyze {{input}} and...", tip: "The core instruction. Be specific and use action verbs: Analyze, Generate, Summarize..." },
  format:      { label: "Output Format",      icon: <AlignLeft className="w-4 h-4" />,    color: "from-amber-500 to-orange-600",   placeholder: "Respond in the following format:\n{\n  \"result\": \"\",\n  \"reasoning\": \"\"\n}", tip: "Specify EXACTLY how you want the output. JSON, markdown, bullet list, table..." },
  constraints: { label: "Constraints",        icon: <ShieldOff className="w-4 h-4" />,    color: "from-red-500 to-rose-600",       placeholder: "Important constraints:\n- Do NOT include...\n- Keep response under 500 words\n- Always cite sources", tip: "What the AI must NOT do. Constraints prevent the most common failure modes." },
  examples:    { label: "Few-Shot Examples",  icon: <BookOpen className="w-4 h-4" />,     color: "from-pink-500 to-fuchsia-600",   placeholder: "Input: 'The product is great'\nOutput: Positive\n\nInput: 'Terrible experience'\nOutput: Negative", tip: "2-3 examples teach better than 100 words of instruction. Show, don't tell." },
  cot:         { label: "Chain of Thought",   icon: <Brain className="w-4 h-4" />,        color: "from-indigo-500 to-blue-600",    placeholder: "Think through this step by step:\n1. First, consider...\n2. Then evaluate...\n3. Finally, conclude...", tip: "Triggers extended reasoning. Crucial for math, logic, and complex decisions." },
  vision:      { label: "Vision Instructions",icon: <Eye className="w-4 h-4" />,         color: "from-teal-500 to-cyan-600",      placeholder: "Analyze the provided image:\n- Focus on: {{focus_area}}\n- Detail level: {{detail_level}}\n- Style: descriptive", tip: "For multimodal prompts. Specify what to look for, detail level, and output format." },
  memory:      { label: "Memory / History",   icon: <MessageSquare className="w-4 h-4" />, color: "from-slate-500 to-gray-600",   placeholder: "<conversation_history>\n{{conversation_history}}\n</conversation_history>", tip: "Inject past conversation or session context. Use {{variable}} for dynamic content." },
  custom:      { label: "Custom Block",       icon: <Code2 className="w-4 h-4" />,        color: "from-stone-500 to-neutral-600", placeholder: "Add any custom instruction or content here...", tip: "Freeform block for any content that doesn't fit the standard categories." },
};

const BLOCK_ORDER: BlockType[] = ["role", "context", "memory", "task", "cot", "examples", "constraints", "format", "vision", "custom"];

// Vibe Coding Presets
const VIBE_PRESETS = [
  { id: "glassmorphism", label: "✨ Glassmorphism", desc: "Frosted glass, blurs, soft gradients" },
  { id: "dark-brutal",   label: "⬛ Dark Brutalist", desc: "Bold borders, high contrast, minimal" },
  { id: "neon-cyber",    label: "🌆 Neon Cyberpunk", desc: "Neon accents, dark backgrounds, glow" },
  { id: "minimal-clean", label: "🤍 Minimal Clean",  desc: "White space, light colors, elegant" },
  { id: "corporate",     label: "💼 Corporate",      desc: "Professional, muted, trust-building" },
  { id: "retro-pixel",   label: "👾 Retro Pixel",    desc: "8-bit style, pixel fonts, nostalgia" },
];
const TECH_STACKS = ["React + Tailwind", "Next.js", "Vue 3", "SvelteKit", "FastAPI", "Django", "Express.js", "Flutter"];

function uid() { return Math.random().toString(36).slice(2, 9); }

function assemblePrompt(blocks: Block[]): string {
  return blocks
    .filter(b => b.content.trim())
    .map(b => {
      const meta = BLOCK_META[b.type];
      return `# ${meta.label}\n${b.content}`;
    })
    .join("\n\n");
}

export default function StudioPage() {
  const { toast } = useToast();
  const [blocks, setBlocks] = useState<Block[]>([
    { id: uid(), type: "role", content: "", collapsed: false },
    { id: uid(), type: "task", content: "", collapsed: false },
    { id: uid(), type: "format", content: "", collapsed: false },
  ]);
  const [mode, setMode] = useState<"anatomy" | "vibe">("anatomy");
  const [vibePreset, setVibePreset] = useState("glassmorphism");
  const [vibeStack, setVibeStack] = useState("React + Tailwind");
  const [vibeComponent, setVibeComponent] = useState("");
  const [copied, setCopied] = useState(false);
  const [showAddMenu, setShowAddMenu] = useState(false);
  const [artifactId, setArtifactId] = useState("drafts/new-prompt");
  const [saving, setSaving] = useState(false);

  const addBlock = (type: BlockType) => {
    setBlocks(prev => [...prev, { id: uid(), type, content: "", collapsed: false }]);
    setShowAddMenu(false);
  };

  const removeBlock = (id: string) => setBlocks(prev => prev.filter(b => b.id !== id));

  const updateContent = (id: string, content: string) =>
    setBlocks(prev => prev.map(b => b.id === id ? { ...b, content } : b));

  const toggleCollapse = (id: string) =>
    setBlocks(prev => prev.map(b => b.id === id ? { ...b, collapsed: !b.collapsed } : b));

  const moveBlock = (from: number, to: number) => {
    if (to < 0 || to >= blocks.length) return;
    const arr = [...blocks];
    const [item] = arr.splice(from, 1);
    arr.splice(to, 0, item);
    setBlocks(arr);
  };

  const assembled = assemblePrompt(blocks);

  function buildVibePrompt() {
    if (!vibeComponent) return "";
    const preset = VIBE_PRESETS.find(p => p.id === vibePreset);
    return `You are a senior frontend developer specializing in stunning UI design.

# Task
Build a ${vibeStack} component for: ${vibeComponent}

# Design Vibe: ${preset?.label}
Style: ${preset?.desc}

# Requirements
- Make it visually stunning — production-quality
- Smooth hover animations and micro-interactions
- Fully responsive (mobile-first)
- Accessible (ARIA labels, keyboard navigation)
- Clean, commented code

# Output
Complete, copy-paste-ready code. Include all imports. Add a usage example at the end.`;
  }

  function copyAssembled() {
    const content = mode === "anatomy" ? assembled : buildVibePrompt();
    navigator.clipboard.writeText(content);
    setCopied(true);
    toast("Prompt copied!", "success");
    setTimeout(() => setCopied(false), 2000);
  }

  async function savePromptFile() {
    const content = mode === "anatomy" ? assembled : buildVibePrompt();
    if (!content.trim()) return toast("Add prompt content before saving", "error");
    if (!artifactId.trim()) return toast("Enter a PromptFile id", "error");
    setSaving(true);
    try {
      await createPrompt({
        id: artifactId.trim(),
        name: artifactId.trim().split("/").at(-1) || artifactId.trim(),
        description: "Draft created in Prompt Studio; add eval cases before promotion.",
        body: content,
        status: "draft",
        tags: ["studio"],
        commit_message: "Create draft from Prompt Studio",
      });
      toast(`Saved ${artifactId} as an unverified draft`, "success");
    } catch (error) {
      toast(error instanceof Error ? error.message : "Failed to save draft", "error");
    } finally {
      setSaving(false);
    }
  }

  const usedTypes = new Set(blocks.map(b => b.type));
  const availableToAdd = BLOCK_ORDER.filter(t => !usedTypes.has(t) || t === "examples" || t === "custom");

  return (
    <div className="flex h-full min-w-0 flex-col xl:flex-row">
      {/* Left: Builder */}
      <div className="min-w-0 flex-1 flex flex-col border-b xl:border-b-0 xl:border-r border-border">
        {/* Header */}
        <div className="p-5 border-b border-border">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-fuchsia-500 to-violet-600 flex items-center justify-center">
              <Wand2 className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-foreground">Prompt Studio</h1>
              <p className="text-sm text-muted-foreground">Visual Anatomy Builder + Vibe Coding Studio</p>
            </div>
          </div>
          {/* Mode toggle */}
          <div className="flex gap-2 p-1 bg-muted rounded-xl">
            {[["anatomy","🏗️ Anatomy Builder"],["vibe","🎨 Vibe Coding Studio"]].map(([m,label]) => (
              <button key={m} onClick={() => setMode(m as "anatomy"|"vibe")}
                className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${mode === m ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Anatomy Builder */}
        {mode === "anatomy" && (
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {blocks.map((block, idx) => {
              const meta = BLOCK_META[block.type];
              return (
                <div key={block.id} className="rounded-xl border border-border bg-card overflow-hidden group">
                  {/* Block header */}
                  <div className={`flex items-center gap-3 px-4 py-3 bg-gradient-to-r ${meta.color} bg-opacity-10`}>
                    <div className="text-white opacity-80">{meta.icon}</div>
                    <span className="font-semibold text-sm text-white">{meta.label}</span>
                    <div className="flex-1" />
                    <button aria-label={`Move ${meta.label} up`} onClick={() => moveBlock(idx, idx-1)} className="text-white hover:text-white p-1 disabled:opacity-40" disabled={idx === 0}><ChevronUp className="w-3.5 h-3.5" /></button>
                    <button aria-label={`Move ${meta.label} down`} onClick={() => moveBlock(idx, idx+1)} className="text-white hover:text-white p-1 disabled:opacity-40" disabled={idx === blocks.length-1}><ChevronDown className="w-3.5 h-3.5" /></button>
                    <button aria-label={`${block.collapsed ? "Expand" : "Collapse"} ${meta.label}`} onClick={() => toggleCollapse(block.id)} className="text-white hover:text-white p-1">
                      {block.collapsed ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
                    </button>
                    <button aria-label={`Remove ${meta.label}`} onClick={() => removeBlock(block.id)} className="text-white hover:text-red-100 p-1"><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                  {!block.collapsed && (
                    <div className="p-3 space-y-2">
                      <p className="text-xs text-muted-foreground italic">{meta.tip}</p>
                      <textarea
                        className="w-full min-h-[90px] bg-background border border-border rounded-lg p-3 text-sm font-mono text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 resize-none"
                        placeholder={meta.placeholder}
                        value={block.content}
                        onChange={e => updateContent(block.id, e.target.value)}
                      />
                    </div>
                  )}
                </div>
              );
            })}
            {/* Add block */}
            <div className="relative">
              <button onClick={() => setShowAddMenu(!showAddMenu)}
                className="w-full flex items-center justify-center gap-2 py-3 rounded-xl border-2 border-dashed border-border hover:border-primary/50 text-muted-foreground hover:text-primary transition-all text-sm">
                <Plus className="w-4 h-4" /> Add Block
              </button>
              {showAddMenu && (
                <div className="absolute top-full left-0 right-0 mt-2 bg-popover border border-border rounded-xl shadow-xl z-10 p-2 grid grid-cols-2 gap-1">
                  {availableToAdd.map(type => {
                    const meta = BLOCK_META[type];
                    return (
                      <button key={type} onClick={() => addBlock(type)}
                        className="flex items-center gap-2 p-2.5 rounded-lg hover:bg-muted text-sm text-left transition-colors">
                        <span className="text-primary">{meta.icon}</span>
                        <span className="text-foreground">{meta.label}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Vibe Coding Studio */}
        {mode === "vibe" && (
          <div className="flex-1 overflow-y-auto p-5 space-y-5">
            <div>
              <label className="block text-sm font-semibold text-foreground mb-2">What do you want to build?</label>
              <textarea
                className="w-full h-24 bg-background border border-border rounded-xl p-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 resize-none"
                placeholder="e.g. A pricing card with 3 tiers, hover animations, and a featured plan..."
                value={vibeComponent}
                onChange={e => setVibeComponent(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-semibold text-foreground mb-2">Tech Stack</label>
              <div className="flex flex-wrap gap-2">
                {TECH_STACKS.map(s => (
                  <button key={s} onClick={() => setVibeStack(s)}
                    className={`px-3 py-1.5 rounded-lg text-sm border transition-all ${vibeStack === s ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:border-primary/50"}`}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-sm font-semibold text-foreground mb-2">Design Vibe</label>
              <div className="grid grid-cols-2 gap-2">
                {VIBE_PRESETS.map(p => (
                  <button key={p.id} onClick={() => setVibePreset(p.id)}
                    className={`p-3 rounded-xl border text-left transition-all ${vibePreset === p.id ? "border-primary bg-primary/5" : "border-border hover:border-primary/40"}`}>
                    <div className="font-semibold text-sm text-foreground">{p.label}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">{p.desc}</div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Right: Preview */}
      <div className="w-full xl:w-[420px] flex flex-col bg-background">
        <div className="p-4 border-b border-border space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-semibold text-sm text-foreground">Assembled Prompt Preview</h2>
            <button onClick={copyAssembled}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium hover:bg-muted transition-all">
              {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              {copied ? "Copied!" : "Copy"}
            </button>
          </div>
          <div className="flex gap-2">
            <input
              aria-label="PromptFile id"
              value={artifactId}
              onChange={event => setArtifactId(event.target.value)}
              className="min-w-0 flex-1 rounded-lg border bg-background px-3 py-1.5 font-mono text-xs"
              placeholder="namespace/prompt-id"
            />
            <button onClick={savePromptFile} disabled={saving}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium disabled:opacity-50">
              <Save className="w-3.5 h-3.5" /> {saving ? "Saving…" : "Save draft"}
            </button>
          </div>
          <p className="text-[10px] text-muted-foreground">Saved drafts have no eval cases yet and remain explicitly unverified.</p>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {(() => {
            const preview = mode === "anatomy" ? assembled : buildVibePrompt();
            return preview ? (
              <pre className="text-xs font-mono text-foreground whitespace-pre-wrap leading-relaxed">{preview}</pre>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center text-muted-foreground">
                <Wand2 className="w-10 h-10 mb-3 opacity-20" />
                <p className="text-sm">Fill in the blocks on the left</p>
                <p className="text-xs mt-1">Your assembled prompt will appear here</p>
              </div>
            );
          })()}
        </div>
        {/* Stats bar */}
        <div className="p-3 border-t border-border bg-muted/30 flex gap-4 text-xs text-muted-foreground">
          {(() => {
            const t = mode === "anatomy" ? assembled : buildVibePrompt();
            const words = t.trim() ? t.split(/\s+/).length : 0;
            const approxTokens = Math.ceil(words * 1.3);
            return (
              <>
                <span>{words} words</span>
                <span>~{approxTokens} tokens</span>
                <span>{blocks.filter(b=>b.content.trim()).length} blocks filled</span>
              </>
            );
          })()}
        </div>
      </div>
    </div>
  );
}
