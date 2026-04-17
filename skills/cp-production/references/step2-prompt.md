# 步骤二：输出视觉节拍表

## 执行目标

- 将旁白脚本转换为稳定、可执行、可复用的生产节拍表。
- 让 beat 成为后续资产提炼、关键帧提示词和视频提示词的共享规划单元。
- 在 beat 层加入内部“scene dramatization / 场景戏剧化设计”，让后续提示词不是从字段机械拼接，而是从已经被视觉化、戏剧化、连续性校准过的场景设计中渲染。
- 明确区分完整 clip 候选 beat、插入类 beat、过渡类 beat 和仅适合作为 narration support 的 beat。

## 核心原则

### 1. 按生产节拍拆分，不按句子机械切分

- 一章/一节通常会拆成多个 beat。
- 一个 beat 只承载一个主要动作、一个主要认知变化、一个主要关系变化，或一个主要视觉信息点。
- 不要把多个重大事件塞进一个 beat。
- 也不要把一句话拆成一个 beat，导致过碎。

### 2. beat 是视觉场景规划单元，不是 recap prose

- `summary` 必须简洁、清晰、可供后续生产理解。
- 不要写成文学性长句。
- 不要写成主题分析、角色解读、象征意义说明。
- 但每个 clip-worthy 或 maybe beat 必须已经具备强画面判断：这一拍最值得看的瞬间是什么、观众第一眼该看见什么、这一拍相对前后镜头有什么区别。

### 3. 必须先做场景戏剧化，再做字段归档

对每个 beat，必须先在脑中完成一个内部 scene design，再把结果写入字段。不要从元数据直接跳到后续提示词。

内部 scene design 至少要回答：
- 这个 beat 的 `visual_core` 是什么：最强、最清晰、最可见的画面核心。
- 这个 beat 的 `dramatic_focus` 是什么：局势压力、关系压力、选择压力或揭示压力在哪里。
- 上一个 beat 到这个 beat 有哪些 `continuity_notes`：人物身份、服装、地点、时间、道具状态、情绪走势哪些不能断。
- 当前 beat 的 `subject_focus`、`scene_focus`、`prop_focus` 谁优先，谁只是辅助。
- `strongest_single_frame_interpretation` 是什么：如果只能生成一张图，最有冲击力的静帧是哪一秒。
- `strongest_motion_interpretation` 是什么：如果做成视频，这张锚帧之后最应该发生的可见变化是什么。
- `shot_design` 如何让画面有压迫感、悬念、速度、孤独、胜利或崩塌，而不只是“中景/近景”。
- `camera_intent` 为什么这样移动或不移动：镜头服务于揭示、逼近、跟随、压迫、拉开距离还是制造对比。

### 4. 必须做价值判断

- `story_function` 仅允许：
  - `hook`
  - `development`
  - `turn`
  - `payoff`
  - `cliffhanger`
  - `insert`
- `priority` 仅允许：
  - `high`
  - `medium`
  - `low`
- `clip_worthy` 仅允许：
  - `yes`
  - `no`
  - `maybe`
- `duration_class` 仅允许：
  - `short`
  - `medium`
  - `long`

### 5. 每个 beat 至少包含这些字段

保留原有生产规划字段：
- `beat_id`
- `chapter_id`
- `beat_title`
- `summary`
- `story_function`
- `priority`
- `clip_worthy`
- `duration_class`
- `shot_type_suggestion`
- `camera_movement_suggestion`
- `mood`
- `subject_focus`
- `scene_focus`
- `prop_focus`
- `narration_anchor_line`

新增 scene dramatization 字段：
- `visual_core`
- `dramatic_focus`
- `continuity_notes`
- `emotional_pressure`
- `strongest_single_frame_interpretation`
- `strongest_motion_interpretation`
- `shot_design`
- `camera_intent`

## 字段写法要求

### `visual_core`

- 写成一个可被画出来的核心画面，不写抽象主题。
- 应包含主要主体、环境压力、关键动作或关键状态。
- 示例方向：`雨夜山路上，浑身泥水的青年机械师死死扶起倒地摩托，远处电视台面包车尾灯消失在雾里。`

### `dramatic_focus`

- 写这个 beat 的戏剧张力，不写泛泛情绪。
- 必须说明压力来自哪里：被拒绝、债务、时间、比赛、身份证明、关系撕裂、目标即将破裂等。

### `continuity_notes`

