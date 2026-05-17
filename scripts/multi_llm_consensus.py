#!/usr/bin/env python3
"""Query multiple configured LLM providers and emit structured results.

This script intentionally uses only the Python standard library so it can run
inside OpenClaw, Codex, Claude Code, or a plain terminal.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


DEFAULT_CONFIG: Dict[str, Any] = {
    "defaults": {
        "timeout_seconds": 60,
        "retries": 1,
        "max_output_tokens": 1400,
        "temperature": 0.2,
        "concurrency": 6,
    },
    "providers": {
        "openai": {
            "enabled": True,
            "client": "openai_responses",
            "base_url": "https://api.openai.com/v1",
            "api_key_env": "OPENAI_API_KEY",
            "model_env": "OPENAI_MODEL",
            "model_priority": [
                "gpt-5.4",
                "gpt-5.3-codex",
                "gpt-5.2",
                "gpt-5.1",
                "gpt-5",
                "gpt-5.4-mini",
                "gpt-5.2-codex",
                "gpt-5.1-codex",
                "gpt-5-codex",
                "gpt-4.1",
                "o3",
                "o4-mini",
            ],
            "discover_models": True,
        },
        "anthropic": {
            "enabled": True,
            "client": "anthropic_messages",
            "base_url": "https://api.anthropic.com/v1",
            "api_key_env": "ANTHROPIC_API_KEY",
            "model_env": "ANTHROPIC_MODEL",
            "model_priority": [
                "claude-opus-4-7",
                "claude-opus-4-6",
                "claude-sonnet-4-6",
                "claude-opus-4-5-20251101",
                "claude-sonnet-4-5-20250929",
                "claude-haiku-4-5",
                "claude-opus-4-1-20250805",
                "claude-opus-4-20250514",
                "claude-sonnet-4-20250514",
            ],
            "discover_models": True,
        },
        "gemini": {
            "enabled": True,
            "client": "gemini_generate",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "api_key_env": "GEMINI_API_KEY",
            "model_env": "GEMINI_MODEL",
            "model_priority": [
                "gemini-3.1-pro-preview",
                "gemini-3-pro-preview",
                "gemini-2.5-pro",
                "gemini-3-flash-preview",
                "gemini-3.1-flash-lite-preview",
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
                "gemini-2.0-flash",
            ],
            "discover_models": True,
        },
        "deepseek": {
            "enabled": True,
            "client": "openai_chat_completions",
            "base_url": "https://api.deepseek.com/v1",
            "api_key_env": "DEEPSEEK_API_KEY",
            "model_env": "DEEPSEEK_MODEL",
            "model_priority": [
                "deepseek-v3.2",
                "deepseek-v3.1",
                "deepseek-v3",
                "deepseek-reasoner",
                "deepseek-chat",
            ],
            "discover_models": True,
        },
        "minimax": {
            "enabled": True,
            "client": "openai_chat_completions",
            "base_url": "https://api.minimax.io/v1",
            "api_key_env": "MINIMAX_API_KEY",
            "model_env": "MINIMAX_MODEL",
            "model_priority": [
                "MiniMax-M2.7",
                "minimax-m2.7",
                "MiniMax-M2.7-highspeed",
                "minimax-m2.7-highspeed",
                "MiniMax-M2.5",
                "minimax-m2.5",
                "MiniMax-M2.5-highspeed",
                "minimax-m2.5-lightning",
                "MiniMax-M2.1",
                "minimax-m2.1",
                "minimax-m2.1-lightning",
                "MiniMax-M2",
                "minimax-m2",
            ],
            "discover_models": True,
        },
        "qwen": {
            "enabled": True,
            "client": "openai_chat_completions",
            "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            "api_key_env": ["QWEN_API_KEY", "DASHSCOPE_API_KEY"],
            "model_env": "QWEN_MODEL",
            "model_priority": [
                "qwen3.6-plus",
                "qwen3-max",
                "qwen3.5-plus",
                "qwen3-coder-plus",
                "qwen3-coder-next",
                "qwen3-coder-flash",
                "qwen3-235b-a22b",
                "qwen3-32b",
                "qwq-plus",
                "qwq-32b",
            ],
            "discover_models": True,
        },
        "xiaomi-mimo": {
            "enabled": True,
            "client": "anthropic_messages",
            "base_url": "https://token-plan-cn.xiaomimimo.com/anthropic/v1",
            "api_key_env": "MIMO_API_KEY",
            "model_env": "MIMO_MODEL",
            "model_priority": [
                "mimo-v2.5-pro",
                "mimo-v2-pro",
                "mimo-v2-flash",
            ],
            "discover_models": False,
        },
    },
}


SYSTEM_PROMPT = (
    "You are one independent participant in a multi-model consensus workflow. "
    "Answer the user's original task directly and concretely. Do not mention "
    "that other models will also answer. Be useful to a downstream reviewer: "
    "include your key recommendation, reasoning, assumptions, risks or weak "
    "points, and next steps when relevant."
)


@dataclasses.dataclass
class ProviderRuntime:
    name: str
    config: Dict[str, Any]
    api_key: str
    api_key_env: str
    model: str
    model_source: str
    available_models: List[str]
    model_list_error: Optional[str]


class ProviderHTTPError(RuntimeError):
    def __init__(self, status: int, reason: str, body: str) -> None:
        self.status = status
        self.reason = reason
        self.body = body
        trimmed = body[:800].replace("\n", " ")
        super().__init__(f"HTTP {status} {reason}: {trimmed}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a multi-provider LLM consensus request."
    )
    input_group = parser.add_mutually_exclusive_group(required=False)
    input_group.add_argument("--task", help="Task text to send to providers.")
    input_group.add_argument("--task-file", help="Read task text from a file.")
    input_group.add_argument(
        "--stdin", action="store_true", help="Read task text from stdin."
    )
    parser.add_argument("--config", help="Path to llm-providers.json override.")
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--provider",
        action="append",
        help="Only include this provider. Repeat to include several.",
    )
    parser.add_argument(
        "--exclude-provider",
        action="append",
        default=[],
        help="Exclude this provider. Repeat to exclude several.",
    )
    parser.add_argument("--timeout", type=float, help="Override timeout seconds.")
    parser.add_argument("--retries", type=int, help="Override retry count.")
    parser.add_argument(
        "--max-output-tokens", type=int, help="Override per-provider output cap."
    )
    parser.add_argument("--temperature", type=float, help="Override temperature.")
    parser.add_argument("--concurrency", type=int, help="Override max workers.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show discovered providers/models without sending prompts.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Return deterministic mock provider results without API keys.",
    )
    return parser.parse_args()


def read_task(args: argparse.Namespace) -> str:
    if args.task is not None:
        return args.task.strip()
    if args.task_file:
        return Path(args.task_file).read_text(encoding="utf-8").strip()
    if args.stdin:
        return sys.stdin.read().strip()
    return ""


def load_dotenv(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists() or not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def deep_merge(base: Dict[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    merged = json.loads(json.dumps(base))
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, Mapping)
        ):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def load_config(args: argparse.Namespace, env: Mapping[str, str]) -> Tuple[Dict[str, Any], List[str]]:
    cwd = Path.cwd()
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    loaded: List[str] = []
    candidate_paths: List[Path] = [
        cwd / "llm-providers.json",
        cwd / "config" / "llm-providers.json",
    ]
    if args.config:
        candidate_paths.append(Path(args.config))
    if env.get("LLM_PROVIDERS_CONFIG"):
        candidate_paths.append(Path(env["LLM_PROVIDERS_CONFIG"]))

    for path in candidate_paths:
        if path.exists():
            data = load_json(path)
            config = deep_merge(config, data)
            loaded.append(str(path))

    defaults = config.setdefault("defaults", {})
    if args.timeout is not None:
        defaults["timeout_seconds"] = args.timeout
    if args.retries is not None:
        defaults["retries"] = args.retries
    if args.max_output_tokens is not None:
        defaults["max_output_tokens"] = args.max_output_tokens
    if args.temperature is not None:
        defaults["temperature"] = args.temperature
    if args.concurrency is not None:
        defaults["concurrency"] = args.concurrency
    return config, loaded


def make_env() -> Dict[str, str]:
    dotenv = load_dotenv(Path.cwd() / ".env")
    env = dict(dotenv)
    env.update(os.environ)
    return env


def env_names(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def resolve_api_key(provider_config: Mapping[str, Any], env: Mapping[str, str]) -> Tuple[Optional[str], str]:
    in_memory_key = provider_config.get("_api_key_value")
    if in_memory_key:
        return str(in_memory_key), str(provider_config.get("_api_key_source", "in-memory"))

    names = env_names(provider_config.get("api_key_env"))
    for name in names:
        if env.get(name):
            return env[name], name
    return None, names[0] if names else ""


def normalize_model_id(model_id: str) -> str:
    return model_id.rsplit("/", 1)[-1].strip()


def build_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def http_json(
    method: str,
    url: str,
    headers: Mapping[str, str],
    payload: Optional[Mapping[str, Any]],
    timeout: float,
) -> Dict[str, Any]:
    body = None
    final_headers = dict(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        final_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=body, headers=final_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise ProviderHTTPError(exc.code, exc.reason, raw) from exc


def openai_headers(api_key: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def anthropic_headers(api_key: str) -> Dict[str, str]:
    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }


def list_models(provider: str, config: Mapping[str, Any], api_key: str, timeout: float) -> List[str]:
    client = config.get("client")
    base_url = str(config.get("base_url", "")).rstrip("/")
    if not config.get("discover_models", True):
        return []

    if client in {"openai_responses", "openai_chat_completions"}:
        data = http_json(
            "GET",
            build_url(base_url, "models"),
            openai_headers(api_key),
            None,
            timeout,
        )
        return parse_model_ids(data)

    if client == "anthropic_messages":
        data = http_json(
            "GET",
            build_url(base_url, "models"),
            anthropic_headers(api_key),
            None,
            timeout,
        )
        return parse_model_ids(data)

    if client == "gemini_generate":
        query = urllib.parse.urlencode({"key": api_key})
        data = http_json(
            "GET",
            f"{build_url(base_url, 'models')}?{query}",
            {},
            None,
            timeout,
        )
        models = data.get("models", [])
        if isinstance(models, list):
            return [
                normalize_model_id(str(item.get("name", "")))
                for item in models
                if isinstance(item, dict) and item.get("name")
            ]
        return []

    raise ValueError(f"{provider}: unsupported client for model listing: {client}")


def parse_model_ids(data: Mapping[str, Any]) -> List[str]:
    records = data.get("data")
    if not isinstance(records, list):
        records = data.get("models")
    if not isinstance(records, list):
        return []
    model_ids: List[str] = []
    for item in records:
        if isinstance(item, dict):
            raw = item.get("id") or item.get("name")
            if raw:
                model_ids.append(normalize_model_id(str(raw)))
        elif isinstance(item, str):
            model_ids.append(normalize_model_id(item))
    return model_ids


def select_model(
    provider: str,
    config: Mapping[str, Any],
    env: Mapping[str, str],
    api_key: str,
    timeout: float,
) -> Tuple[Optional[str], str, List[str], Optional[str]]:
    model_env = config.get("model_env")
    if isinstance(model_env, str) and env.get(model_env):
        return env[model_env], f"env:{model_env}", [], None

    explicit_model = config.get("model")
    if explicit_model:
        return str(explicit_model), "config:model", [], None

    available: List[str] = []
    list_error: Optional[str] = None
    if config.get("discover_models", True):
        try:
            available = list_models(provider, config, api_key, timeout)
        except Exception as exc:  # model listing is advisory
            list_error = safe_error(exc)

    priority = [str(item) for item in config.get("model_priority", [])]
    if available:
        by_lower = {normalize_model_id(model).lower(): normalize_model_id(model) for model in available}
        for candidate in priority:
            found = by_lower.get(normalize_model_id(candidate).lower())
            if found:
                return found, "model_priority+models_api", available, list_error
        if config.get("allow_unprioritized_models"):
            return normalize_model_id(available[0]), "models_api:first", available, list_error

    if priority:
        return priority[0], "model_priority:fallback", available, list_error

    return None, "missing:model_priority", available, list_error


def build_provider_runtimes(
    config: Mapping[str, Any],
    env: Mapping[str, str],
    args: argparse.Namespace,
) -> Tuple[List[ProviderRuntime], List[Dict[str, Any]]]:
    providers = dict(config.get("providers", {}))
    defaults = config.get("defaults", {})
    timeout = float(defaults.get("timeout_seconds", 60))
    include = set(args.provider or [])
    exclude = set(args.exclude_provider or [])
    runtimes: List[ProviderRuntime] = []
    skipped: List[Dict[str, Any]] = []

    for name, raw_config in providers.items():
        if include and name not in include:
            skipped.append({"provider": name, "reason": "not requested"})
            continue
        if name in exclude:
            skipped.append({"provider": name, "reason": "excluded"})
            continue
        if not isinstance(raw_config, dict):
            skipped.append({"provider": name, "reason": "invalid config"})
            continue
        provider_config = dict(raw_config)
        if not provider_config.get("enabled", True):
            skipped.append({"provider": name, "reason": "disabled"})
            continue

        api_key, api_key_env = resolve_api_key(provider_config, env)
        if not api_key:
            skipped.append(
                {
                    "provider": name,
                    "reason": "missing api key",
                    "expected_env": env_names(provider_config.get("api_key_env")),
                }
            )
            continue

        model, model_source, available, list_error = select_model(
            name, provider_config, env, api_key, timeout
        )
        if not model:
            skipped.append(
                {
                    "provider": name,
                    "reason": "missing model",
                    "model_source": model_source,
                    "model_list_error": list_error,
                }
            )
            continue

        runtimes.append(
            ProviderRuntime(
                name=name,
                config=provider_config,
                api_key=api_key,
                api_key_env=api_key_env,
                model=model,
                model_source=model_source,
                available_models=available,
                model_list_error=list_error,
            )
        )

    return runtimes, skipped


def unified_prompt(task: str) -> str:
    return (
        "Original task:\n"
        f"{task}\n\n"
        "Please respond as an expert independent reviewer. Include:\n"
        "1. Direct answer or recommendation\n"
        "2. Key reasoning and assumptions\n"
        "3. Risks, weak points, or uncertainties\n"
        "4. Practical next steps or implementation details when relevant\n"
        "Keep the answer concise enough for another agent to compare with other model answers."
    )


def generate_response(
    runtime: ProviderRuntime,
    prompt: str,
    defaults: Mapping[str, Any],
) -> str:
    client = runtime.config.get("client")
    if client == "openai_responses":
        return call_openai_responses(runtime, prompt, defaults)
    if client == "openai_chat_completions":
        return call_openai_chat_completions(runtime, prompt, defaults)
    if client == "anthropic_messages":
        return call_anthropic_messages(runtime, prompt, defaults)
    if client == "gemini_generate":
        return call_gemini_generate(runtime, prompt, defaults)
    raise ValueError(f"{runtime.name}: unsupported client: {client}")


def with_extra_body(payload: Dict[str, Any], config: Mapping[str, Any]) -> Dict[str, Any]:
    extra = config.get("extra_body")
    if isinstance(extra, dict):
        merged = dict(payload)
        merged.update(extra)
        return merged
    return payload


def call_openai_responses(
    runtime: ProviderRuntime,
    prompt: str,
    defaults: Mapping[str, Any],
) -> str:
    timeout = float(defaults.get("timeout_seconds", 60))
    payload: Dict[str, Any] = {
        "model": runtime.model,
        "instructions": SYSTEM_PROMPT,
        "input": prompt,
        "max_output_tokens": int(defaults.get("max_output_tokens", 1400)),
    }
    if defaults.get("temperature") is not None:
        payload["temperature"] = float(defaults.get("temperature"))
    payload = with_extra_body(payload, runtime.config)
    data = http_json(
        "POST",
        build_url(str(runtime.config["base_url"]), "responses"),
        openai_headers(runtime.api_key),
        payload,
        timeout,
    )
    return extract_openai_responses_text(data)


def call_openai_chat_completions(
    runtime: ProviderRuntime,
    prompt: str,
    defaults: Mapping[str, Any],
) -> str:
    timeout = float(defaults.get("timeout_seconds", 60))
    token_field = str(runtime.config.get("max_tokens_field", "max_tokens"))
    payload: Dict[str, Any] = {
        "model": runtime.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        token_field: int(defaults.get("max_output_tokens", 1400)),
    }
    if defaults.get("temperature") is not None:
        payload["temperature"] = float(defaults.get("temperature"))
    payload = with_extra_body(payload, runtime.config)
    data = http_json(
        "POST",
        build_url(str(runtime.config["base_url"]), "chat/completions"),
        openai_headers(runtime.api_key),
        payload,
        timeout,
    )
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"].strip()
        text = choices[0].get("text") if isinstance(choices[0], dict) else None
        if isinstance(text, str):
            return text.strip()
    return extract_any_text(data)


def call_anthropic_messages(
    runtime: ProviderRuntime,
    prompt: str,
    defaults: Mapping[str, Any],
) -> str:
    timeout = float(defaults.get("timeout_seconds", 60))
    payload: Dict[str, Any] = {
        "model": runtime.model,
        "max_tokens": int(defaults.get("max_output_tokens", 1400)),
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }
    if defaults.get("temperature") is not None:
        payload["temperature"] = float(defaults.get("temperature"))
    payload = with_extra_body(payload, runtime.config)
    data = http_json(
        "POST",
        build_url(str(runtime.config["base_url"]), "messages"),
        anthropic_headers(runtime.api_key),
        payload,
        timeout,
    )
    parts = data.get("content")
    if isinstance(parts, list):
        texts = [
            part.get("text", "")
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        if texts:
            return "\n".join(texts).strip()
    return extract_any_text(data)


def call_gemini_generate(
    runtime: ProviderRuntime,
    prompt: str,
    defaults: Mapping[str, Any],
) -> str:
    timeout = float(defaults.get("timeout_seconds", 60))
    generation_config: Dict[str, Any] = {
        "maxOutputTokens": int(defaults.get("max_output_tokens", 1400))
    }
    if defaults.get("temperature") is not None:
        generation_config["temperature"] = float(defaults.get("temperature"))
    payload: Dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }
    payload = with_extra_body(payload, runtime.config)
    model = urllib.parse.quote(runtime.model, safe="")
    query = urllib.parse.urlencode({"key": runtime.api_key})
    data = http_json(
        "POST",
        f"{build_url(str(runtime.config['base_url']), f'models/{model}:generateContent')}?{query}",
        {},
        payload,
        timeout,
    )
    candidates = data.get("candidates")
    if isinstance(candidates, list) and candidates:
        content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if isinstance(parts, list):
            texts = [
                part.get("text", "")
                for part in parts
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            ]
            if texts:
                return "\n".join(texts).strip()
    return extract_any_text(data)


def extract_openai_responses_text(data: Mapping[str, Any]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output = data.get("output")
    texts: List[str] = []
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        texts.append(part["text"])
    if texts:
        return "\n".join(texts).strip()
    return extract_any_text(data)


def extract_any_text(data: Any) -> str:
    texts: List[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            text = value.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data)
    return "\n".join(dict.fromkeys(texts)).strip()


def safe_error(exc: BaseException) -> str:
    message = str(exc)
    if isinstance(exc, ProviderHTTPError):
        message = str(exc)
    return message.replace("\r", " ").replace("\n", " ")[:1000]


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, ProviderHTTPError):
        return exc.status == 429 or exc.status >= 500
    return isinstance(exc, (TimeoutError, urllib.error.URLError))


def call_with_retries(
    runtime: ProviderRuntime,
    prompt: str,
    defaults: Mapping[str, Any],
) -> Dict[str, Any]:
    start = time.perf_counter()
    retries = int(defaults.get("retries", 1))
    last_error = ""
    attempts = 0
    for attempt in range(retries + 1):
        attempts = attempt + 1
        try:
            response = generate_response(runtime, prompt, defaults)
            latency = time.perf_counter() - start
            return {
                "provider": runtime.name,
                "model": runtime.model,
                "status": "success",
                "response": response,
                "error": None,
                "latency": round(latency, 3),
                "attempts": attempts,
                "model_source": runtime.model_source,
                "api_key_env": runtime.api_key_env,
                "model_list_error": runtime.model_list_error,
            }
        except Exception as exc:
            last_error = safe_error(exc)
            if attempt >= retries or not is_retryable(exc):
                break
            time.sleep(min(1.5 * (2**attempt), 6.0))

    latency = time.perf_counter() - start
    return {
        "provider": runtime.name,
        "model": runtime.model,
        "status": "error",
        "response": "",
        "error": last_error,
        "latency": round(latency, 3),
        "attempts": attempts,
        "model_source": runtime.model_source,
        "api_key_env": runtime.api_key_env,
        "model_list_error": runtime.model_list_error,
    }


def run_requests(
    runtimes: List[ProviderRuntime],
    prompt: str,
    defaults: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    if not runtimes:
        return []
    max_workers = max(1, min(int(defaults.get("concurrency", 6)), len(runtimes)))
    results: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(call_with_retries, runtime, prompt, defaults): runtime
            for runtime in runtimes
        }
        for future in concurrent.futures.as_completed(future_map):
            results.append(future.result())
    return sorted(results, key=lambda item: item["provider"])


def mock_results(task: str, provider_filter: Optional[Iterable[str]]) -> List[Dict[str, Any]]:
    names = list(provider_filter or ["openai", "anthropic", "gemini"])
    results: List[Dict[str, Any]] = []
    for index, name in enumerate(names, start=1):
        start = time.perf_counter()
        response = (
            f"Mock answer from {name}. Recommendation {index}: define the goal, "
            "compare assumptions, identify risks, and produce an actionable synthesis. "
            f"Task hash: {hashlib.sha256(task.encode('utf-8')).hexdigest()[:12]}."
        )
        results.append(
            {
                "provider": name,
                "model": "mock-model",
                "status": "success",
                "response": response,
                "error": None,
                "latency": round(time.perf_counter() - start, 3),
                "attempts": 1,
                "model_source": "mock",
                "api_key_env": None,
                "model_list_error": None,
            }
        )
    return results


def summarize_discovery(
    runtimes: List[ProviderRuntime],
    skipped: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "participants": [
            {
                "provider": runtime.name,
                "model": runtime.model,
                "model_source": runtime.model_source,
                "api_key_env": runtime.api_key_env,
                "model_list_error": runtime.model_list_error,
            }
            for runtime in runtimes
        ],
        "skipped": skipped,
    }


def build_report(
    task: str,
    prompt: str,
    results: List[Dict[str, Any]],
    skipped: List[Dict[str, Any]],
    loaded_config_files: List[str],
    dry_run: bool = False,
) -> Dict[str, Any]:
    successful = [
        {"provider": item["provider"], "model": item["model"]}
        for item in results
        if item["status"] == "success"
    ]
    discovered = [
        {"provider": item["provider"], "model": item["model"]}
        for item in results
        if item["status"] == "discovered"
    ]
    failed = [
        {
            "provider": item["provider"],
            "model": item["model"],
            "error": item.get("error"),
        }
        for item in results
        if item["status"] not in {"success", "discovered"}
    ]
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "dry_run": dry_run,
        "task_sha256": hashlib.sha256(task.encode("utf-8")).hexdigest(),
        "task": task,
        "unified_prompt": prompt,
        "loaded_config_files": loaded_config_files,
        "required_final_sections": [
            "简短结论",
            "本次参与模型",
            "各模型输出评审",
            "综合后的最终建议/答案",
            "分歧点与我的判断",
            "仍需用户确认的问题",
        ],
        "per_model_review_fields": [
            "关键观点",
            "优点",
            "不足或风险",
            "可采纳内容",
        ],
        "successful": successful,
        "discovered": discovered,
        "failed": failed,
        "skipped": skipped,
        "results": results,
    }


def output_json(report: Mapping[str, Any]) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2))


def output_markdown(report: Mapping[str, Any]) -> None:
    print("# Multi-LLM Consensus Run")
    print()
    print(f"- Generated: `{report['generated_at']}`")
    print(f"- Task SHA-256: `{report['task_sha256']}`")
    loaded = report.get("loaded_config_files") or []
    print(f"- Config files: {', '.join(f'`{item}`' for item in loaded) if loaded else 'built-in defaults only'}")
    print()
    print("## Task")
    print()
    print(str(report.get("task", "")).strip() or "(empty)")
    print()
    print("## Participation")
    print()
    successful = report.get("successful") or []
    discovered = report.get("discovered") or []
    failed = report.get("failed") or []
    skipped = report.get("skipped") or []
    if successful:
        print("Successful:")
        for item in successful:
            print(f"- {item['provider']} / `{item['model']}`")
    else:
        print("Successful: none")
    if discovered:
        print()
        print("Discovered:")
        for item in discovered:
            print(f"- {item['provider']} / `{item['model']}`")
    if failed:
        print()
        print("Failed:")
        for item in failed:
            print(f"- {item['provider']} / `{item['model']}`: {item.get('error')}")
    if skipped:
        print()
        print("Skipped:")
        for item in skipped:
            expected = item.get("expected_env")
            suffix = f" Expected env: {', '.join(expected)}." if expected else ""
            print(f"- {item.get('provider')}: {item.get('reason')}.{suffix}")
    print()

    if report.get("dry_run"):
        print("Dry run only; no provider prompts were sent.")
        return

    print("## Raw Model Answers")
    print()
    for item in report.get("results", []):
        print(f"### {item['provider']} / `{item['model']}`")
        print()
        print(f"- Status: `{item['status']}`")
        print(f"- Latency: `{item['latency']}s`")
        print(f"- Attempts: `{item.get('attempts', 1)}`")
        if item.get("model_source"):
            print(f"- Model source: `{item['model_source']}`")
        if item.get("model_list_error"):
            print(f"- Model list warning: {item['model_list_error']}")
        if item["status"] == "success":
            print()
            print(item.get("response", "").strip() or "(empty response)")
        else:
            print()
            print(f"Error: {item.get('error')}")
        print()

    successful_results = [
        item for item in report.get("results", []) if item.get("status") == "success"
    ]
    if successful_results:
        print("## Per-Model Review Worksheet")
        print()
        print("Fill this in before writing the final synthesis:")
        print()
        for item in successful_results:
            print(f"### {item['provider']} / `{item['model']}`")
            print()
            print("- 关键观点:")
            print("- 优点:")
            print("- 不足或风险:")
            print("- 可采纳内容:")
            print()

    print("## Synthesis Checklist For The Agent")
    print()
    print("- Report the exact successful provider/model pairs and any failed or skipped providers.")
    print("- For each successful model, extract key points, strengths, weak points or risks, and adoptable content.")
    print("- State which providers succeeded and failed.")
    print("- Produce: 简短结论, 本次参与模型, 各模型输出评审, 综合后的最终建议/答案, 分歧点与我的判断, 仍需用户确认的问题.")


def main() -> int:
    args = parse_args()
    env = make_env()
    config, loaded_config_files = load_config(args, env)
    defaults = config.get("defaults", {})

    task = read_task(args)
    if not task:
        print("No task provided. Use --task, --task-file, or --stdin.", file=sys.stderr)
        return 2

    prompt = unified_prompt(task)

    if args.mock:
        results = mock_results(task, args.provider)
        report = build_report(task, prompt, results, [], loaded_config_files)
        output_json(report) if args.format == "json" else output_markdown(report)
        return 0

    runtimes, skipped = build_provider_runtimes(config, env, args)

    if args.dry_run:
        discovery = summarize_discovery(runtimes, skipped)
        results = [
            {
                "provider": item["provider"],
                "model": item["model"],
                "status": "discovered",
                "response": "",
                "error": None,
                "latency": 0,
                "attempts": 0,
                "model_source": item["model_source"],
                "api_key_env": item["api_key_env"],
                "model_list_error": item["model_list_error"],
            }
            for item in discovery["participants"]
        ]
        report = build_report(task, prompt, results, skipped, loaded_config_files, dry_run=True)
        output_json(report) if args.format == "json" else output_markdown(report)
        return 0

    if not runtimes:
        report = build_report(task, prompt, [], skipped, loaded_config_files)
        output_json(report) if args.format == "json" else output_markdown(report)
        print(
            "\nNo usable provider was found. Configure one or more API key environment variables "
            "such as OPENAI_API_KEY, ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, GEMINI_API_KEY, "
            "MINIMAX_API_KEY, QWEN_API_KEY, or DASHSCOPE_API_KEY.",
            file=sys.stderr,
        )
        return 1

    results = run_requests(runtimes, prompt, defaults)
    report = build_report(task, prompt, results, skipped, loaded_config_files)
    output_json(report) if args.format == "json" else output_markdown(report)
    return 0 if any(item["status"] == "success" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
