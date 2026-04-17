# 步骤五：输出视频提示词

## 执行目标

- 基于视觉节拍表、资产注册表和关键帧提示词，为 LTX-2 生成 motion-first 视频提示词。
- 默认关键帧已经建立主体、场景与风格，因此视频提示词应重点描述“接下来发生什么”。
- 输出必须比关键帧提示词更短、更明确、更偏运动和镜头控制。
- 关键变化：视频 prompt 必须从 beat 的 scene dramatization 和 anchor frame 共同推导，像锚帧的自然运动延续，而不是重新写一个新场景。

## 核心原则

### 1. 不要重写整张静帧

- 不要重新把 subject、environment、style 全部从头讲一遍。
- 只在理解动作所必需时补充静态信息。
- 重点是动作、环境变化、反应和镜头行为。
- 任何身份、服装、地点、道具、风格描述都应作为 continuity cue，而不是新场景重写。

### 2. 先做 motion continuation，再填记录字段

每个视频提示词必须先回答：

- 从 anchor frame 的下一秒开始，什么可见内容发生变化？
- 人物的动作如何推进 `dramatic_focus`？
- 环境如何动：雨、烟、灯光、热浪、人群、反射、尘土、机器震动、屏幕数据等。
- 镜头为什么这样动：跟随、逼近、拉开、揭示、压迫、稳定观察、制造速度感。
- 什么必须保持连续：角色身份、服装、道具位置、车辆比例、场景方向、光线状态、情绪递进。
- 这一条 video prompt 和前后 beats 的运动有何区别？
- 运动不能改变资产类别：摩托车仍是 motorcycle / bike / racing motorcycle，不能变成 car；motorcycle frame 不能变成 car chassis；车辆比例、骑乘方式、轮胎数量、赛道方向和道具状态必须稳定。
- 对 `ZXMOTO 820RR-RS`，动作必须按 motorcycle/sportbike 运动写：rider leans, front wheel, rear wheel, fairing, throttle, braking, apex, lean angle。禁止写 car、race car、automobile、driver cockpit。

### 3. prompt 必须 motion-first

每条记录至少要明确：
- `motion_focus`
- `environment_motion`
- `character_action`
- `camera_movement`
- `pacing`
- `video_prompt`

### 4. 生成 `video_prompt` 时优先使用这些信息

- `strongest_motion_interpretation`
- `camera_intent`
- `continuity_notes`
- `emotional_pressure`
- `dramatic_focus`
- 对应 anchor prompt 的 `visible_state`
- 对应 anchor prompt 的构图和主体优先级

这些字段必须被合成为运动设计，不要机械复制字段名或字段内容。

### 5. camera-aware，但不要滥写镜头花活

- 镜头运动必须服务于动作和信息呈现。
- 优先使用清晰可执行的镜头语言，例如：
  - `slow push in`
  - `static frame`
  - `pan right revealing`
  - `handheld follow`
  - `slow tilt up`
  - `low tracking follow`
  - `subtle dolly out`
- 不要堆砌复杂镜头术语。
- 不要让镜头运动和角色动作互相冲突。

## LTX-2 写法要求

### 好的 video prompt 应该像这样

- 从锚帧继续：`From the anchor frame, ...`
- 先写最重要的可见运动。
- 再写次级环境运动。
- 再写镜头行为和节奏。
- 最后加稳定性约束：身份、服装、道具、比例、风格、场景方向保持不变。

### 推荐结构

```text
From the anchor frame, [main subject action]. [Environment motion / object motion]. [Camera movement and pacing]. Keep [identity / wardrobe / location / prop state / style] stable.
```

### 避免这些失败模式

- 把 anchor prompt 重新完整复述一遍。
- video prompt 读起来像 recap summary。
- 只有情绪，没有可见动作。
- 只有镜头术语，没有主体行为。
- 多个重大事件塞进一条视频 prompt。
- 从一个锚帧跳到新地点或新时间。
- 忽略连续性，导致人物身份、服装、车辆比例、道具状态漂移。
- 把静帧构图词当成运动设计。
- 让视频 prompt 比 anchor prompt 更像图像提示词。
- 把资产换类或换物，例如把摩托车运动写成汽车运动，或把一个道具写成另一个道具。
- 在摩托车或骑手语境中使用 car / race car / driver cockpit 这类汽车词。

### 运动与戏剧压力

视频 prompt 必须把 `emotional_pressure` 变成可见动作：

- 被拒绝：身体后退、手停住、雨中僵住、车灯远离。
- 债务/坚持：手指划过账本、螺丝拧紧、灯光闪烁、疲惫但动作不停。
- 冲突：对方目光逼近、主角站稳、手掌落在桌面、会议室空气凝住。
- 胜利：车辆冲线、热浪抖动、人群起身、维修区反应爆发。
- 回望过去：人物缓慢靠近、影像微微颤动、镜头拉开揭示空间。

## 不是每个 beat 都要生成视频提示词

- 优先覆盖 `clip_worthy = yes` 的 beat。
- 对 `clip_worthy = maybe` 的 beat，只有当其具有明确运动价值时才生成。
- 对 `clip_worthy = no` 或明显只适合静帧/旁白支撑的 beat，可以不生成。

## 输出结构要求

你必须输出一个完整可读文本，并在文末且只在文末提供 **一个** fenced `json` 代码块。

### 可读文本部分建议结构

```text
# 视频提示词

## beat_001
- Linked Anchor Prompt: …
- Linked Assets: …
- Motion Focus: …
- Environment Motion: …
- Character Action: …
- Camera Movement: …
- Pacing: …
- Video Prompt: …
```

### JSON 代码块要求

- 文末必须包含一个合法 JSON 代码块。
- 运行时只会解析 fenced JSON code block。没有字面量 ```json 开头和 ``` 结尾，就会失败。
- 可读文本结束后，必须立即输出下面形式的 fenced block，且 fenced block 后不要再写任何文字：

````text
```json
{
  "project_title": "...",
  "video_prompts": []
}
```
````

- 顶层结构必须至少包含：

```json
{
  "project_title": "项目名",
  "video_prompts": []
}
```

- `video_prompts` 中每个对象必须至少包含：
  - `prompt_id`
  - `beat_id`
  - `linked_anchor_prompt_id`
  - `linked_assets`
  - `motion_focus`
  - `environment_motion`
  - `character_action`
  - `camera_movement`
  - `pacing`
  - `video_prompt`

## 质量要求

- 视频提示词必须与关键帧提示词区分清楚。
- 关键帧提示词回答“这一帧是什么”；视频提示词回答“这一帧之后怎么动、镜头怎么跟”。
- 不要输出 recap 风格 prose。
- 不要输出只有情绪没有动作的空泛描述。
- 输出必须适合后续 LTX-2 使用。
- 每条 video prompt 都必须像锚帧的下一秒：运动明确、镜头服务戏剧压力、连续性稳定、视觉变化可执行。
