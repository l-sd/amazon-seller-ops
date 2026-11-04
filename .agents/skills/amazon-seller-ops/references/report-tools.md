# 报表和快照工具

报表脚本复用仓库根目录 `operations.py`，依赖已有 pandas/openpyxl。先检查当前可用解释器；本机已有 `D:\venvs\ecommerce-analytics-agent\Scripts\python.exe`。不自动安装依赖、不把临时文件放 C 盘。

## 销售日报

在仓库根目录运行，路径由实际任务替换：

```powershell
& 'D:\venvs\ecommerce-analytics-agent\Scripts\python.exe' '.agents\skills\amazon-seller-ops\scripts\run_reports.py' sales --input 'examples\sales_daily.csv' --store DEMO-STORE --marketplace US --currency USD --timezone America/Los_Angeles --data-kind synthetic --report-date 2026-11-01 --output-dir 'outputs\skill-sales-demo'
```

真实表使用 `--data-kind user-provided`，不把模拟标识留在真实结果上，也不将用户导出未经核验地称作官方认证。脚本要求必填日期、订购商品销售额、订购件数、订单项数；会话/页面浏览量可选。按 ASIN 的跨日表不能拆日。输出 Excel、日报文本与运行记录，不覆盖原表和已有输出目录。

## SP 搜索词复盘

```powershell
& 'D:\venvs\ecommerce-analytics-agent\Scripts\python.exe' '.agents\skills\amazon-seller-ops\scripts\run_reports.py' ads --input 'examples\sp_search_terms_old.csv' 'examples\sp_search_terms_updated.csv' --store DEMO-STORE --marketplace US --currency USD --timezone America/Los_Angeles --data-kind synthetic --window 7 --as-of 2026-11-03 --target-acos 0.30 --min-clicks 20 --min-spend 10 --output-dir 'outputs\skill-ads-demo'
```

`--input` 顺序由旧到新，后文件替换整个重叠日。仅可合并同店铺、站点、币种、时区、广告产品、归因口径和完整筛选范围。`--as-of` 是该批实际导出所能观察到的截止日，不是随意填今天。默认阈值只用于演示，正式复盘按目标、样本和产品阶段调整。

英文/中文表头自动映射不完整时，先预览原表，提供 UTF-8 JSON 映射：

```json
{"report.csv": {"date": "日期", "sales": "订购商品销售额", "units": "订购件数", "order_items": "订单项数"}}
```

通过 `--mapping mapping.json` 指定。映射文件按输入文件名取值；不含凭据。广告列名不得混入不同窗口、同 SKU/promoted 指标或浏览归因。

## 竞品快照

空白模板：`assets/competitor-snapshot.csv`。通过获准访问的商品页/截图/导出填记录，缺失项留空。`observed_at` 使用带时区 ISO 时间，`source_type` 区分 observed_public、user_provided、third_party_estimate、synthetic。

```powershell
& 'D:\venvs\ecommerce-analytics-agent\Scripts\python.exe' '.agents\skills\amazon-seller-ops\scripts\compare_snapshots.py' --before 'private_data\before.csv' --after 'private_data\after.csv' --output-dir 'outputs\competitor-changes'
```

输出 JSON 保留输入指纹与来源。比较键为站点、ASIN、具体变体和配送地区；币种/价格口径变化时不计算价格变化，BSR 类目变化时不计算排名差。未再出现的记录标未复查，不认定下架。脚本不抓取、估算销量或证明网页真实状态。

选品模板 `assets/product-candidates.csv` 和巡检模板 `assets/daily-checks.csv` 供 Codex 依据证据填写；不是强制用户先填完所有字段。成本缺失不得当零，实际未检查的巡检项不能填“正常”。
