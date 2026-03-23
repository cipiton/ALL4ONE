---
name: novel_adaptation_plan
display_name: Novel Adaptation Plan
description: Generate a novel adaptation plan for short-drama production by extracting key set pieces, planning pacing phases, and binding major beats into a standardized adaptation outline.
aliases:
  - short_drama_adaption
  - short-drama-adaption
system_instructions: |
  If source_mode=project_ingested or source_type=synthesized_master_outline, treat the provided dossier as sufficient working source material.
  In that case, operate in best-effort production mode:
  - do not ask the user to confirm missing inputs
  - do not output a questionnaire, checklist, or requirements request
  - make conservative assumptions where details are missing
  - produce a substantive adaptation plan directly
  The final output must include: adaptation positioning, compression/omission strategy, principal characters and functions, major arcs, stage/episode structure, key set pieces/reversals, tone/style notes, and production-facing planning notes.
  Only mention blockers briefly at the end if generation is truly impossible; blockers must never replace the deliverable.
---

# Novel Adaptation Plan

## 任务目标
- 本技能用于：根据小说原文，一键全自动完成AI短剧工业化改编策划与编剧
- 能力包含：名场面提取与分级、5阶段节奏规划、单集名场面绑定、标准化制作方案输出
- 触发条件：用户提供小说题材、原文字数、自定义总集数（默认60集），需要将小说改编为竖屏短剧

## Project-Ingested Mode
- 当输入源带有 `source_mode: project_ingested` / `source_type: synthesized_master_outline` 元数据时，说明上游已完成长文本分块、连续性合并、人物与线索整理。
- 在该模式下，必须把 `master_outline.txt` 与其背后的共享 continuity state 视为足够可靠的工作底稿，直接进入“最佳努力生成”。
- 不要把输出写成“请补充字数/集数/确认信息”的问卷、确认单或 checklist。
- 若缺少局部细节，采用保守合理假设并在成稿内自然落地，例如：
  - 未指定总集数时默认按 `60集` 规划
  - 未给出精确字数时按“当前覆盖章节体量”做压缩规划
  - 细枝末节不明时优先保主线、人物功能与节奏节点
- 只有在根本无法形成改编方案时，才允许在正文最后用不超过3行指出真正阻塞项；不得让阻塞说明取代正文主体。

## 交付原则
- 优先交付完整改编方案，而不是索要更多材料。
- 输出必须是可直接用于短剧开发、编剧拆解或制作评审的实质性文档。
- 若原始材料是上游整合后的母本档案，默认其已包含足够的世界观、角色、案件、阶段节奏与关键名场面信息。

## 强制输出合同
- 最终输出必须至少包含以下部分，且内容具体，不可留空：
  1. 项目定位与改编一句话卖点
  2. 改编压缩策略 / 取舍原则
  3. 核心主线与主要人物功能表
  4. 主要阶段节奏规划
  5. 分集结构规划（至少给出每阶段或每集的明确推进）
  6. 名场面/关键反转落点
  7. 风格与拍法建议
  8. 编剧/制作侧注意事项
- 输出必须以“已生成的改编方案”收束，不能停在“待确认/待补充”。

## 前置准备
- 无需额外依赖
- 确保用户提供完整的小说原文内容

## 操作步骤
1. **信息确认与准备**
   - 确认用户输入的3项基础信息：小说题材、原文字数、自定义总集数（默认60集）
   - 接收并完整阅读小说原文
   - 核对原文字数，确认无大偏差（±5%以内）

2. **名场面提取**
   - 从原文中识别连续500-1500字的片段
   - 筛选满足至少1条以下特征的片段：
     - 强冲突/对抗/打脸/对峙
     - 剧情反转/真相揭露/身份曝光
     - 人设高光/关键抉择/情绪极值
     - 可传播金句/标志性仪式场景（告白、决战、决裂等）
     - 主线不可逆关键节点
     - 幽默风趣、具备强传播特性的梗
   - 同时结合用户指定的名场面（如有）

