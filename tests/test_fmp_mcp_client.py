import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fmp_mcp_client.py"
SPEC = importlib.util.spec_from_file_location("fmp_mcp_client", MODULE_PATH)
client_module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(client_module)


class FmpMcpClientTests(unittest.TestCase):
    def test_help_does_not_require_external_dependencies(self):
        parser = client_module.build_parser()
        help_text = parser.format_help()
        self.assertIn("check-key", help_text)

    def test_load_api_key_prefers_fmp_mcp_env(self):
        with patch.dict(
            os.environ,
            {"FMP_MCP_API_KEY": "primary", "FMP_API_KEY": "secondary"},
            clear=True,
        ):
            self.assertEqual(client_module.load_api_key(), "primary")

    def test_load_api_key_from_explicit_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credentials.json"
            path.write_text(json.dumps({"fmp_api_key": "from-file"}), encoding="utf-8")
            with patch.dict(os.environ, {"FMP_MCP_CONFIG": str(path)}, clear=True):
                self.assertEqual(client_module.load_api_key(), "from-file")

    def test_placeholder_config_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credentials.json"
            path.write_text(
                json.dumps({"fmp_api_key": client_module.PLACEHOLDER}),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"FMP_MCP_CONFIG": str(path)}, clear=True):
                with self.assertRaises(SystemExit):
                    client_module.load_api_key()

    def test_sse_parser_handles_crlf_and_matches_request_id(self):
        response = client_module.HttpResponse(
            status=200,
            headers={"content-type": "text/event-stream"},
            text=(
                'event: message\r\n'
                'data: {"jsonrpc":"2.0","id":1,"result":{"ignored":true}}\r\n'
                "\r\n"
                'event: message\r\n'
                'data: {"jsonrpc":"2.0","id":2,"result":{"ok":true}}\r\n'
                "\r\n"
            ),
        )
        parsed = client_module.parse_mcp_response(response, expected_id=2)
        self.assertEqual(parsed["result"], {"ok": True})

    def test_sse_parser_raises_when_id_missing(self):
        response = client_module.HttpResponse(
            status=200,
            headers={"content-type": "text/event-stream"},
            text='data: {"jsonrpc":"2.0","id":1,"result":{}}\n\n',
        )
        with self.assertRaisesRegex(RuntimeError, "matched request id 2"):
            client_module.parse_mcp_response(response, expected_id=2)

    def test_list_tools_paginates(self):
        responses = [
            client_module.HttpResponse(
                status=200,
                headers={"content-type": "application/json"},
                text=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"tools": [{"name": "first"}], "nextCursor": "n1"},
                    }
                ),
            ),
            client_module.HttpResponse(
                status=200,
                headers={"content-type": "application/json"},
                text=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {"tools": [{"name": "second"}]},
                    }
                ),
            ),
        ]

        def fake_post(url, headers, payload, timeout):
            self.assertEqual(url, "https://financialmodelingprep.com/mcp?apikey=k")
            return responses.pop(0)

        with patch.object(client_module, "http_post", side_effect=fake_post):
            client = client_module.FmpMcpClient("k")
            self.assertEqual(
                [tool["name"] for tool in client.list_tools()],
                ["first", "second"],
            )

    def test_extract_tool_result_raises_on_is_error(self):
        result = {
            "result": {
                "isError": True,
                "content": [{"type": "text", "text": "Restricted Endpoint"}],
            }
        }
        with self.assertRaisesRegex(client_module.McpToolError, "Restricted Endpoint"):
            client_module.extract_tool_result(result)

    def test_extract_tool_result_prefers_structured_content_data(self):
        result = {"result": {"structuredContent": {"data": [{"symbol": "NVDA"}]}}}
        self.assertEqual(client_module.extract_tool_result(result), [{"symbol": "NVDA"}])

    def test_coerce_value_preserves_leading_zero_identifiers(self):
        self.assertEqual(client_module.coerce_value("000123"), "000123")
        self.assertEqual(client_module.coerce_value("123"), 123)
        self.assertEqual(client_module.coerce_value("12.5"), 12.5)
        self.assertIs(client_module.coerce_value("true"), True)


if __name__ == "__main__":
    unittest.main()
