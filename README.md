# ONE4ALL

A shared terminal-based LLM workflow runner for recap analysis, long-novel adaptation, episode script generation, rewriting, story creation, and large-text preprocessing.  
一个基于终端的共享 LLM 工作流运行器，用于解说分析、长篇小说改编、剧集脚本生成、重写、故事创作以及大文本预处理。

---

## What this project is
## 项目简介

ONE4ALL is a skill-driven Python app built around a shared runtime.  
ONE4ALL 是一个以技能驱动的 Python 应用，构建在共享运行环境之上。

Instead of creating a separate app for each workflow, the project uses:  
该项目并非为每个工作流创建独立的程序，而是采用了：

- a single entrypoint: `run.py`  
  统一入口：`run.py`
- a shared execution engine in `engine/`  
  `engine/` 中的共享执行引擎
- a registry of skills in `skills/registry.yaml`  
  `skills/registry.yaml` 中的技能注册表
- one `SKILL.md` per skill for behavior, steps, prompts, and runtime rules  
  每个技能拥有独立的 `SKILL.md`，定义其行为、步骤、提示词及运行规则

This makes it easier to add or evolve workflows without rebuilding the whole app.  
这使得在不重构整个应用的情况下，添加或演进工作流变得更加容易。

---

## Main use cases
## 主要使用场景

ONE4ALL is especially suited for:  
ONE4ALL 特别适用于：

- long Chinese novel adaptation  
  长篇中文小说改编
- short-drama planning  
  短剧规划
- short-drama episode script generation  
  短剧单集脚本生成
- recap analysis and recap production  
  解说分析与解说内容制作
- project-scoped rewriting / refresh workflows  
  项目级的重写 / 刷新工作流
- large novel preprocessing and chunking  
  大体量小说预处理与分块
- original microseries story package generation  
  原创微短剧故事包生成

---

## Current skills
## 当前技能库

### 1. Recap Analysis
### 解说分析
Analyze recap inputs and generate structured reports.  
分析解说输入内容并生成结构化报告。

### 2. Recap Production
### 解说制作
Run a resumable recap-production workflow.  
运行可中断 / 续传的解说制作工作流。

### 3. Novel 2 Script
### 小说转剧本
Run a broader multi-step novel-to-script production pipeline.  
运行更宽泛的多步骤小说转剧本生产流水线。

### 4. Recap To TTS
### 解说转配音
Convert recap scripts into episode-level narration WAV files with the isolated local Qwen TTS runner.  
将解说稿转换为分集旁白 WAV，并调用隔离的本地 Qwen TTS 运行器。

### 5. Recap To Comfy Bridge
### 解说桥接到 Comfy
Stage 04 bridge: convert a `02_recap_production` bundle into canonical `assets.json`, legacy VideoArc-style assets, and storyboard JSON.  
第 04 阶段桥接：将 `02_recap_production` 产物包转换为规范 `assets.json`、兼容旧链路的 VideoArc 资产 JSON 和 storyboard JSON。  

### 6. Recap To Assets Z-Image
### 解说资产生图 Z-Image
Generate character, scene, and prop images from `assets.json` by calling the local Z-Image-Turbo backend.  
通过调用本地 Z-Image-Turbo，根据 `assets.json` 生成角色、场景和道具图片。

### 7. Recap To Keyscene Kontext
### 解说关键帧 Kontext
Generate one keyscene I2I image per storyboard beat by injecting stage-04 storyboard data and stage-05 T2I assets into a ComfyUI Flux Kontext API workflow.  
通过将第 04 阶段分镜数据与第 05 阶段 T2I 资产注入 ComfyUI Flux Kontext API 工作流，为每个 storyboard beat 生成一张 I2I 关键帧。

### 8. Novel Adaptation Plan
### 小说改编计划
Turn long-form source material into a structured short-drama adaptation plan.  
将长篇源素材转化为结构化的短剧改编计划。

### 9. Novel-to-Drama Script
### 小说转短剧脚本
Generate short-drama episode scripts from the adaptation plan.  
根据改编计划生成短剧单集脚本。

### 10. Rewriting
### 重写
Create a refresh bible and rewrite script text with consistent refreshed characters, objects, and terms.  
创建刷新设定集并在重写剧本时保持人物、物品和术语的一致性。