3. **名场面分级**
   - S级：≥3条特征，主线终极节点/全局反转/极致情绪，1个=1集
   - A级：≥2条特征，主线关键节点/中强高光，1-2个=1集
   - B级：≥1条特征，爽点/情绪/主线高潮，2-3个=1集
   - C级：无上述特征，纯过渡，仅做衔接，不占名场面名额

4. **5阶段节奏规划**
   - 开篇钩子期：10%集数
   - 主线铺垫期：20%集数
   - 高潮密集期：40%集数
   - 终极爆发期：20%集数
   - 结局留钩期：10%集数
   - 集数按四舍五入取整，保证总和=用户自定义总集数

5. **单集名场面绑定**
   - 每集必含：冲突/反转/情绪峰值 三选一
   - 每集结尾：强制留钩子（悬念/爽点预告/伏笔）
   - S级名场面必须落地：放开篇、付费点、终极高潮位
   - 过渡剧情总占比≤10%，不水剧情

6. **输出标准化方案**
   - 严格按照指定格式输出两个表格
   - 确保内容无废话、可直接导入AI生产工具

## 输出格式

### 表1：阶段集数规划表
| 阶段         | 阶段定位                | 规划集数 | 名场面配比建议（S/A/B） | 核心节奏要求                | 关键功能                  |
|--------------|-------------------------|----------|-------------------------|-----------------------------|---------------------------|
| 开篇钩子期   | 强冲突留人              |          |                         | 开篇炸点，高留存            | 引流/抓用户               |
| 主线铺垫期   | 立人设+铺世界观         |          |                         | 节奏平稳，埋线索            | 铺垫主线                  |
| 高潮密集期   | 名场面高密度连环        |          |                         | 高爽高密，持续上头          | 核心付费/流量段           |
| 终极爆发期   | 主线反转&S级集中         |          |                         | 情绪拉满，终极高潮          | 剧情核心爆点              |
| 结局留钩期   | 收尾+埋第二季钩子       |          |                         | 闭环留悬念，引导续看        | 留客/第二季铺垫           |
| 合计         | ——                      |          | ——                      | ——                          | 适配AI批量制作            |

### 表2：单集剧情+名场面绑定详细大纲
| 集数 | 所属阶段     | 名场面等级 | 绑定名场面（原文核心内容）| 单集纯剧情概要（50–100字）| 节奏亮点 | 结尾钩子 | 制作标注（引流/付费/过渡） |
|------|--------------|------------|----------------------------------|---------------------------------------|----------|----------|----------------------------|
| 1    |              |            |                                  |                                       |          |          |                            |
| 2    |              |            |                                  |                                       |          |          |                            |
| ...  |              |            |                                  |                                       |          |          |                            |
| 总计 | ——           | ——         | S__个 / A__个 / B__个             | 总纯剧情字数：________                 | ——       | ——       | 100%适配AI工业化生成       |

## 最终校准要求
1. 总集数严格等于用户自定义数字，不增减
2. 所有S/A级名场面100%落地，无遗漏
3. 阶段比例、节奏、钩子完全符合竖屏短剧规则
4. 输出内容无废话、可直接导入AI生产工具

## 单集制作标准
- 时长：60-90秒/集
- 单集纯剧情字数：800-1200字
- 每集必含冲突/反转/情绪峰值三选一
- 每集结尾强制留钩子

## 注意事项
- 充分利用对文本内容的深度理解能力，精准识别名场面
- 严格按照规则执行，确保输出标准化、可直接用于AI生产
- 在名场面提取和分级时，结合小说题材特点进行判断
- 确保阶段节奏符合竖屏短剧的流量和留存规律
- 如果已经收到项目整合后的 `master_outline` / 母本大纲，则直接把它当成可执行底稿，不再回退成需求确认问卷
