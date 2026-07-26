# FMP MCP Endpoint Selection

Use this as a starting map. Always prefer `scripts/fmp_mcp_client.py list-tools --query <topic>` for the current server's live tool list because FMP MCP can add or rename endpoints.

## Core MCP Commands

```bash
python scripts/fmp_mcp_client.py list-tools --query statements
python scripts/fmp_mcp_client.py describe-tool statements
python scripts/fmp_mcp_client.py call statements --arg endpoint=income-statement --arg symbol=NVDA --arg period=quarter --arg limit=4
```

## Common Tools And Endpoints

| Need | Tool | Endpoint examples | Notes |
|---|---|---|---|
| Historical prices | `chart` | `historical-price-eod-full`, `historical-price-eod-light`, `historical-price-eod-dividend-adjusted`, intraday endpoints | Use `from_date` and `to_date` when needed. |
| Income statement | `statements` | `income-statement`, `as-reported-income-statements` | Use `period=annual` or `period=quarter`. |
| Balance sheet | `statements` | `balance-sheet-statement`, `as-reported-balance-statements` | Use `period=annual` or `period=quarter`. |
| Cash flow | `statements` | `cashflow-statement`, `as-reported-cashflow-statements` | Use `period=annual` or `period=quarter`. |
| Ratios/metrics | `statements` | endpoints containing `ratios`, `key-metrics`, `enterprise-values`, `financial-scores` | Run `describe-tool statements` for exact endpoint names. |
| Earnings calendar | `calendar` | `earnings-company`, `earnings-calendar` | Use symbol or date range. |
| Dividends/splits | `calendar` | `dividends-company`, `splits-company` | Use symbol. |
| Analyst data | `analyst` | `grades`, `ratings-snapshot`, `price-target-consensus`, `financial-estimates` | Some endpoints may be subscription gated. |
| Sector/industry performance | `marketPerformance` | `historical-sector-performance`, `historical-industry-performance`, `sector-PE-snapshot`, `industry-PE-snapshot` | Some endpoints require sector/industry names or date. |
| Directories | `directory` | `available-sectors`, `available-industries`, `company-symbols-list`, `financial-symbols-list` | Useful for validating inputs. |

## Common Derived Metrics

- Gross margin = `grossProfit / revenue`
- Operating margin = `operatingIncome / revenue`
- Net margin = `netIncome / revenue`
- Inventory to revenue = `inventory / revenue`
- Inventory to total assets = `inventory / totalAssets`
- Inventory to current assets = `inventory / totalCurrentAssets`

Keep numerator and denominator columns in final tables when the user may audit the math.
