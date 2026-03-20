# Story Creation

Single-step shared-engine skill for generating an original vertical microdrama step-1 storyline package from a short `.txt` brief.

## What It Does

- takes a short creative brief as input
- generates an original Chinese microseries storyline package
- outputs only step 1 story development content
- does not generate episode scripts, assets, or image config

## Expected Input Style

Provide a short `.txt` brief such as:

```text
modern revenge romance, female lead comeback, corporate setting, 60 episodes, high-emotion melodrama
```

You can also include short notes like:

- genre
- trope
- setting
- target episode count
- tone
- emotional direction

## Output

The skill writes one primary file:

- `01_storyline_package.txt`

The output is a structured Chinese package with sections such as:

- 标题
- 类型
- 设定背景
- 核心钩子
- 主要人物
- 故事主线
- 核心矛盾
- 关键反转
- 高潮
- 结局方向
- 分集方向概述
- 前10集节奏
- 中段节奏
- 后段节奏
- 风格说明

## Run

From the repo root:

```bash
python run.py
```

Then choose `Story Creation` and point it at a short `.txt` brief file.