### 11. Story Creation
### 故事创作
Generate an original microseries story package from a short brief.  
根据简短的创意梗概生成原创微短剧故事包。

### 12. Large Novel Processor
### 大体量小说处理器
Split oversized novel `.txt` files into chapter/chunk outputs plus an index for downstream workflows.  
将超大容量的小说 `.txt` 文件拆分为章节 / 块，并为下游工作流生成索引。

---

## Installation
## 安装

From the repo root:  
在项目根目录下执行：

```bash
python -m pip install -r requirements.txt
```

Recommended:  
建议：

- Python 3.10+  
  Python 3.10 或更高版本
- a valid API key / provider setup in `config.ini` or environment variables  
  在 `config.ini` 或环境变量中配置有效的 API 密钥 / 供应商信息

---

## Run the app
## 运行应用

```bash
python run.py
```

### Desktop GUI
### 桌面图形界面

```bash
python gui.py
```

The runner will:  
运行器将：

- show the available skills  
  显示可用技能
- let you choose a skill  
  让你选择一个技能
- ask for the required input(s)  
  询问所需的输入文件 / 信息
- run the selected workflow  
  运行选定的工作流
- keep the session open so you can run another job  
  保持会话开启，以便你运行下一个任务

The desktop GUI provides:  
桌面 GUI 提供：

- a guided chat-style Run workspace with a left skill sidebar  
  带有左侧技能栏的引导式对话运行工作区
- a Settings page for provider/model/API-key configuration plus workspace and project defaults  
  设置页面，用于配置供应商、模型、API 密钥以及工作区和项目的默认设置
- a Logs page for live backend output while a job is running  
  日志页面，用于在任务运行时查看实时后端输出

### GUI notes
### GUI 说明

- install `customtkinter` from `requirements.txt`  
  从 `requirements.txt` 中安装 `customtkinter`
- the GUI auto-accepts the existing backend review checkpoints in v1  
  在 v1 版本中，GUI 会自动接受现有的后端审核检查点
- the GUI can group work under `workspace_root/<project>/inputs` and `workspace_root/<project>/outputs`  
  GUI 会将工作按项目分组存储在 `workspace_root/<project>/inputs` 和 `workspace_root/<project>/outputs` 下
- the active project now lives in Settings, while Run uses a guided conversation to collect the next needed input  
  当前活跃项目现位于设置中，而运行页面通过引导式对话收集下一步所需的输入
- skills that support inline text input accept direct pasted text in the Run conversation composer  
  支持内联文本输入的技能允许在对话框中直接粘贴文本
- finished runs show result cards with actions like Open, Open Folder, Preview, Copy, and Save As  
  运行完成后会显示结果卡片，包含打开、打开文件夹、预览、复制和另存为等操作

---

## Repository structure
## 仓库结构

```text
ONE4ALL/
├─ app/
├─ engine/
├─ skills/
│  ├─ registry.yaml
│  └─ <skill_name>/
│     └─ SKILL.md
├─ outputs/
├─ run.py
├─ gui.py
├─ config.ini
├─ requirements.txt
└─ README.md
```

> Repository structure diagram as provided in original text.  
> 仓库结构图如原件所示。

---

## Core concepts
## 核心概念

### Skills
### 技能

Each workflow is defined as a skill. A skill typically includes:  
每个工作流都被定义为一个技能。一个技能通常包含：

- `SKILL.md`  
  `SKILL.md` 文件
- optional prompt/reference files  
  可选的提示词 / 参考文件
- optional deterministic helper scripts  
  可选的确定性辅助脚本
- metadata for routing, steps, and runtime prompts  
  用于路由、步骤和运行时提示的元数据

### Shared runtime
### 共享运行时

The shared runtime handles:  
共享运行时负责处理：

- menu display  
  菜单显示
- input routing  
  输入路由
- folder/file handling  
  文件夹 / 文件处理
- step execution  
  步骤执行
- review loops  
  审核循环
- model routing  
  模型路由
- output creation  
  输出生成
- oversized text handling  
  超大文本处理

### Output roots
### 输出根目录

Outputs are usually written under one of these patterns:  
输出内容通常写入以下两类路径之一：

