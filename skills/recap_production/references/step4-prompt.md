# 步骤四：输出视频场景脚本

## 执行目标

- 基于已确认的解说剧剧本、资产清单、生图配置，为 recap/短剧解说视频生成每集可执行的视觉规划。
- 这是视频场景规划步骤，不是最终配音或剪辑时间轴步骤。
- 每个 scene beat 都必须被视为一个共享规划单元，同时服务于：
  - 视觉生成
  - 旁白锚点对齐
  - 后续装配与剪辑统筹
- 输出必须同时满足：
  - 人类可读：方便人工审阅和后续剪辑统筹
  - 机器可读：方便后续媒体生成、镜头资产准备、装配流程使用

## 核心原则

### 1. 按视觉/叙事节拍拆分，而不是按句子硬切

- 每集拆成 **8 到 14 个 scene beats**
- 每个 scene beat 必须代表一个明确且单一的视觉/叙事单位
- 一个 beat 内不要塞入多个重大转折、多个核心揭示、或多个独立行动结果
- 可以把连续描述合并成一个更强的视觉场面
- 不要把每一句旁白都变成一个镜头
- 不要过 sparse，也不要过 granular

### 2. 让 Step 4 成为视觉与旁白的共享规划层

- 每个 beat 都必须能被后续用于：
  - narration chunking
  - TTS 对齐准备
  - media asset generation
  - edit assembly
- `anchor_text` 必须在实践中视为必填
- `anchor_text` 应是短而清晰的旁白对齐语句或短语，只锚定该 beat 的核心信息
- `pace_weight` 仅提供相对节奏提示，不代表真实时长
- 不要输出任何逐秒时码或最终时长

### 3. 先考虑故事推进，再考虑镜头包装

- 开头 hook：更抓眼、更冲突、更具悬念
- 中段核心剧情：强调关系变化、反转推进、信息递进
- 转折位：用 `turn` 明确标出关系变化、认知变化或局势变化
- 结尾 cliffhanger：更强烈、更留钩子、方便下集承接
- 输出要像可直接用于 recap 视频策划的“视觉打点脚本”

### 4. 让 prompt 可用于后续资产生成

- `visual_prompt` 必须具有明确可视化内容
- 结合已有角色/场景/道具设定，尽量与上游资产风格保持一致
- 体现短剧/解说视频常见的强戏剧感、强情绪、强信息密度
- 避免空泛描述，如“一个女人很伤心”“一个男人很坏”
- 避免多个 scene beat 只是重复同一构图、同一动作、同一情绪

### 5. 维持连续性与视觉多样性

- 相邻 beats 默认应维持角色身份、服装、所在地点、时间状态、情绪走势的一致性
- 只有故事明确发生变化时，才改变 wardrobe、location、time-of-day、或 emotional state
- 如果发生变化，要让 `summary`、`anchor_text` 和 `visual_prompt` 都能看出变化原因
- 相邻 beats 不要机械重复同一种 shot distance 和 camera motion，除非这种重复是刻意用于压迫感、对峙感或循环感

### 6. 暂不绑定 TTS 时间

- 不要写逐秒时长、镜头秒数、配音时码、节拍点
- 不要输出最终 TTS timing
- 先完成故事、视觉和相对节奏规划

## 每个 scene beat 必须包含的字段

- `scene_id`
  - 格式：`ep01_s01`、`ep01_s02`
- `summary`
  - 1 句简洁描述这个视觉节拍的核心事件
- `visual_prompt`
  - 面向后续图像/视频资产生成的详细提示词
  - 必须包含人物、环境、动作、光线、情绪或画面重点
- `shot_type`
  - 使用简洁英文或行业常见表述，例如：
    - `close-up`
    - `medium close-up`
    - `medium shot`
    - `wide shot`
    - `over-the-shoulder`
    - `insert`
- `camera_motion`
  - 使用简洁可执行描述，例如：
    - `static`
    - `slow push in`
    - `slow dolly out`
    - `pan left`
    - `pan right`
    - `handheld drift`
- `mood`
  - 1 到 3 个词，概括氛围，例如：
    - `suspenseful`
    - `bitter`
    - `tense`
    - `triumphant`
- `anchor_text`
  - 必填
  - 必须是短的 narration-aligned line 或 phrase
  - 只锚定当前 beat 的核心信息，不要跨多个 beat 复合描述
- `priority`
  - 必填
  - 仅允许：`high` / `medium` / `low`
