# Provider Setup And Installation

## Installation Paths

Use the same `multi-llm-consensus/` directory in all three agents.

OpenClaw:

```text
~/.openclaw/skills/multi-llm-consensus/SKILL.md
<workspace>/skills/multi-llm-consensus/SKILL.md
```

Codex:

```text
~/.codex/skills/multi-llm-consensus/SKILL.md
```

Claude Code:

```text
~/.claude/skills/multi-llm-consensus/SKILL.md
<project>/.claude/skills/multi-llm-consensus/SKILL.md
```

The portable core is the root `SKILL.md` plus `scripts/`, `references/`, and `assets/`. Codex can also read `agents/openai.yaml` as optional UI metadata. OpenClaw and Claude Code can ignore it.

## API Key Discovery

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

The script also reads `.env` from the current working directory. Environment variables already set in the process take precedence over `.env` values.

## Registry Files

The script loads provider registry overrides in this order:

1. built-in defaults
2. `llm-providers.json`
3. `config/llm-providers.json`
4. path passed with `--config`
5. path in `LLM_PROVIDERS_CONFIG`

Use `assets/llm-providers.example.json` as the template. Keep API keys out of JSON; store key names such as `OPENAI_API_KEY` in `api_key_env`.

## Model Selection

Each provider contributes at most one model. Selection order:

1. provider-specific model environment variable, such as `OPENAI_MODEL`
2. explicit `model` in registry config
3. first configured `model_priority` entry found in the provider's `/models` response
4. first configured `model_priority` entry when model listing is unavailable

Update `model_priority` as providers release or deprecate models. The defaults are intentionally easy to edit and are not treated as permanent truth.

## Supported Provider Clients

`openai_responses`
: OpenAI Responses API, default base URL `https://api.openai.com/v1`.

`anthropic_messages`
: Anthropic Messages API, default base URL `https://api.anthropic.com/v1`.

`gemini_generate`
: Gemini `generateContent` API, default base URL `https://generativelanguage.googleapis.com/v1beta`.

`openai_chat_completions`
: OpenAI-compatible chat completions. Used by DeepSeek, MiniMax, and Qwen/DashScope by default.

## Extending Providers

Add a provider entry under `providers`:

```json
{
  "providers": {
    "my-provider": {
      "enabled": true,
      "client": "openai_chat_completions",
      "base_url": "https://example.com/v1",
      "api_key_env": "MY_PROVIDER_API_KEY",
      "model_env": "MY_PROVIDER_MODEL",
      "model_priority": ["best-model", "fallback-model"],
      "discover_models": true
    }
  }
}
```

If the provider is not OpenAI-compatible, add a new client implementation in `scripts/multi_llm_consensus.py` and keep its request/parse logic isolated.

## Expected Agent Output

After running the script, the agent should synthesize, not paste. Use:

```text
简短结论
本次参与模型
各模型输出评审
综合后的最终建议/答案
分歧点与我的判断
仍需用户确认的问题
```

Mention successful and failed providers explicitly. In `各模型输出评审`, include one entry per successful model with:

```text
模型: <provider>/<model>
关键观点:
优点:
不足或风险:
可采纳内容:
```
