# 步骤四：输出关键帧提示词

## 执行目标

- 基于视觉节拍表和资产注册表，为 FLUX.2 klein 生成关键帧/锚帧提示词。
- 这些提示词必须服务于 still-image generation，而不是视频运动生成。
- 每条提示词应对应一个可控、清晰、单帧成立的画面方案。
- 关键变化：不要从 beat 字段机械拼接提示词；必须先读取 beat 的 scene dramatization，再渲染成强静帧场景提示词。

## 核心原则

### 1. 关键帧提示词是强单帧场景计划，不是 prose 改写

- 不要直接复制小说 prose 或旁白句子。
- 不要写成 recap 式描述。
- 不要写成多阶段动作过程。
- 一条关键帧提示词只描述一个稳定画面。
- 这个稳定画面必须是该 beat 的“最强单帧版本”，而不是字段摘要。

### 2. 先做 scene rendering，再填记录字段

每个可生成的 beat 必须先合成一个内部 still-frame design：

- 这个 beat 最有冲击力的一帧是什么？
- 观众第一眼必须注意谁或什么？
- 上一 beat 继承来的服装、地点、道具状态、情绪状态哪些必须保持连续？
- 这一帧和前后 beat 的画面差异是什么？
- 哪个主体最重要，哪个环境信息必须支撑戏剧压力，哪个道具必须被看见？
- 构图、光线、机位如何把 `dramatic_focus` 和 `emotional_pressure` 变成可见画面？

然后才输出字段和 `anchor_image_prompt`。

### 3. 关键帧提示词必须强调可见构图

每条记录至少要明确：
- `shot_size`
- `subject`
- `environment`
- `main_object`
- `composition`
- `lighting`
- `visible_state`
- `style`
- `anchor_image_prompt`

### 4. 生成 `anchor_image_prompt` 时优先使用这些 beat 字段

- `strongest_single_frame_interpretation`
- `shot_design`
- `camera_intent`
- `dramatic_focus`
- `visual_core`
- `continuity_notes`
- `emotional_pressure`
- `subject_focus`
- `scene_focus`
- `prop_focus`

这些字段是提示词素材，不是要逐项复制到最终 prompt。最终 prompt 必须读起来像一条强图像生成指令，而不是 metadata dump。

## 视觉风格渲染规则

如果输入或运行时提供 `visual_style`、`style` 或资产注册表中包含风格线索，必须按其渲染。如果没有明确风格，保持资产注册表中最稳定的风格，不要自行改变项目美术方向。

### 风格映射

- `realism` / `写实`：写实电影静帧，真实镜头质感，可信材质，真实皮肤/金属/织物，环境光有方向性，避免插画化。
- `2D` / `anime` / `动漫`：高质量 2D 动画/漫画插画，清晰线条，绘制感阴影，电影级构图，避免照片级真实渲染。
- `3D`：默认使用 `anime_donghua_3d` 子类型，除非用户或运行时明确指定其他 `3d_style_variant`。

### 3D 子类型机制

当 `visual_style = 3D` 或 `style = 3D` 时，内部解析：

- 默认：`3d_style_variant = anime_donghua_3d`
- 可选/旧版：`western_family_3d`
- 可选：`realistic_cg_3d`

不要要求用户额外输入。只有当上游明确给出 `3d_style_variant` 时才覆盖默认值。

### 默认 3D：`anime_donghua_3d`

3D 锚帧提示词默认应注入这些风格特征：

- anime-inspired 3D character design
- donghua-style facial structure
- stylized cinematic East Asian CG
- sharper silhouettes
- clean line of action
- elegant proportions
- dramatic cinematic lighting
- refined material rendering
- stylized but not toy-like
- expressive eyes without exaggerated childlike proportions
- premium East Asian CG fantasy/drama feel
- less rounded, less plush, less comedic by default

3D 锚帧提示词必须避免默认漂移到：

- Pixar-like
- Disney-like
- overly rounded children's animation
- toy-like proportions
- chibi-like face shapes unless explicitly requested
- soft plastic-looking material treatment
- exaggerated family-film expression style

如果需要负向约束，可以在 `anchor_image_prompt` 末尾用短语加入：`not Pixar-like, not Disney-like, not toy-like, not chibi, not plush rounded family animation`。

## prompt 写法要求

