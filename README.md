# FMP MCP Equity Data

Direct Financial Modeling Prep MCP integration for US equity analysis. This skill helps an AI assistant fetch stock prices, quotes, financial statements, ratios, metrics, company profiles, sector and industry data, peers, analyst data, calendars, and other FMP MCP endpoints without relying on third-party data wrappers.

## Install

Clone this repository into your assistant application's skills directory.

```bash
git clone git@github.com:syuio/fmp-mcp-equity-data.git <SKILLS_DIR>/fmp-mcp-equity-data
```

Replace `<SKILLS_DIR>` with the skills directory used by your application, such as a local skills folder configured for ChatGPT, Claude, or another AI assistant.

## Configure The FMP API Key

Open the bundled key file:

```bash
nano <SKILLS_DIR>/fmp-mcp-equity-data/config/credentials.json
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
chmod 600 <SKILLS_DIR>/fmp-mcp-equity-data/config/credentials.json
```

Do not commit a real API key back to GitHub.

If you installed the skill from a Git checkout and edited the bundled placeholder file, you can reduce accidental commits with:

```bash
git update-index --skip-worktree config/credentials.json
```

## Optional Key Locations

The client checks key sources in this order:

1. `FMP_MCP_API_KEY`
2. `FMP_API_KEY`
3. `FMP_MCP_CONFIG`, pointing to a JSON file with `fmp_api_key`
4. `~/.config/fmp-mcp-equity-data/credentials.json`
5. Bundled `config/credentials.json`

The bundled `config/credentials.json` exists so users only need to replace the placeholder, not create the file manually.

## Requirements

The helper script requires Python with `requests` installed.

```bash
python -m pip install requests
```

## Verify

From the skill directory:

```bash
python scripts/fmp_mcp_client.py check-key
python scripts/fmp_mcp_client.py list-tools --query quote
python scripts/fmp_mcp_client.py call quote --arg endpoint=quote --arg symbol=NVDA
```

## Examples

Latest quote:

```bash
python scripts/fmp_mcp_client.py call quote --arg endpoint=quote --arg symbol=NVDA
```

Annual income statements:

```bash
python scripts/fmp_mcp_client.py call statements --arg endpoint=income-statement --arg symbol=NVDA --arg period=annual --arg limit=4
```

Quarterly balance sheets:

```bash
python scripts/fmp_mcp_client.py call statements --arg endpoint=balance-sheet-statement --arg symbol=NVDA --arg period=quarter --arg limit=4
```

Historical prices:

```bash
python scripts/fmp_mcp_client.py call chart --arg endpoint=historical-price-eod-full --arg symbol=NVDA --arg from_date=2026-01-01 --arg to_date=2026-07-24
```
