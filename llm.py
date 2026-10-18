"""LLM helpers: JSON calls + a small tool-using agent loop with a full trace.

The agent loop is plain JSON ("call this tool" / "here is my final answer"), so it works
with any model and gives us a clean trace to show judges (Track 01: explainable results).
"""
import json
import os
import re
import time

from google import genai

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
_client = None


def _c():
    global _client
    if _client is None:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _client = genai.Client(api_key=key)
    return _client


FALLBACK = os.environ.get("GEMINI_FALLBACK_MODEL")  # optional: a second model to try if the first is overloaded


def _generate(prompt: str, json_mode: bool) -> str:
    cfg = {"response_mime_type": "application/json"} if json_mode else None
    last = None
    delays = [3, 6, 12, 20, 30, 45]          # ~2 minutes of patience for 503 / 429 spikes
    for attempt in range(len(delays) + 1):
        model = FALLBACK if (FALLBACK and attempt >= 3) else MODEL
        try:
            r = _c().models.generate_content(model=model, contents=prompt, config=cfg)
            return r.text or ""
        except Exception as e:
            last = e
            msg = str(e)
            transient = any(code in msg for code in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "500", "timed out"))
            if not transient or attempt == len(delays):
                break
            time.sleep(delays[attempt])
    raise last


def parse_json(text: str) -> dict:
    try:
        out = json.loads(text)
        return out if isinstance(out, dict) else {}
    except Exception:
        m = re.search(r"\{.*\}", text or "", re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}


def ask_json(prompt: str) -> dict:
    return parse_json(_generate(prompt, True))


def ask_text(prompt: str) -> str:
    return _generate(prompt, False)


def agent_loop(role: str, task: str, tools: dict, context: str = "", max_steps: int = 6):
    """tools = {name: (callable, 'description incl. args')}.  Returns (final_dict, trace)."""
    tool_doc = "\n".join(f"- {n}: {d}" for n, (_, d) in tools.items())
    trace, scratch, seen = [], [], set()

    for step in range(1, max_steps + 1):
        prompt = f"""{role}

TOOLS (they read the knowledge graph):
{tool_doc}

{context}

TASK: {task}

WORK SO FAR:
{chr(10).join(scratch) or '(nothing yet)'}

Reply with ONLY JSON. Either call exactly one tool:
{{"thought": "short reason", "tool": "<tool name>", "args": {{...}}}}
or, once you have enough evidence, finish:
{{"thought": "short reason", "final": {{...}}}}
Never repeat a tool call with the same args."""
        out = parse_json(_generate(prompt, True))

        if out.get("tool") in tools:
            args = out.get("args") or {}
            key = out["tool"] + json.dumps(args, sort_keys=True, default=str)
            if key in seen:
                scratch.append("(You already made that exact call. Use new args or finish.)")
                continue
            seen.add(key)
            try:
                result = tools[out["tool"]][0](**args)
            except Exception as e:
                result = {"error": f"{type(e).__name__}: {e}"}
            trace.append({"step": step, "thought": out.get("thought", ""),
                          "tool": out["tool"], "args": args, "result": result})
            scratch.append(f"Step {step}: {out['tool']}({json.dumps(args, default=str)}) -> "
                           f"{json.dumps(result, default=str)[:1800]}")
            continue

        final = out.get("final", out)
        if isinstance(final, str):
            final = {"answer": final}
        return final, trace

    # Out of steps: force a best-effort final answer from the evidence so far.
    prompt = f"""{role}

TASK: {task}

Evidence gathered from the graph:
{chr(10).join(scratch)}

Give your best final answer now. Reply ONLY with JSON: {{"final": {{...}}}}"""
    out = parse_json(_generate(prompt, True))
    final = out.get("final", out)
    if isinstance(final, str):
        final = {"answer": final}
    return final, trace