```text
outputs/<skill>/<job_or_project>/
outputs/stories/<story_slug>/<run_id>/<stage_folder>/
```

The recap pipeline now uses the story-first structure so related stages for one story share the same run root.  
解说流水线现在使用故事优先结构，因此同一故事的相关阶段会共享同一个运行根目录。  

Current recap pipeline stages:  
当前解说流水线阶段：  

```text
01_recap_analysis
02_recap_production
03_recap_to_tts
04_recap_to_comfy_bridge
05_assets_t2i
06_keyscene_i2i
07_clips_flf2v
08_final
```

---

## Large text support
## 大文本支持

LLM-backed `.txt` skills support shared large-text ingestion.  
基于 LLM 的 `.txt` 技能支持共享的大文本摄取。

When a `.txt` input is too large for safe single-pass processing, the runtime can:  
当输入的 `.txt` 文件太大，无法通过单次处理完成时，运行时可以：

- detect oversize input  
  检测超大输入
- switch into project ingestion mode  
  切换到项目摄取模式
- auto-split or consume a chunked project  
  自动分块或读取已分块的项目
- build continuity state  
  构建连续性状态
- synthesize a `master_outline.txt`  
  合成一份主大纲 `master_outline.txt`
- continue the skill from the consolidated result  
  从整合后的结果继续执行技能

Typical intermediate artifacts include `project_state.json`, `continuity_log.json`, and `master_outline.txt`.  
典型的中间产物包括项目状态文件、连续性日志以及主大纲。

---

## Model routing
## 模型路由

The runtime supports model routing by phase.  
运行时支持按阶段进行模型路由。

Typical routing pattern:  
典型的路由模式：

- fast model for mechanical or intermediate work  
  快速模型：用于机械性或中间环节的工作
- strong model for final deliverables and polish  
  强力模型：用于最终交付物和润色

---

## Skill details
## 技能详情

### 1. Recap Analysis
### 解说分析

Analyze one or more novel `.txt` files and generate structured recap-fit analysis including title, premise, and adaptation suitability.  
分析一个或多个小说 `.txt` 文件，并生成适合做解说的结构化分析报告，包含标题、前提以及改编适合度等。

### 4. Novel Adaptation Plan
### 小说改编计划

Convert long-form source material into a structured short-drama adaptation plan. This is the planning layer of the main adaptation workflow.  
将长篇源素材转化为结构化的短剧改编计划。这是主改编工作流的规划层。

### 5. Novel-to-Drama Script
### 小说转短剧脚本

Generate episode-level short-drama scripts from the adaptation plan. This is the script generation layer.  
根据改编计划生成单集短剧脚本。这是脚本生成层。

### 6. Rewriting
### 重写

Create and apply a project-scoped refresh bible, then rewrite script text consistently across a project.  
创建并应用项目级的刷新设定集，随后在整个项目中一致地重写剧本内容。

---

## Recommended workflows
## 推荐工作流

### Workflow A: standard adaptation pipeline
### 工作流 A：标准改编流水线

```text
raw novel -> Skill 4 -> Skill 5 -> Skill 6
原始小说 -> 技能 4 -> 技能 5 -> 技能 6
```

Meaning:  
流程说明：

- Skill 4 creates the adaptation blueprint  
  技能 4 创建改编蓝图
- Skill 5 generates episode scripts  
  技能 5 生成剧集脚本
- Skill 6 applies the project refresh canon and rewrite logic  
  技能 6 应用项目刷新规范和重写逻辑

---

## Practical guidance
## 实践指导

### Detail tradeoff in Skill 5
### 技能 5 的细节权衡

Smaller episode ranges produce richer script detail.  
较小的单次生成集数范围会产生更丰富的脚本细节。

Rule of thumb:  
经验法则：

- 1 episode = most detailed  
  1 集 = 最详细
- 2–5 episodes = good balance  
  2–5 集 = 良好的平衡
- 10 episodes = faster, lighter detail  
  10 集 = 速度更快，细节较少

---

## Notes
## 说明

For long-novel work, the most stable serious workflow is: plan first, generate scripts second, rewrite with a project-scoped refresh bible third.  
对于严肃的长篇小说任务，最稳健的工作流是：先规划，后生成脚本，最后使用项目级刷新设定集进行重写。
