"""
data_source.py — Pandadata 适配层（策略绩效 tearsheet）

三层回退策略（与组织样板一致）：
  1) 生产环境：`import panda_data` SDK 直连（组织标准）。
  2) 无 SDK：回退到 examples 内置样本 JSON，保证离线可跑 demo。
  3) 显式 `--prefer sample`：强制使用样本，忽略 SDK。

本技能的核心指标计算**不依赖 Pandadata**——用户直接传净值/收益序列即可跑通。
数据接口只在两个可选增强场景使用：
  - 用户只给基金代码，用 get_fund_daily 收盘价构造净值代理序列。
  - 用户指定基准指数，用 get_index_daily 拉指数日线做相对基准分析。

所有接口日期格式 YYYYMMDD；symbol 传 "" 表示全市场。
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "sample_data"


def year_chunks(start: str, end: str) -> list[tuple[str, str]]:
    """Split an inclusive YYYYMMDD range into requests that never cross a year."""
    first = datetime.strptime(start, "%Y%m%d")
    last = datetime.strptime(end, "%Y%m%d")
    if first > last:
        raise ValueError("start must not be after end")
    chunks = []
    for year in range(first.year, last.year + 1):
        chunk_start = max(first, datetime(year, 1, 1))
        chunk_end = min(last, datetime(year, 12, 31))
        chunks.append((chunk_start.strftime("%Y%m%d"), chunk_end.strftime("%Y%m%d")))
    return chunks


# ---------------------------------------------------------------------------
# 后端探测
# ---------------------------------------------------------------------------
def _sdk_available() -> bool:
    try:
        import panda_data  # noqa: F401
        return True
    except Exception:
        return False


def _call_sdk(method: str, **params) -> list[dict]:
    """调用 panda_data.<method>(**params)，统一归一为 list[dict]。

    SDK 返回可能是 DataFrame、list[dict]，或包 result 的 dict，都要能处理。
    """
    import panda_data
    fn = getattr(panda_data, method)
    res = fn(**params)
    try:
        import pandas as pd
        if isinstance(res, pd.DataFrame):
            return res.to_dict("records")
    except Exception:
        pass
    if isinstance(res, list):
        return res
    if isinstance(res, dict) and "result" in res:
        return res["result"]
    if isinstance(res, dict):
        # 单条记录也包成列表
        return [res]
    return []


def _sample_available() -> bool:
    return SAMPLE_DIR.exists()


def _call_sample(method: str, **params) -> list[dict]:
    """从内置样本读取；若样本含 symbol 列且调用指定了 symbol 则过滤。"""
    f = SAMPLE_DIR / f"{method}.json"
    if not f.exists():
        return []
    rows = json.loads(f.read_text(encoding="utf-8"))
    symbol = params.get("symbol")
    if symbol and rows and "symbol" in rows[0]:
        syms = [symbol] if isinstance(symbol, str) else list(symbol)
        rows = [r for r in rows if r.get("symbol") in syms]
    start, end = params.get("start_date"), params.get("end_date")
    if start and end:
        rows = [r for r in rows if not r.get("date") or start <= str(r["date"]) <= end]
    return rows


# ---------------------------------------------------------------------------
# 统一取数入口
# ---------------------------------------------------------------------------
class DataSource:
    def __init__(self, prefer: str | None = None):
        # prefer: "sdk" | "sample" | None(自动)
        if prefer == "sample":
            self.backend = "sample"
        elif prefer == "sdk" or _sdk_available():
            self.backend = "sdk"
        elif _sample_available():
            self.backend = "sample"
        else:
            self.backend = "none"
        self.diagnostics: list[str] = []

    def fetch(self, method: str, **params) -> list[dict]:
        if self.backend == "sdk":
            try:
                return _call_sdk(method, **params)
            except Exception as e:  # noqa: BLE001
                # 单接口失败不应中断流程，返回空并让上层记降级
                message = f"SDK {method} failed: {e}"
                self.diagnostics.append(message)
                print(f"[data_source] {message}")
                return []
        if self.backend == "sample":
            return _call_sample(method, **params)
        return []

    def _fetch_chunked(self, method: str, symbol: str, start: str, end: str,
                       **params) -> list[dict]:
        """Fetch annual chunks, then deduplicate boundary rows and sort by date."""
        merged: dict[tuple[str, str], dict] = {}
        for chunk_start, chunk_end in year_chunks(start, end):
            rows = self.fetch(method, symbol=symbol, start_date=chunk_start,
                              end_date=chunk_end, **params)
            for row in rows:
                key = (str(row.get("symbol", symbol)), str(row.get("date", "")))
                merged[key] = dict(row)
        return sorted(merged.values(), key=lambda row: str(row.get("date", "")))

    # --- 语义化封装 ---
    def fund_nav(self, symbol: str, start: str, end: str,
                 exchange: str = "", fields: str = "") -> list[dict]:
        """基金日线代理净值；用 get_fund_daily.close 映射为 unit_nav。"""
        params = {}
        if fields:
            params["fields"] = fields
        daily = self._fetch_chunked("get_fund_daily", symbol, start, end, **params)
        for r in daily:
            if "unit_nav" not in r and r.get("close") is not None:
                r["unit_nav"] = r["close"]
        return daily

    def index_daily(self, symbol: str, start: str, end: str,
                    fields: str = "") -> list[dict]:
        """指数日线做基准。返回 {symbol,date,open,close,high,low,volume,pre_close,amount}。"""
        params = {"fields": fields} if fields else {}
        return self._fetch_chunked("get_index_daily", symbol, start, end, **params)