- `beat_role`
  - 必填
  - 仅允许：`hook` / `development` / `turn` / `cliffhanger`
- `pace_weight`
  - 必填
  - 仅允许：`short` / `medium` / `long`
  - 这是相对节奏提示，不是真实时长
- `asset_focus`
  - 必填
  - 仅允许：`character` / `interaction` / `environment` / `object` / `montage`

## 字段使用规则

- `anchor_text`
  - 用于后续字幕/旁白对齐
  - 要短、清晰、可单独成立
- `priority`
  - `high`：关键钩子、关键反转、关键情绪冲击、关键结尾
  - `medium`：承上启下的重要推进 beat
  - `low`：过渡、补充、铺垫，但仍然有存在价值
- `beat_role`
  - `hook`：开头抓力 beat
  - `development`：剧情推进与信息递进
  - `turn`：关系、认知、局势、策略出现变化
  - `cliffhanger`：结尾悬念或强收口 beat
- `pace_weight`
  - `short`：适合快节奏打点、短信息冲击、插入镜头
  - `medium`：标准推进 beat
  - `long`：需要更完整表演、情绪停留、或较复杂画面信息的 beat
- `asset_focus`
  - `character`：以人物状态或单人表现为主
  - `interaction`：以人物关系、动作互动、冲突交换为主
  - `environment`：以空间、地点、氛围建立为主
  - `object`：以关键道具、证据、屏幕信息、细节特写为主
  - `montage`：以组合画面、变化过程、连续推进为主

## 输出结构要求

你必须输出一个完整的 Markdown 文档，并且在文末提供且只提供 **一个** fenced `json` 代码块。

### Markdown 部分必须包含

1. 标题
2. 系列概览（1 段即可）
3. 每集独立章节
4. 每集的：
   - 集数
   - 节奏说明（hook / development / turn / cliffhanger 如何组织）
   - scene beats 明细

### 推荐 Markdown 呈现方式

每集可使用以下结构：

```text
## 第1集

节奏说明：……

### ep01_s01
- Summary: …
- Shot Type: …
- Camera Motion: …
- Mood: …
- Anchor Text: …
- Priority: …
- Beat Role: …
- Pace Weight: …
- Asset Focus: …
- Visual Prompt: …
```

## JSON 代码块要求

- 文末必须包含一个可被直接解析的 `json` 代码块
- 代码块外不要再补充解释性文字
- JSON 必须是合法 JSON
- 顶层结构建议如下：

```json
{
  "series_title": "双面女巫",
  "episodes": [
    {
      "episode_number": 1,
      "scene_beats": [
        {
          "scene_id": "ep01_s01",
          "summary": "……",
          "visual_prompt": "……",
          "shot_type": "medium shot",
          "camera_motion": "slow push in",
          "mood": "suspenseful",
          "anchor_text": "……",
          "priority": "high",
          "beat_role": "hook",
          "pace_weight": "short",
          "asset_focus": "interaction"
        }
      ]
    }
  ]
}
```

## JSON 字段要求

- `series_title`: 系列标题
- `episodes`: 分集数组
- 每集对象至少包含：
  - `episode_number`
  - `scene_beats`
- 每个 `scene_beats` 项必须包含：
  - `scene_id`
  - `summary`
  - `visual_prompt`
  - `shot_type`
  - `camera_motion`
  - `mood`
  - `anchor_text`
  - `priority`
  - `beat_role`
  - `pace_weight`
  - `asset_focus`

## 质量要求

- 每个 beat 都要有清晰叙事推进
- 每个 beat 只承载一个主要视觉/叙事动作
- 开头 1-2 个 beat 必须更有抓力
- 结尾 1-2 个 beat 必须更有钩子感
- prompts 必须保持视觉具体，不要空泛
- beats 不要太 sparse，也不要太 granular
- 尽量利用已知角色、场景、道具，减少泛化画面
- 避免重复 prompt、重复视觉语法、重复镜头组织
- 输出必须能作为后续 narration/video alignment 的共享规划层

## 禁止事项

- 不要输出逐镜头秒数
- 不要输出最终 TTS timing
- 不要输出最终 TTS duration 字段
- 不要把每句旁白都拆成一个 scene beat
- 不要把多个重大揭示塞进同一个 beat
- 不要只写笼统 prompt
- 不要输出无效 JSON
- 不要在最终 `json` 代码块之后继续输出说明文字
