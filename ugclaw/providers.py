"""
providers.py — unified LLM layer for UGCLAW.

Supports: OpenAI, Anthropic, Google Gemini, Groq, OpenRouter.
All providers expose the same interface:
    client.chat(messages, tools) → (text, tool_calls)

Tool calls are always normalised to OpenAI-style objects so agent.py
never needs to care which provider is active.
"""

import json
import requests
from typing import Optional


# ── Provider registry ─────────────────────────────────────────────────────────

PROVIDERS: dict[str, dict] = {
    "openai": {
        "label":         "OpenAI",
        "key_field":     "openai_api_key",
        "fetch_models":  True,
        "models_url":    "https://api.openai.com/v1/models",
        "default_model": "gpt-4o",
        "chat_models_prefix": ["gpt-"],
    },
    "anthropic": {
        "label":         "Anthropic",
        "key_field":     "anthropic_api_key",
        "fetch_models":  True,
        "models_url":    "https://api.anthropic.com/v1/models",
        "default_model": "claude-sonnet-4-5",
    },
    "gemini": {
        "label":         "Google Gemini",
        "key_field":     "gemini_api_key",
        "fetch_models":  True,
        "models_url":    "https://generativelanguage.googleapis.com/v1beta/models",
        "default_model": "gemini-1.5-pro",
    },
    "groq": {
        "label":         "Groq",
        "key_field":     "groq_api_key",
        "fetch_models":  True,
        "models_url":    "https://api.groq.com/openai/v1/models",
        "default_model": "llama-3.1-70b-versatile",
    },
    "openrouter": {
        "label":         "OpenRouter",
        "key_field":     "openrouter_api_key",
        "fetch_models":  True,
        "models_url":    "https://openrouter.ai/api/v1/models",
        "default_model": "openai/gpt-4o",
    },
}

# Models to exclude when filtering provider lists
_SKIP_KEYWORDS = [
    "embed", "tts", "whisper", "dall-e", "vision-preview",
    "instruct", "search", "similarity", "edit", "babbage",
    "davinci-002", "ada-002", "moderation",
]


# ── Model fetching ─────────────────────────────────────────────────────────────

def fetch_models(provider_id: str, api_key: str) -> list[str]:
    """
    Return available model IDs from a provider.
    Falls back to static list on any error.
    Raises ValueError with a clear message if the API key is wrong.
    """
    meta = PROVIDERS.get(provider_id)
    if not meta:
        raise ValueError(f"Unknown provider: {provider_id}")

    if not meta.get("fetch_models"):
        return list(meta.get("static_models", []))

    url = meta["models_url"]

    try:
        if provider_id == "gemini":
            resp = requests.get(url, params={"key": api_key}, timeout=12)
        elif provider_id == "anthropic":
            resp = requests.get(
                url,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=12,
            )
        else:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=12,
            )

        if resp.status_code == 401:
            raise ValueError(f"Invalid API key for {meta['label']} (HTTP 401).")
        if resp.status_code == 403:
            raise ValueError(f"API key lacks permission for {meta['label']} (HTTP 403).")
        if not resp.ok:
            raise ValueError(f"{meta['label']} API error: HTTP {resp.status_code}.")

        data = resp.json()

        if provider_id == "gemini":
            raw = [m["name"].replace("models/", "") for m in data.get("models", [])]
        elif provider_id == "anthropic":
            raw = [m["id"] for m in data.get("data", [])]
        elif provider_id == "openrouter":
            raw = [m["id"] for m in data.get("data", [])]
        else:
            raw = [m["id"] for m in data.get("data", [])]

        # Filter to useful chat models
        filtered = [
            m for m in sorted(raw)
            if not any(kw in m.lower() for kw in _SKIP_KEYWORDS)
        ]
        return filtered or raw[:50]

    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Could not fetch models from {meta['label']}: {e}") from e


# ── Unified client ─────────────────────────────────────────────────────────────

