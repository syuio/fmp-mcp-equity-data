#!/usr/bin/env python3
"""Small standard-library JSON-RPC client for FMP's remote MCP server."""

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MCP_URL_TEMPLATE = "https://financialmodelingprep.com/mcp?apikey={api_key}"
PROTOCOL_VERSION = "2025-03-26"
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "fmp-mcp-equity-data" / "credentials.json"
EXAMPLE_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "credentials.example.json"
)
PLACEHOLDER = "REPLACE_WITH_YOUR_FMP_API_KEY"


@dataclass
class HttpResponse:
    status: int
    headers: Dict[str, str]
    text: str


class McpToolError(RuntimeError):
    """Raised when a MCP tool returns isError=true."""


def load_api_key() -> str:
    """Load FMP key from environment or an external config file."""
    env_key = os.environ.get("FMP_MCP_API_KEY") or os.environ.get("FMP_API_KEY")
    if env_key:
        return env_key

    settings_path = Path(os.environ.get("FMP_MCP_CONFIG", DEFAULT_CONFIG_PATH))
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(
            "FMP key not found. Set FMP_MCP_API_KEY, set FMP_API_KEY, set "
            f"FMP_MCP_CONFIG, or run init-config to create {settings_path}."
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Could not parse {settings_path}: {exc}") from exc

    key = settings.get("fmp_api_key")
    if not key:
        raise SystemExit(f"FMP key not found in {settings_path}: missing fmp_api_key.")
    if PLACEHOLDER in key:
        raise SystemExit(f"FMP key placeholder has not been replaced in {settings_path}.")
    return key


def init_config(force: bool = False) -> Path:
    """Create the default external config file from the bundled example."""
    if not EXAMPLE_CONFIG_PATH.exists():
        raise SystemExit(f"Missing example config: {EXAMPLE_CONFIG_PATH}")
    DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DEFAULT_CONFIG_PATH.exists() and not force:
        raise SystemExit(
            f"Config already exists: {DEFAULT_CONFIG_PATH}. Use --force to overwrite."
        )
    shutil.copyfile(EXAMPLE_CONFIG_PATH, DEFAULT_CONFIG_PATH)
    DEFAULT_CONFIG_PATH.chmod(0o600)
    return DEFAULT_CONFIG_PATH


def http_post(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    timeout: int,
) -> HttpResponse:
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            return HttpResponse(
                status=response.status,
                headers={key.lower(): value for key, value in response.headers.items()},
                text=text,
            )
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return HttpResponse(
            status=exc.code,
            headers={key.lower(): value for key, value in exc.headers.items()},
            text=text,
        )
    except URLError as exc:
        raise RuntimeError(f"MCP network request failed: {exc}") from exc


def parse_json_response(text: str) -> Dict[str, Any]:
    result = json.loads(text)
    if not isinstance(result, dict):
        raise RuntimeError("MCP JSON response was not an object.")
    return result


def parse_sse_events(text: str) -> List[Dict[str, Any]]:
    """Parse text/event-stream data into JSON payload objects."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    events: List[Dict[str, Any]] = []
    for block in re.split(r"\n{2,}", normalized.strip()):
        if not block:
            continue
        data_lines = []
        for line in block.split("\n"):
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            continue
        raw = "\n".join(data_lines)
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise RuntimeError("MCP SSE data payload was not an object.")
        events.append(parsed)
    return events


def parse_mcp_response(response: HttpResponse, expected_id: Optional[int]) -> Dict[str, Any]:
    """Parse JSON or SSE MCP responses and match the JSON-RPC request id."""
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type or response.text.startswith(("event:", "data:")):
        events = parse_sse_events(response.text)
        if not events:
            raise RuntimeError(f"No JSON data in event-stream response: {response.text[:500]}")
        if expected_id is not None:
            for event in events:
                if event.get("id") == expected_id:
                    return event
            raise RuntimeError(f"No MCP SSE response matched request id {expected_id}.")
        return events[-1]
    return parse_json_response(response.text)


class FmpMcpClient:
    """Minimal MCP Streamable HTTP client for FMP."""

    def __init__(self, api_key: str, timeout: int = 60):
        self.url = MCP_URL_TEMPLATE.format(api_key=api_key)
        self.timeout = timeout
        self.session_id: Optional[str] = None
        self.next_id = 1
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

    def _headers(self) -> Dict[str, str]:
        headers = dict(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def _post(self, payload: Dict[str, Any], parse_response: bool = True) -> Dict[str, Any]:
        response = http_post(self.url, self._headers(), payload, self.timeout)
        if response.status >= 400:
            raise RuntimeError(f"MCP request failed {response.status}: {response.text[:1000]}")
        self.session_id = response.headers.get("mcp-session-id") or self.session_id
        if not parse_response:
            return {}

        expected_id = payload.get("id") if isinstance(payload.get("id"), int) else None
        result = parse_mcp_response(response, expected_id)
        if result.get("error"):
            raise RuntimeError(json.dumps(result["error"], indent=2))
        return result

    def request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": self.next_id,
            "method": method,
            "params": params or {},
        }
        self.next_id += 1
        return self._post(payload)

    def initialize(self) -> Dict[str, Any]:
        result = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "fmp-mcp-equity-data-client", "version": "1.0.0"},
            },
        )
        self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            parse_response=False,
        )
        return result

    def list_tools(self) -> List[Dict[str, Any]]:
        tools: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            result = self.request("tools/list", params)
            payload = result.get("result", {})
            tools.extend(payload.get("tools", []))
            cursor = payload.get("nextCursor")
            if not cursor:
                return tools

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        result = self.request(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
        return extract_tool_result(result)


def content_text(result: Dict[str, Any]) -> str:
    content = result.get("content") or []
    texts = [
        item.get("text", "")
        for item in content
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    return "\n".join(texts)


def extract_tool_result(call_result: Dict[str, Any]) -> Any:
    """Extract structured data from a MCP tools/call result."""
    result = call_result.get("result", {})
    if result.get("isError") is True:
        message = content_text(result) or json.dumps(result, ensure_ascii=False)
        raise McpToolError(f"MCP tool error: {message}")

    for key in ("structuredContent", "structured_content"):
        if key in result:
            structured = result[key]
            if isinstance(structured, dict) and "data" in structured:
                return structured["data"]
            return structured

    raw = content_text(result)
    if not raw:
        return result
    parsed = json.loads(raw)
    if isinstance(parsed, dict) and "data" in parsed:
        return parsed["data"]
    return parsed


def parse_arg_values(values: Iterable[str]) -> Dict[str, Any]:
    args: Dict[str, Any] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--arg must be key=value, got: {value}")
        key, raw = value.split("=", 1)
        args[key] = coerce_value(raw)
    return args


def coerce_value(raw: str) -> Any:
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in ("none", "null"):
        return None
    if re.fullmatch(r"-?(0|[1-9][0-9]*)", raw):
        return int(raw)
    if re.fullmatch(r"-?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+(?:\.[0-9]*)?[eE][+-]?[0-9]+)", raw):
        return float(raw)
    return raw


def make_client(timeout: int) -> Tuple[FmpMcpClient, Dict[str, Any]]:
    client = FmpMcpClient(load_api_key(), timeout=timeout)
    init_result = client.initialize()
    return client, init_result


def command_check_key(_: argparse.Namespace) -> None:
    _ = load_api_key()
    print(json.dumps({"fmp_api_key_configured": True}, indent=2))


def command_init_config(args: argparse.Namespace) -> None:
    path = init_config(force=args.force)
    print(f"Created {path}. Replace {PLACEHOLDER} before using the skill.")


def command_config_path(_: argparse.Namespace) -> None:
    configured = os.environ.get("FMP_MCP_CONFIG")
    path = Path(configured) if configured else DEFAULT_CONFIG_PATH
    print(str(path))


def command_list_tools(args: argparse.Namespace) -> None:
    client, _ = make_client(args.timeout)
    tools = client.list_tools()
    if args.query:
        query = args.query.lower()
        tools = [
            tool
            for tool in tools
            if query
            in " ".join(
                [
                    tool.get("name", ""),
                    tool.get("title", ""),
                    tool.get("description", ""),
                ]
            ).lower()
        ]
    print(json.dumps(tools, indent=2, ensure_ascii=False))


def command_describe_tool(args: argparse.Namespace) -> None:
    client, _ = make_client(args.timeout)
    for tool in client.list_tools():
        if tool.get("name") == args.name:
            print(json.dumps(tool, indent=2, ensure_ascii=False))
            return
    raise SystemExit(f"Tool not found: {args.name}")


def command_call(args: argparse.Namespace) -> None:
    client, _ = make_client(args.timeout)
    result = client.call_tool(args.name, parse_arg_values(args.arg or []))
    print(json.dumps(result, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=60)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_key = subparsers.add_parser("check-key")
    check_key.set_defaults(func=command_check_key)

    init = subparsers.add_parser("init-config")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=command_init_config)

    config_path = subparsers.add_parser("config-path")
    config_path.set_defaults(func=command_config_path)

    list_tools = subparsers.add_parser("list-tools")
    list_tools.add_argument("--query", help="Filter tools by name, title, or description")
    list_tools.set_defaults(func=command_list_tools)

    describe = subparsers.add_parser("describe-tool")
    describe.add_argument("name")
    describe.set_defaults(func=command_describe_tool)

    call = subparsers.add_parser("call")
    call.add_argument("name", help="MCP tool name, e.g. statements")
    call.add_argument(
        "--arg",
        action="append",
        default=[],
        help="Tool argument as key=value. Repeat for multiple arguments.",
    )
    call.set_defaults(func=command_call)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
