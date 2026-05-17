# multi-llm-consensus

Portable multi-LLM consensus skill for OpenClaw, Codex, and Claude Code.

Use it when you want an agent to send the same complex task to several configured LLM providers, review the answers, and produce one synthesized response instead of a simple vote or pasted bundle.

## Triggers

Primary trigger:

```text
群智
```

Other trigger phrases:

```text
multi-llm consensus
multi-llm
consensus
问多个模型
多模型综合
让几个模型一起想
```

Example:

```text
群智：帮我设计一个可执行的研究计划，并指出主要风险
```

## What It Does

- Discovers configured LLM provider API keys from environment variables or local config.
- Selects at most one model per provider.
- Sends a unified prompt to all available providers concurrently.
- Saves structured per-model results: provider, model, status, response, error, latency.
- Requires the agent to review each model's strengths, weaknesses, unique ideas, and adoptable content.
- Produces a final multi-model synthesis with explicit disagreement handling.

Supported provider clients:

- OpenAI Responses API
- Anthropic Messages API
- Gemini `generateContent`
- OpenAI-compatible chat completions for DeepSeek, MiniMax, and Qwen/DashScope

## Install

Use the same folder structure in all supported agents:

```text
multi-llm-consensus/
  SKILL.md
  scripts/
  references/
  assets/
  agents/
```

OpenClaw:

```text
~/.openclaw/skills/multi-llm-consensus/
```

Codex:

```text
~/.codex/skills/multi-llm-consensus/
```

Claude Code:

```text
~/.claude/skills/multi-llm-consensus/
```

After installing into Codex, restart Codex so it can discover the new skill.

## Configure API Keys

Set one or more environment variables:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
DEEPSEEK_API_KEY
GEMINI_API_KEY
MINIMAX_API_KEY
QWEN_API_KEY
DASHSCOPE_API_KEY
```

Optional model override variables:

```text
OPENAI_MODEL
ANTHROPIC_MODEL
DEEPSEEK_MODEL
GEMINI_MODEL
MINIMAX_MODEL
QWEN_MODEL
```

Do not commit real API keys. The included `.gitignore` excludes `.env`, `.env.*`, `llm-providers.json`, and `config/llm-providers.json`.

## Configure Providers And Model Priority

Copy the template if you want to customize providers or model priority:

```text
assets/llm-providers.example.json
```

The script loads registry overrides in this order:

1. built-in defaults
2. `llm-providers.json`
3. `config/llm-providers.json`
4. `--config <path>`
5. `LLM_PROVIDERS_CONFIG`

Each provider contributes at most one model. Selection order:

1. provider-specific model environment variable
2. explicit `model` in registry config
3. first configured `model_priority` entry found from the provider's model list
4. first configured `model_priority` entry as fallback

## Script Usage

Run a short task:

```bash
python scripts/multi_llm_consensus.py --task "Design a research plan for ..." --format markdown
```

Run a multiline task through stdin:

```bash
python scripts/multi_llm_consensus.py --stdin --format markdown
```

Preview provider discovery without model calls:

```bash
python scripts/multi_llm_consensus.py --task "test" --dry-run --format markdown
```

Validate behavior without real API keys:

```bash
python scripts/multi_llm_consensus.py --task "Plan a small note-taking app" --mock --format markdown
```

## Expected Final Agent Output

The skill asks the agent to synthesize, not paste. The final answer should use:

```text
简短结论
本次参与模型
各模型输出评审
综合后的最终建议/答案
分歧点与我的判断
仍需用户确认的问题
```

For each successful model, include:

```text
模型: <provider>/<model>
关键观点:
优点:
不足或风险:
可采纳内容:
```

## Security Notes

- This repo stores only environment variable names and example registry metadata.
- Do not put real API keys in `SKILL.md`, `README.md`, or provider JSON committed to git.
- Keep real keys in environment variables, a local `.env`, or a private secret manager.
- Failed providers do not block the rest of the consensus run.
- If the task contains private or regulated data, confirm that sending it to external providers is acceptable before invoking the skill.

## Repository Contents

- `SKILL.md`: portable agent instructions and trigger behavior.
- `scripts/multi_llm_consensus.py`: provider discovery, concurrent API calls, structured results.
- `references/providers.md`: installation paths, provider config, and extension notes.
- `assets/llm-providers.example.json`: editable provider registry template.
- `agents/openai.yaml`: optional Codex UI metadata.