- 明确从上一 beat 继承什么，或本 beat 改变了什么。
- 包含角色服装/状态、地点/时间、道具位置、情绪递进、伤痕/泥水/汗水/光线等可见连续性。
- 如果是章节或时间跳转，也要写明跳转后的新连续性起点。
- 必须锁定资产类型，不允许在戏剧化时改写物体类别：摩托车始终是 motorcycle / bike，不要写成 car；摩托车车架始终是 motorcycle frame，不要写成 car chassis；车辆型号、车身比例、轮胎数量和用途必须保持一致。

### `emotional_pressure`

- 写成可被视觉和动作承载的压力。
- 不要只写“悲伤”“激动”；要写“被雨水和嘲笑压住但仍伸手抓车把”“面对投资人保守目光仍不后退”。

### `strongest_single_frame_interpretation`

- 必须是一张可生成的强静帧。
- 选择动作最饱和、关系最清楚、信息最集中、构图最有记忆点的瞬间。
- 不要写多个连续动作；只写一个冻结瞬间。

### `strongest_motion_interpretation`

- 必须是从强静帧继续发生的可见运动。
- 包含人物动作、环境变化、道具运动、反应变化或镜头运动。
- 不要写新场景，不要跨越多个重大事件。

### `shot_design`

- 不只是景别标签，而是画面组织策略。
- 应说明构图重心、前景/中景/背景关系、负空间、遮挡、光线方向、视觉层次或对比。

### `camera_intent`

- 说明镜头意图，而不是堆镜头术语。
- 示例：`slow push in to trap him inside the investors' stare`、`low tracking angle to make the motorcycle feel fast but unstable`、`static wide frame to make the factory feel empty and ceremonial`。

## 输出结构要求

你必须输出一个完整 Markdown 文档，并在文末且只在文末提供 **一个** fenced `json` 代码块。

### 输出长度控制

- 对短篇或单文件输入，优先控制在 8-14 个核心 beats；只有故事明确需要时才超过 14 个。
- Markdown 是审阅摘要，不是完整重复数据库。每个 Markdown 字段只写一行，尽量短句。
- JSON 是运行时 sidecar 的权威结构，必须完整输出。
- 如果篇幅紧张，压缩 Markdown，不要压缩、截断或省略 JSON。
- 任何时候都禁止在输出未完成 JSON fenced block 前停止。

### Markdown 部分必须包含

1. 标题
2. 节拍规划总览
3. 按章节或序列分组的 beat 明细

### Markdown 推荐样式

```text
# 视觉节拍表

## ch01

### beat_001
- Beat Title: …
- Summary: …
- Story Function: …
- Priority: …
- Clip Worthy: …
- Duration Class: …
- Shot Type Suggestion: …
- Camera Movement Suggestion: …
- Mood: …
- Subject Focus: …
- Scene Focus: …
- Prop Focus: …
- Narration Anchor Line: …
- Visual Core: …
- Dramatic Focus: …
- Continuity Notes: …
- Emotional Pressure: …
- Strongest Single Frame Interpretation: …
- Strongest Motion Interpretation: …
- Shot Design: …
- Camera Intent: …
```

## JSON 代码块要求

- 文末必须包含一个合法 JSON 代码块。
- 代码块外不要再追加解释文字。
- 运行时只会解析 fenced JSON code block。没有字面量 ```json 开头和 ``` 结尾，就会失败。
- Markdown 明细结束后，必须立即输出下面形式的 fenced block：

````text
```json
{
  "project_title": "...",
  "source_file": "...",
  "beats": []
}
```
````

- 顶层结构必须至少包含：

```json
{
  "project_title": "项目名",
  "source_file": "novel.txt",
  "beats": []
}
```

- `beats` 内每个对象必须包含本步骤要求的全部字段，包括原有生产字段和新增 scene dramatization 字段。
- `beat_id` 应稳定、可读、可排序，例如 `b001`、`b002` 或 `ch01_b01`。
- `chapter_id` 应反映原文章节或你推断出的序列编号。

## 质量要求

- 保持故事顺序。
- 明确 hook、turn、payoff、cliffhanger 的叙事作用。
- 不是每个 beat 都必须值得做完整视频 clip。
- 要为步骤三到步骤五提供足够稳定的信息，但不要提前把它写成最终提示词。
- 每个高优先级或 clip-worthy beat 都必须像可执行的 storyboard beat，而不是数据表行。
- 相邻 beats 必须能看出连续性和差异性：观众在看什么先变了，什么必须保持不变。
- 禁止把 scene dramatization 写成空泛形容词列表；所有新增字段都要服务于可见画面、戏剧压力和后续 prompt rendering。
- 禁止为了 cinematic wording 改变资产事实，尤其是车辆、道具和服装类别。
- 完整性优先级：合法 fenced JSON sidecar > 字段完整 > Markdown 美观 > 文字丰富度。
