"""
agent.py — UGCLAW LLM brain.

Runs a tool-calling loop until the LLM returns a plain text response.
When max iterations are hit, asks the LLM to summarise progress instead
of returning a dead error message.

Supports hot-swapping provider/model mid-session without losing history.
"""

import json
import re
from typing import Optional

from ugclaw.providers import make_client, LLMClient
from ugclaw.memory import Memory


class Agent:
    def __init__(
        self,
        config: dict,
        tools_handler,
        memory: Memory,
        session_id: str = "terminal",
        system_prompt: Optional[str] = None,
        provider_id: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.config      = config
        self.tools       = tools_handler
        self.memory      = memory
        self.session_id  = session_id
        self.system_prompt = system_prompt or config.get("system_prompt", "You are UGCLAW.")
        self.context: dict = {}

        self._provider_id = provider_id or config.get("active_provider", "openai")
        self._model       = model or config.get("active_model", "gpt-4o")
        self._client: LLMClient = make_client(config, self._provider_id, self._model)
        self._max_iter    = config.get("max_tool_iterations", 15)

        # Load persisted history
        self.history: list = memory.load_session(session_id)

    # ── Public ────────────────────────────────────────────────────────────────

    def chat(self, user_input: str) -> str:
        self.history.append({"role": "user", "content": user_input})
        messages = [{"role": "system", "content": self._system()}] + self.history

        for iteration in range(self._max_iter):
            try:
                text, tool_calls = self._client.chat(messages, self.tools.definitions())
            except Exception as e:
                error_msg = f"⚠️  LLM error: {e}"
                self.history.append({"role": "assistant", "content": error_msg})
                self._persist()
                return error_msg

            # No tool calls — we have a final answer
            if not tool_calls:
                content = self._strip_thinking(text or "")
                self.history.append({"role": "assistant", "content": content})
                self._persist()
                return content

            # Append assistant turn with tool_calls
            tc_dicts = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name":      tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
            messages.append({
                "role":       "assistant",
                "content":    text,
                "tool_calls": tc_dicts,
            })

            # Execute all tool calls in this round
            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {}

                result, ctx_update = self.tools.call(name, args, self.context)
                if ctx_update:
                    self.context.update(ctx_update)

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      str(result),
                })

        # Hit max iterations — ask LLM to summarise what it did
        messages.append({
            "role":    "user",
            "content": (
                "You have reached the maximum number of tool calls. "
                "Summarise everything you have done, found, or completed so far. "
                "Be concise and clear."
            ),
        })
        try:
            summary_text, _ = self._client.chat(messages, tools=None)
            content = self._strip_thinking(summary_text or "") or "Task incomplete — max tool iterations reached."
        except Exception:
            content = "⚠️  Task incomplete — max tool iterations reached."

        self.history.append({"role": "assistant", "content": content})
        self._persist()
        return content

    def switch_model(self, provider_id: str, model: str):
        """Hot-swap provider/model without clearing history."""
        self._provider_id = provider_id
        self._model       = model
        self._client      = make_client(self.config, provider_id, model)
        self.config["active_provider"] = provider_id
        self.config["active_model"]    = model

    def current_model(self) -> str:
        return f"{self._provider_id} / {self._model}"

    def usage_stats(self) -> dict:
        """Basic usage info for /usage command."""
        return {
            "session_id":    self.session_id,
            "messages":      len(self.history),
            "provider":      self._provider_id,
            "model":         self._model,
            "max_iter":      self._max_iter,
        }

    def reset(self):
        """Clear history and context. Memory (facts/AGENT.md) is preserved."""
        self.history.clear()
        self.context.clear()
        self._persist()

    # ── Private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """
        Remove internal monologue that thinking/reasoning models emit
        before their actual reply.

        Handles:
          1. XML tags:  <think>…</think>  or  <thinking>…</thinking>
          2. Prose thinking blocks (single-newline separated) where lines look like
             "The user said…", "Plan:", "I should…", etc., followed by the real answer.
        """
        if not text:
            return text

        # 1. Strip XML-style thinking tags (greedy across newlines)
        text = re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", "", text, flags=re.DOTALL).strip()

        # 2. Prose thinking — work line by line.
        # A line is a "thinking line" if it matches any of these patterns.
        _THINKING_LINE_RE = re.compile(
            r"^("
            r"The (user|agent|assistant|system|response|reply|task|request|goal|plan|approach|context|result|output)\b"
            r"|There (is|are|were|was)\b"
            r"|I (am|should|need|will|have|can|must|want|think|know|see|notice|realize|believe|understand|found|got|checked|ran|executed|asked)\b"
            r"|I'(m|ll|ve|d)\b"
            r"|Let me\b"
            r"|Let's\b"
            r"|Plan:|Step \d+:|Steps?:|Note:|Notes:|Summary:|Approach:|Goal:|Reasoning:|Thinking:|Context:"
            r"|Assistant:|From the\b|Based on\b|Looking at\b|Given (that|the)\b"
            r"|My \w+\b"
            r"|First[,.]|Second[,.]|Third[,.]|Next[,.]|Then[,.]|Finally[,.]|Now[,.]|Also[,.]"
            r"|So[,.]|Thus[,.]|Therefore[,.]"
            r")",
            re.IGNORECASE,
        )

        lines = text.splitlines()

        # Find the last line that looks like thinking — everything after is the answer.
        # We scan from the bottom up to find where thinking ends.
        last_thinking_idx = -1
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if _THINKING_LINE_RE.match(stripped):
                last_thinking_idx = i

        # Only strip if thinking lines were actually found and they don't
        # consume the entire text (i.e. there's a real answer after them).
        if last_thinking_idx >= 0 and last_thinking_idx < len(lines) - 1:
            answer_lines = lines[last_thinking_idx + 1:]
            answer = "\n".join(answer_lines).strip()
            if answer:
                return answer

        return text

    def _system(self) -> str:
        parts = [
            self.memory.build_context_prefix(),
            self.system_prompt,
        ]
        if self.context:
            parts.append(f"\n[Runtime context: {json.dumps(self.context)}]")
        return "\n\n".join(parts)

    def _persist(self):
        self.memory.save_session(self.session_id, self.history)
