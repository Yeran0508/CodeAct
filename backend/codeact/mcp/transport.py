from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from collections.abc import Mapping
from typing import Any, Protocol

from codeact.mcp.models import McpServerConfig


class McpTransportError(RuntimeError):
    pass


class McpProtocolError(RuntimeError):
    pass


class JsonRpcTransport(Protocol):
    def request(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]: ...

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None: ...

    def close(self) -> None: ...


class StdioJsonRpcTransport:
    """Newline-delimited JSON-RPC 2.0 over an allowlisted subprocess."""

    def __init__(self, config: McpServerConfig) -> None:
        self.config = config
        environment = {"PATH": os.environ.get("PATH", "")}
        environment.update(config.env)
        self._process = subprocess.Popen(
            [config.command, *config.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=False,
            env=environment,
            bufsize=0,
        )
        self._messages: queue.Queue[dict[str, Any] | BaseException] = queue.Queue()
        self._pending: dict[int, dict[str, Any]] = {}
        self._next_id = 1
        self._write_lock = threading.Lock()
        self._reader = threading.Thread(target=self._read_messages, daemon=True)
        self._reader.start()

    def _read_messages(self) -> None:
        assert self._process.stdout is not None
        try:
            while line := self._process.stdout.readline(self.config.max_message_bytes + 1):
                if len(line) > self.config.max_message_bytes:
                    raise McpTransportError("MCP message exceeds configured byte limit")
                try:
                    message = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError) as error:
                    raise McpProtocolError("MCP server emitted invalid JSON") from error
                if not isinstance(message, dict):
                    raise McpProtocolError("MCP message must be a JSON object")
                self._messages.put(message)
        except BaseException as error:
            self._messages.put(error)

    def _write(self, message: Mapping[str, Any]) -> None:
        if self._process.poll() is not None:
            raise McpTransportError("MCP server process is not running")
        assert self._process.stdin is not None
        encoded = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"
        if len(encoded) > self.config.max_message_bytes:
            raise McpTransportError("MCP request exceeds configured byte limit")
        with self._write_lock:
            self._process.stdin.write(encoded)
            self._process.stdin.flush()

    def _next_message(self) -> dict[str, Any]:
        try:
            message = self._messages.get(timeout=self.config.request_timeout_seconds)
        except queue.Empty as error:
            raise McpTransportError("MCP request timed out") from error
        if isinstance(message, BaseException):
            raise McpTransportError("MCP reader failed") from message
        return message

    def request(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._write(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)}
        )
        if request_id in self._pending:
            return self._validate_response(self._pending.pop(request_id), request_id)
        while True:
            message = self._next_message()
            if message.get("method") == "ping" and "id" in message:
                self._write({"jsonrpc": "2.0", "id": message["id"], "result": {}})
                continue
            response_id = message.get("id")
            if isinstance(response_id, int) and response_id != request_id:
                self._pending[response_id] = message
                continue
            return self._validate_response(message, request_id)

    @staticmethod
    def _validate_response(message: dict[str, Any], request_id: int) -> dict[str, Any]:
        if message.get("jsonrpc") != "2.0" or message.get("id") != request_id:
            raise McpProtocolError("invalid JSON-RPC response envelope")
        if "error" in message:
            raise McpProtocolError(f"MCP error response: {message['error']}")
        result = message.get("result")
        if not isinstance(result, dict):
            raise McpProtocolError("MCP response result must be an object")
        return result

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = dict(params)
        self._write(message)

    def close(self) -> None:
        if self._process.stdin is not None:
            self._process.stdin.close()
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)
