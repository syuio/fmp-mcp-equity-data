#!/usr/bin/env python3
"""Small JSON-RPC client for Financial Modeling Prep's remote MCP server."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import requests
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: requests. Run with a Python environment that has requests installed."
    ) from exc


MCP_URL_TEMPLATE = "https://financialmodelingprep.com/mcp?apikey={api_key}"
PROTOCOL_VERSION = "2025-03-26"
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "fmp-mcp-equity-data" / "credentials.json"
SKILL_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "credentials.json"


def load_api_key() -> str:
    """Load FMP key from environment or the skill-specific config file."""
    env_key = os.environ.get("FMP_MCP_API_KEY") or os.environ.get("FMP_API_KEY")
    if env_key:
        return env_key

    config_paths = []
    if os.environ.get("FMP_MCP_CONFIG"):
        config_paths.append(Path(os.environ["FMP_MCP_CONFIG"]))
    config_paths.extend([DEFAULT_CONFIG_PATH, SKILL_CONFIG_PATH])

    missing_paths = []
    for settings_path in config_paths:
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            missing_paths.append(str(settings_path))
            continue
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Could not parse {settings_path}: {exc}") from exc

        key = settings.get("fmp_api_key")
        if key and "REPLACE_WITH_YOUR_FMP_API_KEY" not in key:
            return key

        raise SystemExit(
            "FMP key placeholder has not been replaced. Edit "
            f"{settings_path} and replace REPLACE_WITH_YOUR_FMP_API_KEY."
        )

    searched = ", ".join(missing_paths)
    raise SystemExit(
        "FMP key not found. Set FMP_MCP_API_KEY, set FMP_API_KEY, set "
        "FMP_MCP_CONFIG, or edit the bundled config/credentials.json. "
        f"Searched: {searched}"
    )


def parse_mcp_response(response: requests.Response) -> Dict[str, Any]:
    """Parse JSON or text/event-stream MCP responses."""
    text = response.text
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type or text.startswith(("event:", "data:")):
        events: List[Dict[str, Any]] = []
        for block in text.split("\n\n"):
            data_lines = [
                line[5:].strip() for line in block.splitlines() if line.startswith("data:")
            ]
            if data_lines:
                events.append(json.loads("\n".join(data_lines)))
        if not events:
            raise RuntimeError(f"No JSON data in event-stream response: {text[:500]}")
        return events[-1]
    return response.json()


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

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = dict(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        response = requests.post(
            self.url, headers=headers, json=payload, timeout=self.timeout
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"MCP request failed {response.status_code}: {response.text[:1000]}"
            )
        self.session_id = response.headers.get("mcp-session-id") or self.session_id
        result = parse_mcp_response(response)
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
        headers = dict(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        response = requests.post(
            self.url,
            headers=headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                "MCP initialized notification failed "
                f"{response.status_code}: {response.text[:1000]}"
            )
        return result

    def list_tools(self) -> List[Dict[str, Any]]:
        result = self.request("tools/list")
        return result["result"]["tools"]

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        result = self.request(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
        return extract_tool_result(result)


def extract_tool_result(call_result: Dict[str, Any]) -> Any:
    """Extract structured data from a MCP tools/call result."""
    result = call_result.get("result", {})
    for key in ("structuredContent", "structured_content"):
        if key in result:
            structured = result[key]
            if isinstance(structured, dict) and "data" in structured:
                return structured["data"]
            return structured

    content = result.get("content") or []
    texts = [
        item.get("text", "")
        for item in content
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    raw = "\n".join(texts)
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
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def make_client(timeout: int) -> Tuple[FmpMcpClient, Dict[str, Any]]:
    client = FmpMcpClient(load_api_key(), timeout=timeout)
    init_result = client.initialize()
    return client, init_result


def command_check_key(_: argparse.Namespace) -> None:
    _ = load_api_key()
    print(json.dumps({"fmp_api_key_configured": True}, indent=2))


def command_config_path(_: argparse.Namespace) -> None:
    configured = os.environ.get("FMP_MCP_CONFIG")
    paths = [Path(configured)] if configured else [DEFAULT_CONFIG_PATH, SKILL_CONFIG_PATH]
    print(json.dumps([str(path) for path in paths], indent=2))


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
