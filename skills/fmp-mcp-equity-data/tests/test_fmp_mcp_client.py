import importlib.util
import json
import os
import ssl
import tempfile
import unittest
from argparse import Namespace
from io import BytesIO, StringIO
from pathlib import Path
from urllib.error import HTTPError, URLError
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

    def test_connection_url_defaults_to_placeholder(self):
        args = Namespace(show_key=False, redacted=False)
        with patch("sys.stdout", new_callable=StringIO) as stdout:
            client_module.command_connection_url(args)
        self.assertEqual(stdout.getvalue().strip(), client_module.MCP_URL_PLACEHOLDER)

    def test_connection_url_can_be_redacted(self):
        args = Namespace(show_key=False, redacted=True)
        with patch("sys.stdout", new_callable=StringIO) as stdout:
            client_module.command_connection_url(args)
        self.assertEqual(stdout.getvalue().strip(), client_module.MCP_URL_REDACTED)

    def test_connection_url_requires_explicit_show_key_for_full_url(self):
        args = Namespace(show_key=True, redacted=False)
        with patch.dict(os.environ, {"FMP_MCP_API_KEY": "secret-key"}, clear=True), patch(
            "sys.stdout", new_callable=StringIO
        ) as stdout:
            client_module.command_connection_url(args)
        self.assertEqual(
            stdout.getvalue().strip(),
            "https://financialmodelingprep.com/mcp?apikey=secret-key",
        )

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
            self.assertEqual(client.headers["User-Agent"], client_module.USER_AGENT)
            self.assertEqual(
                [tool["name"] for tool in client.list_tools()],
                ["first", "second"],
            )

    def test_http_post_retries_retryable_http_status(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append((request, timeout))
            if len(calls) == 1:
                raise HTTPError(
                    request.full_url,
                    503,
                    "Service Unavailable",
                    {"Content-Type": "text/plain"},
                    BytesIO(b"temporary"),
                )

            class FakeResponse:
                status = 200
                headers = {"Content-Type": "application/json"}

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, traceback):
                    return False

                def read(self):
                    return b'{"ok": true}'

            return FakeResponse()

        with patch.object(client_module, "urlopen", side_effect=fake_urlopen), patch.object(
            client_module.time, "sleep"
        ) as sleep:
            response = client_module.http_post(
                "https://example.test/mcp",
                {"User-Agent": client_module.USER_AGENT},
                {"jsonrpc": "2.0"},
                timeout=10,
                max_retries=1,
                backoff_seconds=0,
            )

        self.assertEqual(response.status, 200)
        self.assertEqual(len(calls), 2)
        sleep.assert_called_once_with(0)

    def test_http_post_retries_tls_eof_url_error(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append((request, timeout))
            if len(calls) == 1:
                raise URLError(ssl.SSLError("UNEXPECTED_EOF_WHILE_READING"))

            class FakeResponse:
                status = 200
                headers = {"Content-Type": "application/json"}

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, traceback):
                    return False

                def read(self):
                    return b'{"ok": true}'

            return FakeResponse()

        with patch.object(client_module, "urlopen", side_effect=fake_urlopen), patch.object(
            client_module.time, "sleep"
        ):
            response = client_module.http_post(
                "https://example.test/mcp",
                {"User-Agent": client_module.USER_AGENT},
                {"jsonrpc": "2.0"},
                timeout=10,
                max_retries=1,
                backoff_seconds=0,
            )

        self.assertEqual(response.status, 200)
        self.assertEqual(len(calls), 2)

    def test_initialize_rejects_unsupported_protocol_version(self):
        response = client_module.HttpResponse(
            status=200,
            headers={"content-type": "application/json", "mcp-session-id": "s1"},
            text=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {"protocolVersion": "2024-11-05"},
                }
            ),
        )

        with patch.object(client_module, "http_post", return_value=response) as post:
            client = client_module.FmpMcpClient("k")
            with self.assertRaisesRegex(RuntimeError, "Unsupported MCP protocol version"):
                client.initialize()
            self.assertEqual(post.call_count, 1)
            self.assertIsNone(client.session_id)

    def test_request_recovers_once_from_expired_session_404(self):
        calls = []
        responses = [
            client_module.HttpResponse(status=404, headers={}, text="expired"),
            client_module.HttpResponse(
                status=200,
                headers={"content-type": "application/json", "mcp-session-id": "new"},
                text=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {"protocolVersion": client_module.PROTOCOL_VERSION},
                    }
                ),
            ),
            client_module.HttpResponse(status=202, headers={}, text=""),
            client_module.HttpResponse(
                status=200,
                headers={"content-type": "application/json"},
                text=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"tools": [{"name": "quote"}]},
                    }
                ),
            ),
        ]

        def fake_post(url, headers, payload, timeout):
            calls.append((headers, payload))
            return responses.pop(0)

        with patch.object(client_module, "http_post", side_effect=fake_post):
            client = client_module.FmpMcpClient("k")
            client.session_id = "old"
            self.assertEqual(client.list_tools(), [{"name": "quote"}])

        self.assertEqual(calls[0][0]["Mcp-Session-Id"], "old")
        self.assertNotIn("Mcp-Session-Id", calls[1][0])
        self.assertEqual(calls[2][0]["Mcp-Session-Id"], "new")
        self.assertEqual(calls[3][0]["Mcp-Session-Id"], "new")
        self.assertEqual(calls[3][1]["id"], 1)

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

    def test_extract_tool_result_returns_successful_plain_text(self):
        result = {
            "result": {
                "content": [{"type": "text", "text": "successful plain text"}],
            }
        }
        self.assertEqual(client_module.extract_tool_result(result), "successful plain text")

    def test_coerce_value_preserves_leading_zero_identifiers(self):
        self.assertEqual(client_module.coerce_value("000123"), "000123")
        self.assertEqual(client_module.coerce_value("123"), 123)
        self.assertEqual(client_module.coerce_value("12.5"), 12.5)
        self.assertIs(client_module.coerce_value("true"), True)

    def test_init_config_force_creates_backup_before_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            default = tmp_path / "credentials.json"
            example = tmp_path / "credentials.example.json"
            default.write_text(json.dumps({"fmp_api_key": "real-key"}), encoding="utf-8")
            example.write_text(
                json.dumps({"fmp_api_key": client_module.PLACEHOLDER}),
                encoding="utf-8",
            )
            with patch.object(client_module, "DEFAULT_CONFIG_PATH", default), patch.object(
                client_module, "EXAMPLE_CONFIG_PATH", example
            ):
                client_module.init_config(force=True)

            backup = tmp_path / "credentials.json.bak"
            self.assertEqual(
                json.loads(backup.read_text(encoding="utf-8"))["fmp_api_key"],
                "real-key",
            )
            self.assertEqual(
                json.loads(default.read_text(encoding="utf-8"))["fmp_api_key"],
                client_module.PLACEHOLDER,
            )


@unittest.skipUnless(
    os.environ.get("FMP_INTEGRATION_TEST") == "1",
    "Set FMP_INTEGRATION_TEST=1 to run live FMP MCP checks.",
)
class FmpMcpIntegrationTests(unittest.TestCase):
    def test_live_tool_discovery_and_quote(self):
        client = client_module.FmpMcpClient(client_module.load_api_key(), timeout=60)
        client.initialize()

        tools = client.list_tools()
        self.assertTrue(any(tool.get("name") == "quote" for tool in tools))

        quote = client.call_tool("quote", {"endpoint": "quote", "symbol": "AAPL"})
        self.assertIsInstance(quote, list)
        self.assertEqual(quote[0]["symbol"], "AAPL")


if __name__ == "__main__":
    unittest.main()
