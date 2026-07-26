---
name: fmp-mcp-equity-data
description: Direct Financial Modeling Prep MCP integration for US equity data retrieval. Use when an AI assistant needs direct FMP MCP data for a named ticker or explicit FMP data task, such as stock quotes, price history, financial statements, ratios, metrics, company profile, sector/industry data, peers, analyst data, or calendars; especially use when the user asks to avoid third-party wrappers.
---

# FMP MCP Equity Data

## Overview

Use Financial Modeling Prep's hosted remote MCP server directly for US equity data. Do not use third-party data wrappers or yfinance when this skill is triggered unless the user explicitly asks for them.

For MCP-compatible applications, prefer the official Remote MCP Server URL:

```text
https://financialmodelingprep.com/mcp?apikey=YOUR_FMP_API_KEY
```

The bundled script is a standard-library fallback for generating the connection URL, checking credentials, discovering tools, and making direct JSON-RPC calls when a native MCP client is unavailable. It sends a fixed `User-Agent` and retries transient TLS EOF, connection reset, HTTP 429, and HTTP 502/503/504 failures.

## Key Lookup

Use the first available key source:

1. Environment variable: `FMP_MCP_API_KEY`
2. Environment variable: `FMP_API_KEY`
3. Skill-specific config file set by `FMP_MCP_CONFIG`
4. Default skill-specific config file: `~/.config/fmp-mcp-equity-data/credentials.json`

Create the default external config file from the bundled example:

```bash
python3 scripts/fmp_mcp_client.py init-config
```

Then edit `~/.config/fmp-mcp-equity-data/credentials.json` and replace the placeholder value. The config file must be JSON:

```json
{
  "fmp_api_key": "REPLACE_WITH_YOUR_FMP_API_KEY"
}
```

Recommended permissions on Unix-like systems:

```bash
chmod 600 ~/.config/fmp-mcp-equity-data/credentials.json
```

Do not store a real API key in the skill repository. The bundled `config/credentials.example.json` is only a template.

Never print the key. Only report whether a key is present.

Exception: if the user explicitly asks for the full Remote MCP Server URL, run `python3 scripts/fmp_mcp_client.py connection-url --show-key` and warn that the URL contains their FMP API key.

## Quick Start

For a native MCP client, configure the remote server URL above in the client. To print the placeholder URL:

```bash
python3 scripts/fmp_mcp_client.py connection-url
```

To print the full URL from the configured key for copy/paste into a MCP-compatible app:

```bash
python3 scripts/fmp_mcp_client.py connection-url --show-key
```

Use direct tool calls only when a native MCP client is unavailable or when debugging.

List available MCP tools:

```bash
python3 scripts/fmp_mcp_client.py list-tools --query statements
```

Call an MCP tool:

```bash
python3 scripts/fmp_mcp_client.py call statements \
  --arg endpoint=income-statement \
  --arg symbol=NVDA \
  --arg period=quarter \
  --arg limit=4
```

Run with Python 3.9+:

```bash
python3 scripts/fmp_mcp_client.py call statements --arg endpoint=income-statement --arg symbol=NVDA --arg period=quarter --arg limit=4
```

## Workflow

1. Normalize ticker symbols to uppercase.
2. Confirm the FMP key is available without revealing it:
   `python3 scripts/fmp_mcp_client.py check-key`
3. For unfamiliar data needs, run `list-tools --query <topic>` and inspect tool descriptions/endpoints.
4. Call `tools/call` through the script with explicit endpoint arguments.
5. Use returned fields as provided by FMP MCP. For financial statements, expect native FMP field names such as `revenue`, `grossProfit`, `operatingIncome`, `netIncome`, `inventory`, `totalAssets`, and `totalCurrentAssets`.
6. If FMP returns a restricted endpoint/subscription error, stop and tell the user which FMP endpoint requires an upgraded plan or separate subscription.
7. When deriving metrics, state formulas and preserve raw period/date context.

## Common Data Routes

Read `references/endpoints.md` when selecting endpoints for a new analysis type or when the exact tool name is unclear.

Typical examples:

- Price history: tool `chart`, endpoint `historical-price-eod-full`
- Quote/profile: use `list-tools --query profile` or `list-tools --query quote`; choose the MCP tool that exposes the desired FMP endpoint
- Financial statements: tool `statements`, endpoints `income-statement`, `balance-sheet-statement`, `cashflow-statement`
- Ratios/metrics: tool `statements`, endpoints containing `ratios`, `key-metrics`, or `enterprise-values`
- Industry/sector/peers: use `marketPerformance`, `directory`, and peer/profile-related tools discovered by `list-tools`

## Output Guidance

Use compact tables for user-facing analysis. Include:

- Stock code
- Date/period
- Raw values needed to audit calculations
- Formula/metric definitions
- A clear note when data is unavailable due to subscription restrictions

Do not mention internal MCP handshake details unless the user asks how the data was retrieved.
