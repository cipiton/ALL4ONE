# 步骤三：提炼资产注册表

## 执行目标

- 基于旁白脚本和视觉节拍表，提炼后续生成环节需要复用的资产注册表。
- 让角色、场景、道具、车辆、服装变体和状态变体以统一注册方式被后续步骤引用。
- 避免每个 beat 各写一套不一致的角色/场景描述。

## 核心原则

### 1. 资产要为复用服务

- 优先提炼会跨多个 beat 出现或对剧情推进重要的资产。
- 单次出现且不重要的临时细节，不必强行注册。
- 资产注册表不是故事摘要，也不是提示词清单。

### 2. 资产分类要明确

`asset_type` 仅使用这些类别：
- `character`
- `environment`
- `prop`
- `vehicle`
- `wardrobe`
- `state_variant`

### 2.1 资产类型事实必须锁定

- 资产注册表必须消除后续提示词的歧义，而不是制造歧义。
- 如果源故事是摩托车、机车、motorcycle、motorbike、bike、rider、骑手、排气、前叉、轮胎、车架、赛道压弯等语境，相关车辆必须注册为 `vehicle`，并在 `short_description` 和 `consistency_notes` 中明确写成 `racing motorcycle` / `sportbike` / `摩托赛车`。
- `ZXMOTO 820RR-RS` 在本项目中必须视为 **racing motorcycle / sportbike / 摩托赛车**，不要写成 car、race car、automobile、汽车赛车。
- 中文 `赛车` 可能被下游误解为 car；涉及摩托车项目时，资产名建议写 `ZXMOTO 820RR-RS 摩托赛车` 或 `ZXMOTO 820RR-RS racing motorcycle`。
- `motorcycle frame` / `摩托车车架` 不要写成 `car chassis` / `汽车底盘`。
- 车辆比例、轮胎数量、骑乘关系、车手姿态和赛道方向必须在 `consistency_notes` 中明确锁定。

### 3. 每个资产至少包含这些字段

- `asset_id`
- `asset_type`
- `asset_name`
- `short_description`
- `recurrence_importance`
- `linked_beats`
- `generation_priority`
- `consistency_notes`

值域要求：
- `recurrence_importance` 仅允许：
  - `core`
  - `recurring`
  - `supporting`
- `generation_priority` 仅允许：
  - `high`
  - `medium`
  - `low`

### 4. consistency_notes 要写得可执行

- 用于约束后续生成一致性。
- 应尽量具体，例如：
  - 面部、体型、发型、年龄感
  - 服装/颜色/配件
  - 场景布局、材质、时间状态
  - 道具外观、磨损、标志特征
- 不要写空泛评价。

## 输出结构要求

你必须输出一个完整可读文本，并在文末且只在文末提供 **一个** fenced `json` 代码块。

### 可读文本部分建议结构

1. 标题
2. 资产总览
3. 按类别分组：
  - 角色
  - 场景/环境
  - 道具
  - 车辆
  - 服装/造型
  - 状态变体

### JSON 代码块要求

- 文末必须包含一个合法 JSON 代码块。
- 顶层结构必须至少包含：

```json
{
  "project_title": "项目名",
  "source_file": "novel.txt",
  "assets": []
}
```

- `assets` 中每个对象必须包含本步骤要求的全部字段。
- `linked_beats` 必须是 beat_id 数组。

## 质量要求

- 资产命名应稳定、可复用、避免歧义。
- 不要把同一角色拆成多个重复资产，除非确实存在造型或状态变体。
- 不要把抽象概念写成资产。
- 输出必须能直接服务步骤四和步骤五，而不是再解释一遍剧情。
- 禁止把摩托车资产注册成汽车资产；如果源文含 `820RR-RS`、motorcycle、bike 或 rider，必须用 motorcycle/sportbike 语义锁定。
