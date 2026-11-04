# 来源与采纳范围

访问日期统一为 **2026-11-03**。以下是用于设计工作流的摘要，不是对来源全文的复制。平台规则以执行时的站点官方资料为准；公开可访问不证明匿名作者的卖家身份或效果。付费工具功能不表示当前用户拥有权限。

## 官方资料

| 编号 | 来源、状态 | 采纳范围及限制 |
|---|---|---|
| O1 | [Amazon Business Reports](https://sell.amazon.com/blog/amazon-business-reports)，正文可读；文章主题含 B2B | 按日期/按 ASIN 报表和导出入口；实际分析需区分总体与 B2B 子集，不把文章主题当用户业务模式 |
| O2 | [Product Opportunity Explorer](https://sell.amazon.com/tools/product-opportunity-explorer)，正文可读 | 从搜索、购买和评论洞察做商品研究；不假设用户可访问后台或具备全部数据 |
| O3 | [FBA Revenue Calculator](https://sell.amazon.com/blog/how-to-use-fba-calculator)，正文可读 | 按商品尺寸、重量、履约和成本做估算；不固化费率，不把估算当实际利润 |
| O4 | [SP 搜索词报表](https://advertising.amazon.com/help/G3HEFZYWZF84NPS9)，检索摘要可读，直接访问仅返回页面外壳 | 搜索词有点击覆盖边界；实际列名、归因窗口与指标必须用用户导出表/当前官方帮助复核 |
| O5 | [Amazon Seller Central 管理业务概览](https://sell.amazon.com.sg/north-america/manage-your-business-in-seller-central)，官方公开说明，检索摘要可读 | 账户健康、库存、客户反馈等工作维度；站点与导航版本可能不同，不据此声称某按钮当前必然存在 |
| O6 | [Amazon 产品安全与合规](https://globalselling.amazon.com/en/policy/product-safety)，官方公开说明，检索摘要可读 | 选品须核查禁限售、危险品和安全要求；不是产品法律/认证审查完成证据 |
| O7 | [Amazon 库存管理](https://sell.amazon.com/learn/inventory-management)，官方公开说明，检索摘要可读 | 库存管理与履约约束；具体库存状态和补货数值仍来自用户数据 |
| O8 | [Amazon Ads 归因说明](https://advertising.amazon.com/help/GX7KDKHMWQYMJ385)，检索摘要可读 | 归因期未结束的指标可能不完整；不把不同广告产品和卖家/供应商窗口混用 |

检索时尝试的 `https://sell.amazon.com/blog/inventory-management` 返回 404，未作为事实依据；改用 O7。网页返回验证码、空壳或入口移动时保留未核实状态，不以工具失败推断产品功能不存在。

## 实务工具提供方

| 编号 | 来源、状态 | 采用/未采用 |
|---|---|---|
| T1 | [Helium 10：Competitors Page](https://kb.helium10.com/hc/en-us/articles/19704054134811-Insights-Dashboard-Competitors-Page)，正文可读，页面日期 2023-10-19 | 采用价格/页面/表现变化及历史快照的分组方法；不假设当前套餐、限额、按钮或销售估计仍相同 |
| T2 | [Jungle Scout：Competitive Intelligence](https://support.junglescout.com/hc/en-us/articles/25103708242711-Discover-Jungle-Scout-s-Competitive-Intelligence)，正文可读，页面更新 2025-02-10 | 采用先界定竞争集合、再作商品/市场对照的次序；市场份额与营收分析须有对应数据，不复制工具营销承诺 |

## 卖家社区个体经验

## 关键词日常工作补充（2026-11-03 检索）

- T3：[西柚找词实务教程](https://knowledge.xydc.com/blog/how-to-use1/)，正文可读，页面日期 2023-07-04。参考先选可比竞品、ASIN 反查、词库筛选和自然位跟踪；不采用示例中的固定类目/名次阈值，也不把 ABA 变化当作具体 ASIN 自然位变化。
- T4：[西柚场景化功能说明](https://knowledge.xydc.com/blog/function-use/)，正文可读，页面日期 2024-05-07。参考多 ASIN 反查、词库分类与覆盖差异；不采纳其词频代表算法权重、固定流量分配阶段等未经平台证实的解释。
- T5：[Helium 10 Keyword Tracker 帮助](https://kb.helium10.com/hc/en-us/articles/360036302794-How-Do-I-Navigate-the-Keyword-Tracker-Dashboard)，正文可读，页面日期 2025-08-29。参考找词/整理和排名监控分开的流程，权限/套餐需实查。
- T6：[卖家精灵运营说明](https://www.sellersprite.com/cn/channel/operation)，检索摘要可读。监控滚动更新、不同来源采集时间和地区可造成差异，需保留实际观测时间。历史帮助含不当推广建议，未采纳。
- [西柚 MCP 页面](https://platform.xydc.com/mcp)及[小时排名示例](https://platform.xydc.com/docs/use-cases/hourly-rank)检索摘要可见，但直接访问返回 WAF 校验外壳；本项目没有接入测试，不复制页面返回的校验参数，也不宣称可直接调用。

实际每日输入按用户补充确定为“其他网站返回的排名表格”，不是本 Skill 自行爬取/查询排名。用户模板另作本地只读结构参考，不作为公开附件。

| 编号 | 来源、状态 | 采用/未采用 |
|---|---|---|
| C1 | [Daily tasks to do on FBA](https://www.reddit.com/r/FulfillmentByAmazon/comments/18nhyn3/daily_tasks_to_do_on_fba/)，正文可读，历史经验帖 | 参考不可售、账户健康、VOC、库存和反馈的巡检维度；没有采用作者固定库存件数阈值，也不将评论中的操作视作平台允许 |
| C2 | [My actual weekly routine](https://www.reddit.com/r/AmazonFBAonline/comments/1wytzl8/my_actual_weekly_routine_for_running_an_fba/)，正文可读，发表日期显示与检索摘要相对时间不一致 | 只参考按销售/广告、库存、页面和费用分配复盘的节奏；不记录未经确认的精确发表日，也不声称该方法已验证有效 |

## 本地材料

- 用户《亚马逊运营知识库》，v1.0，2026 年 10 月，美国站。已从原 DOCX 只读提取并核对 482 个非空段落；原文件 SHA256：`eb206f1a86822cbdbcd9fbf0f07a46afbeaee32f81b28af4ccc7a33d3903e3e3`。
- 本地课程地图与长期学习记忆用于理解目标和表达方式，不复制到公开包，不代表当前用户已掌握所有单元。
- 段落编号和原理纠偏见 [knowledge-map.md](knowledge-map.md)。选品/系统竞品流程为外部资料与本项目设计补充，不能说它们已全部包含在原教材中。
