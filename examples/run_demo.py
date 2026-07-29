#!/usr/bin/env python3
"""run_demo.py — 无需凭证的离线演示。

合成一条跨度 ≥ 18 个月、含明显趋势 + 一段深回撤的日频净值序列，
生成完整 tearsheet（JSON + 自包含 HTML），并打印 HTML 绝对路径。
同时把合成序列落地为 examples/sample_data/nav.csv，供 CLI 复用。

真实使用见 README（配置 panda_data SDK 后用 --fund / --benchmark）。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import metrics   # noqa: E402
import render    # noqa: E402
from tearsheet import build_tearsheet  # noqa: E402

SAMPLE_DIR = HERE / "sample_data"
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)


def synth_nav_series(seed: int = 20260727) -> pd.Series:
    """合成日频净值：整体上行趋势 + 中途一段 ~22% 深回撤 + 随机波动。"""
    rng = np.random.default_rng(seed)
    # 交易日日历（约 21 个月，跨度 ≥ 12 个月，月度热力图有充足数据）
    dates = pd.bdate_range("2024-01-02", periods=440)
    n = len(dates)

    # 基础日漂移（年化 ~24%）+ 波动（年化 ~16%）——整体上行趋势
    mu = 0.24 / 252
    sigma = 0.16 / np.sqrt(252)
    rets = rng.normal(mu, sigma, n)

    # 注入一段明显回撤：第 150~195 交易日持续承压（约 -18%，随后可恢复）
    dd_start, dd_end = 150, 195
    rets[dd_start:dd_end] += rng.normal(-0.0055, 0.003, dd_end - dd_start)

    # 注入几次单日尾部冲击，制造厚尾/偏度
    rets[95] -= 0.045
    rets[300] -= 0.035
    rets[330] += 0.04

    nav = (1.0 + pd.Series(rets, index=dates)).cumprod()
    nav.iloc[0] = 1.0  # 归一起点
    return nav


def write_sample_files(nav: pd.Series):
    """落地 nav.csv 与 get_index_daily.json（合成基准指数），供 CLI / 样本回退复用。"""
    # nav.csv
    nav_df = pd.DataFrame({"date": nav.index.strftime("%Y-%m-%d"),
                           "nav": nav.round(6).values})
    nav_df.to_csv(SAMPLE_DIR / "nav.csv", index=False)

    # 合成一条基准指数日线（get_index_daily 结构）：与策略部分同向（共享市场因子）但更平缓
    rng = np.random.default_rng(11)
    strat_ret = nav.pct_change().fillna(0.0).values
    idio = rng.normal(0.05 / 252, 0.10 / np.sqrt(252), len(nav))
    bret = pd.Series(0.55 * strat_ret + idio, index=nav.index)   # β≈0.55、正相关
    close = (1000.0 * (1.0 + bret).cumprod())
    rows = []
    prev = None
    for d, c in close.items():
        c = float(round(c, 2))
        rows.append({
            "symbol": "000300.SH",
            "date": d.strftime("%Y%m%d"),
            "open": round(c * 0.999, 2),
            "close": c,
            "high": round(c * 1.006, 2),
            "low": round(c * 0.994, 2),
            "volume": float(rng.integers(1_000_000, 5_000_000)),
            "pre_close": prev if prev is not None else c,
            "amount": float(rng.integers(10_000_000, 50_000_000)),
        })
        prev = c
    import json
    (SAMPLE_DIR / "get_index_daily.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    nav = synth_nav_series()
    write_sample_files(nav)

    returns = metrics.nav_to_returns(nav)

    # 合成基准收益（从刚写出的样本读取，走真实解析路径）
    import json
    brows = json.loads((SAMPLE_DIR / "get_index_daily.json").read_text(encoding="utf-8"))
    bdf = pd.DataFrame(brows)
    bdf["date"] = pd.to_datetime(bdf["date"], format="%Y%m%d")
    bnav = pd.Series(bdf["close"].astype(float).values,
                     index=pd.DatetimeIndex(bdf["date"].values))
    bench_returns = metrics.nav_to_returns(bnav)

    t = build_tearsheet(returns, ppy=252, rf_annual=0.02,
                        bench_returns=bench_returns, backend="sample(demo合成)")

    json_path = HERE / "tearsheet.json"
    html_path = HERE / "tearsheet.html"
    json_path.write_text(render.to_json(t), encoding="utf-8")
    html_path.write_text(render.to_html(t, "策略绩效 Tearsheet（演示）"), encoding="utf-8")

    print("=" * 60)
    print("策略绩效 Tearsheet 离线演示")
    print("=" * 60)
    print(f"序列区间: {t['start_date']} ~ {t['end_date']}  共 {t['n_periods']} 期")
    print(f"月度矩阵年份: {t['monthly_returns']['years']}")
    print("-" * 60)
    print(render.build_summary_text(t))
    print("-" * 60)
    print(f"[已写出 JSON] {json_path.resolve()}")
    print(f"[已写出 HTML] {html_path.resolve()}")
    print("\n浏览器直接打开上面的 HTML 即可查看看板（自包含，无需联网）。")
    print("免责：仅供研究参考，不构成投资建议。")


if __name__ == "__main__":
    main()
