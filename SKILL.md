---
name: multi-llm-consensus
description: Run a reviewed multi-provider LLM consensus workflow for complex prompt generation, phenomenon analysis, research design, coding or project planning, and requests triggered by "群智", "multi-llm consensus", "multi-llm", "consensus", "问多个模型", "多模型综合", or "让几个模型一起想". Discovers configured APIs, asks one best model per provider, compares answers, and synthesizes a final response.
---

# Multi-LLM Consensus

Use this skill when the user asks for 群智 / multi-llm consensus, or when they explicitly want several configured models to think through the same complex task.

## Core Workflow

1. Capture the user's original task. If the user wrote `群智：<任务>` or `multi-llm consensus: <task>`, remove only the trigger prefix and preserve the rest verbatim.
2. If provider setup is unclear, read `references/providers.md`.
3. Run `scripts/multi_llm_consensus.py` from this skill directory. Prefer stdin or a task file for multiline tasks to avoid shell quoting issues.
4. If the script reports no configured provider, tell the user which environment variables or config files are needed and stop.
5. Read every successful model answer. Do not simply vote, paste, average, or concatenate.
6. Review each successful answer for:
   - key points
   - unique contribution
   - suspicious or weak points
   - adoptable content
7. Produce the final answer in this structure unless the user requested another format:
   - 简短结论
   - 本次参与模型: list every successful provider/model and every failed or skipped provider.
   - 各模型输出评审: for each successful model, report key points, strengths, weaknesses, and adoptable content.
   - 综合后的最终建议/答案
   - 分歧点与我的判断
   - 仍需用户确认的问题

## Script Usage

Run a short task:

```bash
python scripts/multi_llm_consensus.py --task "Design a research plan for ..." --format markdown
```

Run a multiline task through stdin:

```bash
python scripts/multi_llm_consensus.py --stdin --format markdown
```

Inspect discovered providers without making model calls:

```bash
python scripts/multi_llm_consensus.py --task "test" --dry-run --format markdown
```

Validate the skill without real API keys:

```bash
python scripts/multi_llm_consensus.py --task "Plan a small note-taking app" --mock --format markdown
```

The script prints structured results containing `provider`, `model`, `status`, `response`, `error`, and `latency`. Failed providers must be mentioned in the final answer, but failures from one provider must not block synthesis from the others.

## Provider Selection

The script discovers API keys from environment variables and `.env`, then merges provider/model settings from `llm-providers.json`, `config/llm-providers.json`, or an explicit `--config` path. It also auto-detects CC-SWITCH Claude-compatible providers from `~/.cc-switch/cc-switch.db` when present. It selects at most one model per provider.

Provider priorities are configurable; do not edit API keys into this skill. Use `assets/llm-providers.example.json` as a starting point and keep local secrets in environment variables or `.env`.

## Synthesis Rules

- Treat model outputs as advisory drafts, not authoritative sources.
- Prefer reasoning quality, specificity, feasibility, and fit to the user's task over majority agreement.
- When models disagree, state the disagreement and make an explicit judgment.
- When all models share the same unsupported assumption, flag it instead of amplifying it.
- Keep the user's original constraints and context above model suggestions.
- If the task includes private, regulated, or proprietary data, warn before sending it to external providers unless the user already consented.
- Do not omit the per-model review. Every successful model must get an explicit strengths/weaknesses/adoptable-content assessment, even if the assessment is brief.

## Resources

- `scripts/multi_llm_consensus.py`: provider discovery, model selection, concurrent API calls, structured output.
- `references/providers.md`: installation paths, API key setup, provider registry rules, and extension notes.
- `references/cc-switch-models.md`: local CC-SWITCH model-id snapshot and priority reference.
- `assets/llm-providers.example.json`: editable provider registry and model priority template.
