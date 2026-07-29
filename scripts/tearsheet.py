#!/usr/bin/env python3
"""
tearsheet.py — 策略绩效 tearsheet CLI 入口

典型用法:
  # 从净值 CSV（date,nav）生成
  python scripts/tearsheet.py --nav nav.csv --ppy 252 \
      --out tearsheet.json --html tearsheet.html

  # 从收益 CSV（date,return）+ 基准指数
  python scripts/tearsheet.py --returns ret.csv --benchmark 000300.SH \
      --ppy 252 --rf 0.02 --out t.json --html t.html

  # 只给基金代码，用 get_fund_daily 收盘价构造净值代理（需 panda_data SDK）
  python scripts/tearsheet.py --fund 110011.OF --start 20240101 --end 20241231

数据接入三层回退见 data_source.py；核心指标不依赖 Pandadata，
用户直接传 CSV 即可离线跑通。
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_source import DataSource   # noqa: E402
import metrics                        # noqa: E402
import render                         # noqa: E402


# ---------------------------------------------------------------------------
# CSV / 数据源 → returns Series
# ---------------------------------------------------------------------------
def _read_series_csv(path: str) -> tuple[pd.Series, str]:
    """读 CSV，自动识别 nav 或 return 列，返回 (returns, kind)。"""
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    date_col = cols.get("date") or df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col).set_index(date_col)

    if "nav" in cols:
        nav = df[cols["nav"]].astype(float)
        return metrics.nav_to_returns(nav), "nav"
    if "return" in cols:
        return df[cols["return"]].astype(float).dropna(), "return"
    if "ret" in cols:
        return df[cols["ret"]].astype(float).dropna(), "return"
    # 兜底：取第一个数值列当净值
    val_col = df.select_dtypes("number").columns[0]
    return metrics.nav_to_returns(df[val_col].astype(float)), "nav"


def _rows_to_nav(rows: list[dict]) -> pd.Series:
    """基金净值接口返回 → 净值 Series（优先 nav/unit_nav/close 字段）。"""
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows)
    date_col = next((c for c in ("date", "trade_date", "nav_date") if c in df.columns), None)
    val_col = next((c for c in ("nav", "unit_nav", "adj_nav", "accum_nav", "close")
                    if c in df.columns), None)
    if date_col is None or val_col is None:
        return pd.Series(dtype=float)
    df[date_col] = pd.to_datetime(df[date_col].astype(str), format="mixed", errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col)
    return pd.Series(df[val_col].astype(float).values,
                     index=pd.DatetimeIndex(df[date_col].values))


def _index_rows_to_returns(rows: list[dict]) -> pd.Series:
    """指数日线 → 收益 Series（用 close）。"""
    nav = _rows_to_nav(rows)
    if len(nav) == 0:
        return pd.Series(dtype=float)
    return metrics.nav_to_returns(nav)


def build_tearsheet(returns: pd.Series, ppy: int, rf_annual: float,
                    bench_returns: pd.Series | None, backend: str,
                    rolling_window: int | None = None) -> dict:
    t = metrics.compute_all(returns, ppy=ppy, rf_annual=rf_annual,
                            bench_returns=bench_returns,
                            rolling_window=rolling_window)
    t["backend"] = backend
    return t


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="策略绩效 tearsheet 生成器")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--nav", help="净值 CSV（date,nav）")
    src.add_argument("--returns", help="收益 CSV（date,return）")
    src.add_argument("--fund", help="基金代码（用 get_fund_daily 收盘价构造净值代理，需 SDK）")

    ap.add_argument("--benchmark", default=None, help="基准指数代码，如 000300.SH")
    ap.add_argument("--start", default="20200101", help="取数起始 YYYYMMDD（fund/benchmark 用）")
    ap.add_argument("--end", default="20251231", help="取数结束 YYYYMMDD")
    ap.add_argument("--ppy", type=int, default=252, help="年化期数（日252/周52/月12）")
    ap.add_argument("--rf", type=float, default=0.02, help="无风险利率(年化)")
    ap.add_argument("--rolling-window", type=int, default=None, help="滚动窗口期数")
    ap.add_argument("--prefer", choices=["sdk", "sample"], default=None)
    ap.add_argument("--out", default=None, help="JSON 输出路径")
    ap.add_argument("--html", default=None, help="HTML 看板输出路径")
    ap.add_argument("--title", default="策略绩效 Tearsheet")
    args = ap.parse_args()

    ds = DataSource(prefer=args.prefer)

    # 主序列
    if args.nav:
        returns, _ = _read_series_csv(args.nav)
    elif args.returns:
        returns, _ = _read_series_csv(args.returns)
    else:  # --fund
        rows = ds.fund_nav(args.fund, args.start, args.end)
        nav = _rows_to_nav(rows)
        if len(nav) == 0:
            print("未取到基金净值（检查 SDK 或改用 --nav/--returns）", file=sys.stderr)
            sys.exit(2)
        returns = metrics.nav_to_returns(nav)

    if len(returns) < 3:
        print("有效序列过短，无法计算绩效", file=sys.stderr)
        sys.exit(2)

    # 基准（可选）
    bench_returns = None
    degraded = list(ds.diagnostics)
    if args.benchmark:
        brows = ds.index_daily(args.benchmark, args.start, args.end)
        bench_returns = _index_rows_to_returns(brows)
        if len(bench_returns) == 0:
            print(f"[warn] 基准 {args.benchmark} 未取到数据，跳过相对分析", file=sys.stderr)
            degraded.append(f"基准 {args.benchmark} 未取到 get_index_daily 数据")
            bench_returns = None

    t = build_tearsheet(returns, args.ppy, args.rf, bench_returns,
                        ds.backend, args.rolling_window)
    degraded.extend(message for message in ds.diagnostics if message not in degraded)
    t["status"] = "degraded" if degraded else "ok"
    t["degraded"] = degraded
    t["sources"] = {
        "strategy": (
            "user_nav_csv" if args.nav else
            "user_returns_csv" if args.returns else
            "get_fund_daily"
        ),
        "benchmark": "get_index_daily" if args.benchmark else None,
    }

    # 控制台摘要
    print(render.build_summary_text(t))

    if args.out:
        Path(args.out).write_text(render.to_json(t), encoding="utf-8")
        print(f"\n[已写出 JSON] {Path(args.out).resolve()}")
    if args.html:
        Path(args.html).write_text(render.to_html(t, args.title), encoding="utf-8")
        print(f"[已写出 HTML] {Path(args.html).resolve()}")


if __name__ == "__main__":
    main()
