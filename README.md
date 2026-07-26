# FMP MCP Equity Data

Direct Financial Modeling Prep MCP integration for US equity analysis. This skill helps an AI assistant fetch stock prices, quotes, financial statements, ratios, metrics, company profiles, sector and industry data, peers, analyst data, calendars, and other FMP MCP endpoints without relying on third-party data wrappers.

## Install

Clone this repository into your assistant application's skills directory.

```bash
git clone git@github.com:syuio/fmp-mcp-equity-data.git <SKILLS_DIR>/fmp-mcp-equity-data
```

Replace `<SKILLS_DIR>` with the skills directory used by your application, such as a local skills folder configured for ChatGPT, Claude, or another AI assistant.

## Configure The FMP API Key

Create the external key file from the bundled example:

```bash
cd <SKILLS_DIR>/fmp-mcp-equity-data
python3 scripts/fmp_mcp_client.py init-config
```

Open the created key file:

```bash
nano ~/.config/fmp-mcp-equity-data/credentials.json
```

Replace only the placeholder value:

```json
{
  "fmp_api_key": "REPLACE_WITH_YOUR_FMP_API_KEY"
}
```

with your real FMP API key, keeping the JSON structure unchanged.

Then restrict file permissions on Unix-like systems:

```bash
chmod 600 ~/.config/fmp-mcp-equity-data/credentials.json
```

Do not commit a real API key back to GitHub. The repository only contains `config/credentials.example.json`; real keys should live in environment variables or external config.

If you need to recreate the external config, use:

```bash
python3 scripts/fmp_mcp_client.py init-config --force
```

When `--force` overwrites an existing config, the previous file is copied to `~/.config/fmp-mcp-equity-data/credentials.json.bak` first.

## Connect An MCP-Compatible App

FMP's hosted Remote MCP Server URL is:

```text
https://financialmodelingprep.com/mcp?apikey=YOUR_FMP_API_KEY
```

In an MCP-compatible app, add a custom remote MCP server and paste that URL with your actual FMP API key. For example, Claude-style connectors generally ask for a "Remote MCP Server URL"; Cursor and other MCP clients have equivalent remote server settings.

If you configured the key with this skill, you can print a placeholder URL:

```bash
python3 scripts/fmp_mcp_client.py connection-url
```

or explicitly print the full URL for copy/paste:

```bash
python3 scripts/fmp_mcp_client.py connection-url --show-key
```

The full URL contains your FMP API key. Treat it as a secret.

For custom Python agents, FMP's official docs show `fastmcp.Client` connecting to the same URL. The bundled script is only a no-dependency fallback and diagnostic helper.

## Optional Key Locations

The client checks key sources in this order:

1. `FMP_MCP_API_KEY`
2. `FMP_API_KEY`
3. `FMP_MCP_CONFIG`, pointing to a JSON file with `fmp_api_key`
4. `~/.config/fmp-mcp-equity-data/credentials.json`

The `init-config` command creates `~/.config/fmp-mcp-equity-data/credentials.json` from the bundled example so users do not need to create the file manually.

## Requirements

The helper script uses only Python's standard library. Use Python 3.9 or newer.

## Verify

From the skill directory:

```bash
python3 scripts/fmp_mcp_client.py check-key
python3 scripts/fmp_mcp_client.py connection-url --redacted
python3 scripts/fmp_mcp_client.py list-tools --query quote
python3 scripts/fmp_mcp_client.py call quote --arg endpoint=quote --arg symbol=NVDA
```

## Examples

Latest quote:

```bash
python3 scripts/fmp_mcp_client.py call quote --arg endpoint=quote --arg symbol=NVDA
```

Annual income statements:

```bash
python3 scripts/fmp_mcp_client.py call statements --arg endpoint=income-statement --arg symbol=NVDA --arg period=annual --arg limit=4
```

Quarterly balance sheets:

```bash
python3 scripts/fmp_mcp_client.py call statements --arg endpoint=balance-sheet-statement --arg symbol=NVDA --arg period=quarter --arg limit=4
```

Historical prices:

```bash
python3 scripts/fmp_mcp_client.py call chart --arg endpoint=historical-price-eod-full --arg symbol=NVDA --arg from_date=2026-01-01 --arg to_date=2026-07-24
```