class LLMClient:
    """
    Send messages to any supported LLM provider.
    .chat() always returns (text: str | None, tool_calls: list).
    """

    def __init__(self, provider_id: str, model: str, api_key: str, max_tokens: int = 4096):
        self.provider_id = provider_id
        self.model       = model
        self.api_key     = api_key
        self.max_tokens  = max_tokens

    def chat(self, messages: list, tools: list = None) -> tuple[Optional[str], list]:
        if not self.api_key:
            raise ValueError(
                f"No API key set for provider '{self.provider_id}'. "
                "Run: ugclaw configure providers"
            )

        try:
            if self.provider_id in ("openai", "groq", "openrouter"):
                return self._chat_openai_compat(messages, tools)
            elif self.provider_id == "anthropic":
                return self._chat_anthropic(messages, tools)
            elif self.provider_id == "gemini":
                return self._chat_gemini(messages, tools)
            else:
                raise ValueError(f"Unknown provider: {self.provider_id}")

        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(
                f"LLM request failed ({self.provider_id}/{self.model}): {e}"
            ) from e

    # ── OpenAI-compatible (OpenAI, Groq, OpenRouter) ──────────────────────────

    def _chat_openai_compat(self, messages, tools):
        import openai

        base_urls = {
            "openai":     None,
            "groq":       "https://api.groq.com/openai/v1",
            "openrouter": "https://openrouter.ai/api/v1",
        }
        base = base_urls[self.provider_id]
        kwargs = {"api_key": self.api_key}
        if base:
            kwargs["base_url"] = base

        client = openai.OpenAI(**kwargs)

        req = dict(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
        )
        if tools:
            req["tools"] = tools
            req["tool_choice"] = "auto"

        resp = client.chat.completions.create(**req)
        msg = resp.choices[0].message
        return msg.content, list(msg.tool_calls or [])

    # ── Anthropic ─────────────────────────────────────────────────────────────

    def _chat_anthropic(self, messages, tools):
        import anthropic as ant

        client = ant.Anthropic(api_key=self.api_key)

        system_text = ""
        filtered = []
        for m in messages:
            if m["role"] == "system":
                system_text = m.get("content", "")
            else:
                # Anthropic requires content to be a non-empty string
                content = m.get("content") or ""
                # Skip empty assistant turns (can happen mid-tool-loop)
                if m["role"] == "assistant" and not content:
                    continue
                filtered.append({"role": m["role"], "content": content})

        ant_tools = []
        if tools:
            for t in tools:
                fn = t["function"]
                ant_tools.append({
                    "name":         fn["name"],
                    "description":  fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                })

        req = dict(model=self.model, max_tokens=self.max_tokens, messages=filtered)
        if system_text:
            req["system"] = system_text
        if ant_tools:
            req["tools"] = ant_tools

        resp = client.messages.create(**req)

        text = None
        tool_calls = []
        for block in resp.content:
            if block.type == "text":
                text = block.text
            elif block.type == "tool_use":
                tool_calls.append(_FakeToolCall(block.id, block.name, block.input))

        return text, tool_calls

    # ── Gemini ────────────────────────────────────────────────────────────────

    def _chat_gemini(self, messages, tools):
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)

        model = genai.GenerativeModel(self.model)

        parts = []
        for m in messages:
            role    = m["role"]
            content = m.get("content") or ""
            if role == "system":
                parts.append(f"[System Instructions]: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
            elif role == "tool":
                parts.append(f"[Tool Result]: {content}")

        prompt = "\n\n".join(parts)

        if tools:
            names = [t["function"]["name"] for t in tools]
            prompt += (
                f"\n\n[Available tools: {', '.join(names)}. "
                "If you need to call a tool respond ONLY with valid JSON: "
                '{"tool": "<name>", "args": {<args>}}. '
                "Otherwise respond in plain text.]"
            )

        import re
        resp = model.generate_content(prompt)

        # Gemma 4 / Gemini thinking models return multiple parts per candidate.
        # The old google-generativeai SDK does not expose thought=True, so we
        # cannot filter by attribute. The real answer is always the LAST part;
        # everything before it is internal reasoning.
        try:
            parts = resp.candidates[0].content.parts
            text = (parts[-1].text or "").strip() if parts else (resp.text or "").strip()
        except Exception:
            text = (resp.text or "").strip()

        # Strip markdown code fences some models wrap around JSON
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()

        # Parse optional tool call
        tool_calls = []
        if '"tool"' in text:
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    if "tool" in data:
                        tool_calls.append(
                            _FakeToolCall("gemini_0", data["tool"], data.get("args", {}))
                        )
                        text = None
                except Exception:
                    pass

        return text, tool_calls


# ── Duck-type OpenAI tool call ────────────────────────────────────────────────

class _FakeToolCall:
    """Normalises Anthropic/Gemini tool calls to look like openai tool_call objects."""

    class _Fn:
        def __init__(self, name, arguments):
            self.name      = name
            self.arguments = (
                json.dumps(arguments)
                if isinstance(arguments, dict)
                else str(arguments)
            )

    def __init__(self, id: str, name: str, arguments):
        self.id       = id
        self.type     = "function"
        self.function = self._Fn(name, arguments)


# ── Factory ───────────────────────────────────────────────────────────────────

def make_client(config: dict, provider_id: str = None, model: str = None) -> LLMClient:
    pid  = provider_id or config.get("active_provider", "openai")
    meta = PROVIDERS.get(pid, {})
    key  = config.get(meta.get("key_field", "openai_api_key"), "")
    mod  = model or config.get("active_model", meta.get("default_model", "gpt-4o"))
    return LLMClient(pid, mod, key, config.get("max_tokens", 4096))