### 好的 anchor prompt 应该像这样

- 一个具体的电影静帧。
- 有主体优先级：谁最重要，观众先看哪里。
- 有环境压力：雨、灯、玻璃、工厂空旷、赛道热浪、会议室冷光等不是装饰，而是服务戏剧。
- 有构图意图：前景压迫、中景动作、背景信息、负空间、反射、遮挡、低角度或俯视关系。
- 有连续性：泥水、服装、伤痕、车灯、账本、发动机、奖杯、夜色等可见状态不能断。
- 有资产类型锁定：角色、车辆、道具、服装和环境不得被 cinematic 改写改变类别。摩托车/赛车摩托必须一直写为 motorcycle / bike / racing motorcycle，不要写成 car；motorcycle frame 不要写成 car chassis；车辆比例、轮胎数量和骑乘关系必须保持正确。
- 对 `ZXMOTO 820RR-RS`，必须写成 racing motorcycle / sportbike / motorcycle，禁止写 car、race car、automobile、vehicle body as car。可以写 fairing、bodywork、front wheel、rear wheel、rider posture、lean angle。
- 有风格语言：按 realism / 2D / 3D 正确渲染。

### 避免这些失败模式

- 过度字典化：`subject:..., environment:..., prop:...` 直接拼成一句。
- prompts 读起来像 metadata list。
- 画面正确但没有戏剧焦点。
- 有构图词但没有真实场景压力。
- 把 `summary` 或 `narration_anchor_line` 改写成 prose。
- 多阶段动作塞进一张图。
- 忽略相邻 beat 的身份、服装、地点、道具状态连续性。
- 3D 模式自动写成 Pixar / Disney / rounded family animation。
- 为了让画面“更电影化”而改写资产事实，例如把摩托车改成汽车、把车架改成汽车底盘、把账本改成屏幕、把工厂改成赛场。
- 在摩托车项目中用 `car`、`race car`、`automobile` 描述 `820RR-RS` 或其他两轮赛车。

### FLUX.2 klein 适配

- 使用清晰、具体、可控的视觉描述。
- 保持单帧，不写运动延展。
- 风格词要短而明确，不要堆砌互相冲突的美术方向。
- 如果资产注册表已有角色/场景/道具描述，必须保持身份一致，但不要把资产长提示词全文塞入每条 anchor prompt。

## 不是所有 beat 都必须生成关键帧

- 优先覆盖 `clip_worthy = yes` 的 beat。
- 对视觉上具有定义作用的 `maybe` beat 也可生成关键帧。
- 如果某个 beat 只适合做旁白过渡且无明确静帧价值，可以跳过。

## 输出结构要求

你必须输出一个完整可读文本，并在文末且只在文末提供 **一个** fenced `json` 代码块。

### 可读文本部分建议结构

```text
# 关键帧提示词

## beat_001
- Linked Assets: …
- Shot Size: …
- Subject: …
- Environment: …
- Main Object: …
- Composition: …
- Lighting: …
- Visible State: …
- Style: …
- Anchor Image Prompt: …
```

### JSON 代码块要求

- 文末必须包含一个合法 JSON 代码块。
- 运行时只会解析 fenced JSON code block。没有字面量 ```json 开头和 ``` 结尾，就会失败。
- 可读文本结束后，必须立即输出下面形式的 fenced block，且 fenced block 后不要再写任何文字：

````text
```json
{
  "project_title": "...",
  "anchor_prompts": []
}
```
````

- 顶层结构必须至少包含：

```json
{
  "project_title": "项目名",
  "anchor_prompts": []
}
```

- `anchor_prompts` 中每个对象必须至少包含：
  - `prompt_id`
  - `beat_id`
  - `linked_assets`
  - `shot_size`
  - `subject`
  - `environment`
  - `main_object`
  - `composition`
  - `lighting`
  - `visible_state`
  - `style`
  - `anchor_image_prompt`

## 质量要求

- 关键帧提示词必须明显区别于视频提示词。
- 重点是“这一帧看起来是什么”，不是“接下来发生什么”。
- 输出必须适合作为后续视频步骤的 anchor reference，而不是替代视频提示词本身。
- 每条 `anchor_image_prompt` 都要像真正的视觉镜头计划：有第一视觉重点、戏剧压力、构图组织、光线意图、连续性约束和风格一致性。
