# Strategy Tearsheet Report

[Chinese README](README.md) | English

This skill turns a NAV or periodic-return series into a reproducible performance
tearsheet. It reports annualized return and volatility, Sharpe/Sortino/Calmar/Omega,
drawdowns, rolling metrics, monthly and annual returns, distribution statistics, and
optional benchmark-relative measures.

## Quick start

```bash
pip install -r requirements.txt
python examples/run_demo.py
python scripts/tearsheet.py --nav nav.csv --ppy 252 --rf 0.02 \
  --out tearsheet.json --html tearsheet.html
```

Input is `date,nav` or `date,return`. A fund or benchmark symbol can optionally be
resolved through the Pandadata adapter. The output is JSON plus a self-contained HTML
dashboard; missing dates, short histories, and unavailable sources are disclosed.

## Calculation boundary

Metrics are computed from the supplied series and stated annualization, risk-free-rate,
and benchmark assumptions. Historical results describe the input window and do not
predict future results. Outputs are for research and education only; this project does
not place orders and is not investment advice.

## License

GPL-3.0-only. See [LICENSE](LICENSE).
