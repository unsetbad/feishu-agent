#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import threading
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
STOP = False
CURRENT_PROCESS: subprocess.Popen[str] | None = None


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc


def _is_anthropic_api(base_url: str) -> bool:
    return "anthropic" in base_url.lower()


def _call_anthropic(base_url: str, api_key: str, model: str, system_prompt: str, user_text: str, temperature: float, max_tokens: int) -> str:
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_text},
        ],
    }
    if temperature is not None:
        payload["temperature"] = temperature

    body = json.dumps(payload).encode("utf-8")
    if base_url.endswith("/messages"):
        url = base_url
    elif base_url.endswith("/v1"):
        url = f"{base_url}/messages"
    else:
        url = f"{base_url}/v1/messages"
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"model HTTP {exc.code}: {detail}") from exc

    try:
        parts = data.get("content", [])
        text_parts = [p.get("text", "") for p in parts if p.get("type") == "text"]
        if not text_parts:
            raise RuntimeError(f"no text in model response: {data}")
        return "".join(text_parts).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"unexpected model response: {data}") from exc


def _call_openai(base_url: str, api_key: str, model: str, system_prompt: str, user_text: str, temperature: float, max_tokens: int) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"model HTTP {exc.code}: {detail}") from exc

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"unexpected model response: {data}") from exc


def chat_completion(user_text: str) -> str:
    base_url = (os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "").strip().rstrip("/")
    api_key = (os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not base_url:
        raise RuntimeError("Missing required environment variable: LLM_BASE_URL (or OPENAI_BASE_URL)")
    if not api_key:
        raise RuntimeError("Missing required environment variable: LLM_API_KEY (or OPENAI_API_KEY)")
    model = os.environ.get("LLM_MODEL") or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    system_prompt = os.environ.get(
        "AGENT_SYSTEM_PROMPT",
        "你是一个在飞书里工作的 AI 助手。回答要简洁、准确、可执行，默认使用中文。",
    )
    temperature = env_float("AGENT_TEMPERATURE", 0.3)
    max_tokens = env_int("AGENT_MAX_TOKENS", 1200)

    if _is_anthropic_api(base_url):
        return _call_anthropic(base_url, api_key, model, system_prompt, user_text, temperature, max_tokens)
    return _call_openai(base_url, api_key, model, system_prompt, user_text, temperature, max_tokens)


def reply_to_message(message_id: str, text: str, event_id: str) -> None:
    if not text:
        text = "我没有生成到有效回复。"
    max_chars = env_int("FEISHU_REPLY_MAX_CHARS", 4000)
    use_markdown = os.environ.get("FEISHU_REPLY_FORMAT", "markdown").lower() == "markdown"
    flag = "--markdown" if use_markdown else "--text"
    command = [
        "lark-cli",
        "im",
        "+messages-reply",
        "--as",
        "bot",
        "--message-id",
        message_id,
        flag,
        text[:max_chars],
        "--idempotency-key",
        event_id,
    ]
    if os.environ.get("FEISHU_REPLY_IN_THREAD", "").lower() in {"1", "true", "yes"}:
        command.append("--reply-in-thread")
    subprocess.run(
        command,
        check=True,
    )


def consume_events() -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            "lark-cli",
            "event",
            "consume",
            "im.message.receive_v1",
            "--as",
            "bot",
            "--quiet",
            "--jq",
            'select(.message_type=="text")',
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def pipe_stderr(process: subprocess.Popen[str]) -> None:
    if process.stderr is None:
        return
    for line in process.stderr:
        line = line.strip()
        if line:
            log(f"event consumer: {line}")


def log(message: str) -> None:
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), message, flush=True)


def request_stop(_signum: int, _frame: object) -> None:
    global STOP
    STOP = True
    log("Stop requested.")
    if CURRENT_PROCESS and CURRENT_PROCESS.poll() is None:
        CURRENT_PROCESS.terminate()


class EventDeduper:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl_seconds = ttl_seconds
        self._events: dict[str, float] = {}

    def seen(self, event_id: str) -> bool:
        now = time.monotonic()
        expired = [key for key, seen_at in self._events.items() if now - seen_at > self.ttl_seconds]
        for key in expired:
            del self._events[key]
        if event_id in self._events:
            return True
        self._events[event_id] = now
        return False


def should_ignore_event(event: dict[str, object]) -> bool:
    sender_id = str(event.get("sender_id") or "")
    ignored_senders = {
        item.strip()
        for item in os.environ.get("FEISHU_IGNORE_SENDER_IDS", "").split(",")
        if item.strip()
    }
    return bool(sender_id and sender_id in ignored_senders)


def run_consumer(deduper: EventDeduper) -> None:
    global CURRENT_PROCESS
    process = consume_events()
    CURRENT_PROCESS = process
    threading.Thread(target=pipe_stderr, args=(process,), daemon=True).start()

    if process.stdout is None:
        raise RuntimeError("event consumer stdout is not available")

    try:
        for line in process.stdout:
            if STOP:
                break
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                log(f"skip non-json event line: {line}")
                continue

            event_id = str(event.get("event_id") or event.get("id") or "")
            message_id = str(event.get("message_id") or event.get("id") or "")
            content = str(event.get("content") or "").strip()

            if should_ignore_event(event):
                log(f"skip ignored sender for message {message_id}")
                continue
            if not event_id or not message_id or not content:
                log(f"skip incomplete event: {event}")
                continue
            if deduper.seen(event_id):
                continue

            log(f"received message {message_id}")
            try:
                t0 = time.monotonic()
                answer = chat_completion(content)
                elapsed = time.monotonic() - t0
                reply_to_message(message_id, answer, event_id)
                log(f"replied to {message_id} ({elapsed:.1f}s)")
            except Exception as exc:
                log(f"failed to handle {message_id}: {exc}")
                try:
                    reply_to_message(message_id, "处理失败：Agent 暂时无法生成回复，请稍后再试。", event_id + "-error")
                except Exception as reply_exc:
                    log(f"failed to send error reply: {reply_exc}")
        code = process.poll()
        log(f"event consumer exited with code {code}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
        if CURRENT_PROCESS is process:
            CURRENT_PROCESS = None


def main() -> int:
    load_env(ENV_PATH)
    if not (os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL")):
        raise RuntimeError("Missing required environment variable: LLM_BASE_URL (or OPENAI_BASE_URL)")
    if not (os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")):
        raise RuntimeError("Missing required environment variable: LLM_API_KEY (or OPENAI_API_KEY)")
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    base_url = (os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "").strip()
    model = os.environ.get("LLM_MODEL") or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    api_type = "Anthropic" if _is_anthropic_api(base_url) else "OpenAI"
    log(f"Starting Feishu local agent... (API={api_type}, model={model})")
    deduper = EventDeduper(env_int("FEISHU_EVENT_DEDUP_TTL_SECONDS", 3600))
    restart_delay = env_int("FEISHU_RESTART_DELAY_SECONDS", 5)
    while not STOP:
        run_consumer(deduper)
        if not STOP:
            log(f"Restarting event consumer in {restart_delay}s...")
            time.sleep(restart_delay)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        log("Stopped.")
        raise SystemExit(0)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
