---
name: novel_to_drama_script
display_name: Novel-to-Drama Script
description: Turn novel source material, set-piece notes, and episode outlines into episode-level drama scripts for short-form production.
aliases:
  - novel-to-drama-script
metadata:
  model_routing:
    step_execution_model: fast
    final_deliverable_model: strong
system_instructions: |
  If source_mode=project_ingested or source_type=synthesized_master_outline, treat the provided dossier as sufficient working source material.
  In that case, operate in best-effort production mode:
  - do not ask the user to provide more materials
  - do not output a checklist, questionnaire, or confirmation note
  - make conservative assumptions where details are missing
  - produce a substantive script-ready deliverable directly
  If a full dialogue script would be too large or underdetermined, output a script-ready episode package instead:
  - episode-by-episode breakdown
  - scene order
  - dramatic beats and turning points
  - key dialogue cues
  - ending hooks
  If runtime inputs specify a detected total episode count and a requested episode range, generate only that selected episode or episode range.
  If runtime inputs specify generation_mode=regenerate, treat any provided prior-episode text, neighboring episode context, and regeneration instruction as continuity constraints:
  - preserve the current episode-script style and layout
  - preserve series continuity unless the regeneration instruction explicitly asks for a targeted change
  - use the adaptation plan, character bible, and neighboring episode references to reduce continuity drift
  Keep the existing episode-script writing style, tone, section layout, and script-template behavior materially unchanged.
  The result must be usable by a downstream writer without first answering more questions.

runtime_inputs:
  - name: generation_mode
    prompt: Choose episode operation mode
    type: choice
    choices:
      - generate
      - regenerate
    default: generate
    required: true
  - name: episode_range
    prompt: Which episodes should be generated or regenerated?
    type: episode_range
    required: false
---

# Novel-to-Drama Script

## 任务目标
- 本Skill用于：将小说文字改编为短剧演绎剧分集剧本
- 能力包含：结合名场面整理、遵循分集大纲、创作短剧剧本（对白占比>70%，单句≤12字，第一集3秒黄金开头，每集开头承接上集，每集结尾留钩子，中间有情绪拐点）
- 触发条件：用户需要改编小说为短剧剧本、创作短剧演绎剧剧本、或根据名场面和大纲生成分集剧本

## Project-Ingested Mode
- 当输入源带有 `source_mode: project_ingested` / `source_type: synthesized_master_outline` 元数据时，表示上游已经把长篇原文整合为统一的剧情母本、人物关系、时间线、名场面与连续性档案。
- 在该模式下，必须把这份整合档案视为可直接开工的脚本底稿，而不是再次向用户索要“小说正文/名场面整理/分集大纲确认”。
- 采用最佳努力生成：
  - 缺细节时做保守补足
  - 缺少逐章原文时，以母本大纲中的明确事件链、角色功能、关键场次和连续性约束为准
  - 优先交付可写、可拆、可继续生产的剧本化成果
- 不得把最终输出写成确认清单、问题单、需求问卷或“请先提供更多资料”的说明文。
- 只有在确实无法成稿时，才允许在正文末尾补充极短阻塞说明；正文主体仍必须先交付最佳努力结果。

## 强制输出合同
- 输出必须是“实质性的剧本化交付物”，至少包含以下部分：
  1. 项目定位 / 本轮改编范围
  2. 分集规划或集群规划
  3. 每集的核心戏剧目标
  4. 场次顺序 / scene sequence
  5. 关键戏剧 beats 与冲突钩子
  6. 关键对白走向或可直接扩写的对白提示
  7. 集尾钩子
- 如果篇幅不足以写出完整台词正稿，优先输出“剧本化分集总包”：
  - EP-by-EP 场次拆解
  - 每场的目标/冲突/推进
  - 关键对白提示
  - 视觉与节奏说明
- 输出必须让下游编剧可以直接继续扩写，不允许退化为需求确认文档。

## 前置准备
- 需要用户提供：
  1. 小说原文片段或完整内容
  2. 名场面整理（标注需要重点保留的关键情节）
  3. 分集大纲（每集的主要情节脉络）

## 操作步骤
1. **需求确认**：
   - 确认用户提供的小说内容、名场面整理和分集大纲
   - 确认每集剧本的字数要求（1000-2000字）和对白占比要求（>70%）
   - 确认短剧创作要求：第一集3秒黄金开头、每集开头承接上集、每集结尾留钩子

2. **剧本创作**：
   - 阅读小说原文，理解人物性格、关系和情节发展
   - 根据分集大纲确定当前集数的主要情节
   - 重点保留名场面整理中标注的关键场景
   - 按照参考文档中的剧本格式进行创作
   - 确保单句对白≤12字，大段对白拆分并穿插画面描述
   - 设计情绪拐点：反转、高潮、打脸等冲突节点

3. **质量检查**：
   - 检查对白占比是否>70%
   - 检查单句对白是否≤12字（特殊场景除外）
   - 检查大段对白是否拆分并穿插画面
   - 检查第一集是否有3秒黄金开头
   - 检查每集开头是否承接上集结尾
   - 检查每集结尾是否留钩子或悬念
   - 检查中间是否有情绪拐点/冲突节点
   - 检查字数是否在1000-2000字范围内
   - 检查是否完整保留了名场面
   - 检查人物性格和对话是否符合原著设定

4. **输出交付**：
   - 按照要求格式输出剧本
   - 确认用户是否满意，如需调整进行修改

## 资源索引
- 剧本格式模板：见 [references/script-format.md](references/script-format.md)（剧本格式规范和示例）
- 剧本模板文件：见 [assets/script-template.txt](assets/script-template.txt)（可直接使用的剧本模板）

## 注意事项
- 优先保证对白的质量和自然度，避免生硬改编
- 单句对白尽量控制在12字以内，除非特殊场景（吟唱/念咒等）
- 大段对白必须拆分，中间穿插环境空镜、反应镜、特写等画面
- 第一集前3秒必须是吸睛的黄金开头
- 每集开头要呼应或承接上一集结尾
- 每集结尾要有钩子或悬念吸引观众追剧
- 中间要有反转/高潮/打脸等情绪拐点或冲突节点
- 画面描述要简洁有力，为拍摄或演绎提供指导
- 忠实于原著人物性格，不随意改变人物设定
- 名场面要重点突出，保持原著的情感张力
- 若输入已经是上游整合后的 `master_outline` / 母本档案，则直接据此生成剧本化交付物，不再把输出写成“还缺哪些资料”

## 使用示例
### 示例1：改编武侠小说
- 功能说明：将武侠小说改编为演绎剧剧本
- 执行方式：智能体根据小说内容、名场面和大纲创作
- 关键要点：保留武打场面的精彩描写，突出人物性格特点
- 输出格式：按照剧本格式模板输出

### 示例2：改编言情小说
- 功能说明：将言情小说改编为演绎剧剧本
- 执行方式：智能体根据小说内容、名场面和大纲创作
- 关键要点：重点保留情感互动场面，对话要细腻感人
- 输出格式：按照剧本格式模板输出
