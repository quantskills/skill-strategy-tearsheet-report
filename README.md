# skill-strategy-tearsheet-report

[English](README.en.md)

策略绩效 Tearsheet 报告生成器 —— 输入一条净值/收益序列（CSV: `date,nav` 或 `date,return`），输出机构级绩效画像：年化收益/波动、夏普/索提诺/Calmar/Omega、最大回撤与 Top-N 回撤区间、偏度/峰度/VaR/CVaR、滚动指标、月度收益热力图、可选相对基准分析。产出 **JSON + 自包含 HTML 看板 + 中文摘要**。

> QuantSkills 组织技能 · 数据源 Pandadata（可选）· 仅供研究参考，不构成投资建议。

## 快速开始

> **依赖提示**：本技能依赖 `numpy` / `pandas`，请在装好这两个包的 Python 环境中运行
> （例如 `conda create -n quantskill python=3.11 -y && conda activate quantskill && pip install numpy pandas`）。
> 裸 Python 环境缺少 numpy 会直接报 `ModuleNotFoundError`。

```bash
pip install -r requirements.txt

# 离线演示（无需任何凭证，合成一条带趋势+回撤的净值序列）
python examples/run_demo.py
# → 生成 examples/tearsheet.json 与 examples/tearsheet.html，并打印 HTML 绝对路径

# 从自己的净值 CSV 生成
python scripts/tearsheet.py --nav nav.csv --ppy 252 --rf 0.02 \
    --out tearsheet.json --html tearsheet.html

# 收益 CSV + 基准指数（需 panda_data SDK 取指数）
python scripts/tearsheet.py --returns ret.csv --benchmark 000300.SH \
    --ppy 252 --out t.json --html t.html
```

HTML 看板**完全自包含**（内联 CSS + 手绘 SVG，无外部 CDN），浏览器直接双击打开即可。

## 输入契约

| 输入 | 形态 | 必需 | 说明 |
|------|------|------|------|
| `--nav` / `--returns` | CSV(date,nav) 或 (date,return) | 二选一 | 净值或逐期收益 |
| `--fund` | 基金代码 | 可替代 CSV | 用 `get_fund_daily` 收盘价构造净值代理（需 SDK） |
| `--benchmark` | 指数代码 | 否 | 如 `000300.SH`，做超额/IR/Beta/相关性 |
| `--ppy` | int | 否 | 年化期数，默认 252 |
| `--rf` | float | 否 | 年化无风险利率，默认 0.02 |

输出 `Tearsheet` JSON：`summary / risk_adjusted / distribution / drawdowns[] / rolling / monthly_returns / annual_returns / vs_benchmark` + HTML 看板。

## ⚠️ 年化期数（periods_per_year）

**这是最容易踩的坑**：年化收益、年化波动、夏普、索提诺全都乘 `√ppy` 或用 `ppy` 复利年化。
`ppy` 必须与序列频率一致，否则指标系统性失真：

- 日频（交易日）→ `--ppy 252`
- 周频 → `--ppy 52`
- 月频 → `--ppy 12`

例如把月频序列误按 252 年化，夏普会被放大约 `√(252/12)≈4.6` 倍。详见 `references/metrics-glossary.md`。

## 数据后端（三层回退）

`scripts/data_source.py` 按以下顺序自动选择，与组织样板一致：

1. **`panda_data` SDK**（组织生产标准）：`import panda_data` 成功即用。安装与鉴权见 `skill-pandadata-api`。
2. **内置样本**（`examples/sample_data/*.json`）：无 SDK 时回退，保证 demo 离线可跑。
3. 显式 `--prefer sample` 可强制用样本。

> ⚠️ **注意**：`--prefer sample` 只影响 `--fund`/`--benchmark` 的取数后端（SDK vs 样本），**不能替代序列输入**——无论如何都必须提供 `--nav` / `--returns` / `--fund` 三者之一，否则 CLI 报错。若只想跑离线 demo，用 `python examples/run_demo.py`（内置 nav 样本）。

> 核心指标计算**不依赖 Pandadata**——用户直接传净值/收益序列即可跑通。数据接口仅用于两个可选增强：`--fund` 拉基金净值、`--benchmark` 拉指数做基准。

### 用到的 Pandadata 接口

| 用途 | 接口 | 关键参数/返回 |
|---|---|---|
| 基金净值代理 | `get_fund_daily(symbol,start_date,end_date)` | 按自然年分段读取收盘价并构造收益序列 |
| 基准指数日线 | `get_index_daily(start_date,end_date,symbol,fields)` | `{symbol,date,open,close,high,low,volume,pre_close,amount}` |

日期格式 `YYYYMMDD`；`symbol` 传 `""` 表示全市场。SDK 返回可能是 DataFrame 或 list[dict]，`data_source._call_sdk` 均已归一处理。

## 目录

```
scripts/       data_source.py · metrics.py · render.py · tearsheet.py
references/    metrics-glossary.md
examples/      run_demo.py · sample_data/（nav.csv · get_index_daily.json）
```

## 免责

本工具仅用于绩效分析方法论演示与研究参考，不构成任何投资建议。历史绩效不代表未来表现。

## 许可证

GPL-3.0-only，详见 [LICENSE](LICENSE)。
