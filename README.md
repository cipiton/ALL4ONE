# ONE4ALL

A shared terminal-based LLM workflow runner for recap analysis, long-novel adaptation, episode script generation, rewriting, story creation, and large-text preprocessing.

---

## What this project is

ONE4ALL is a **skill-driven Python app** built around a shared runtime.

Instead of creating a separate app for each workflow, the project uses:

- a single entrypoint: `run.py`
- a shared execution engine in `engine/`
- a registry of skills in `skills/registry.yaml`
- one `SKILL.md` per skill for behavior, steps, prompts, and runtime rules

This makes it easier to add or evolve workflows without rebuilding the whole app.

---

## Main use cases

ONE4ALL is especially suited for:

- long Chinese novel adaptation
- short-drama planning
- short-drama episode script generation
- recap analysis and recap production
- project-scoped rewriting / refresh workflows
- large novel preprocessing and chunking
- original microseries story package generation

---

## Current skills

### 1. Recap Analysis
Analyze recap inputs and generate structured reports.

### 2. Recap Production
Run a resumable recap-production workflow.

### 3. Novel 2 Script
Run a broader multi-step novel-to-script production pipeline.

### 4. Novel Adaptation Plan
Turn long-form source material into a structured short-drama adaptation plan.

### 5. Novel-to-Drama Script
Generate short-drama episode scripts from the adaptation plan.

### 6. Rewriting
Create a refresh bible and rewrite script text with consistent refreshed characters, objects, and terms.

### 7. Story Creation
Generate an original microseries story package from a short brief.

### 8. Large Novel Processor
Split oversized novel `.txt` files into chapter/chunk outputs plus an index for downstream workflows.

---

## Installation

From the repo root:

```bash
python -m pip install -r requirements.txt
```

Recommended:

- Python 3.10+
- a valid API key / provider setup in `config.ini` or environment variables

---

## Run the app

```bash
python run.py
```

The runner will:

1. show the available skills
2. let you choose a skill
3. ask for the required input(s)
4. run the selected workflow
5. keep the session open so you can run another job

---

## Repository structure

```text
ONE4ALL/
├── run.py
├── config.ini
├── README.md
├── tasks.md
├── app/
├── engine/
├── outputs/
└── skills/
    ├── registry.yaml
    ├── SKILL_TEMPLATE.md
    ├── recap_analysis/
    ├── recap_production/
    ├── novel2script/
    ├── novel_adaptation_plan/
    ├── novel_to_drama_script/
    ├── rewriting/
    ├── story_creation/
    └── large_novel_processor/
```

---

## Core concepts

## Skills
Each workflow is defined as a skill. A skill typically includes:

- `SKILL.md`
- optional prompt/reference files
- optional deterministic helper scripts
- metadata for routing, steps, and runtime prompts

## Shared runtime
The shared runtime handles:

- menu display
- input routing
- folder/file handling
- step execution
- review loops
- model routing
- output creation
- oversized text handling

## Output roots
Outputs are usually written under:

```text
outputs/<skill>/<job_or_project>/
```

Some workflows also use:

```text
outputs/<skill>/<job>/intermediate/
outputs/<skill>/<job>/final/
```

---

## Large text support

LLM-backed `.txt` skills support shared large-text ingestion.

When a `.txt` input is too large for safe single-pass processing, the runtime can:

1. detect oversize input
2. switch into project ingestion mode
3. auto-split or consume a chunked project
4. build continuity state
5. synthesize a `master_outline.txt`
6. continue the skill from the consolidated result

Typical intermediate artifacts:

- `project_state.json`
- `continuity_log.json`
- `chunk_summaries.json`
- `master_outline.txt`
- `ingestion_report.txt`

This lets long novels be processed as one logical project instead of isolated chunk runs.

---

## Model routing

The runtime supports model routing by phase.

Typical routing pattern:

- **fast model** for mechanical or intermediate work
- **strong model** for final deliverables and polish

Routing can be defined at:

- global config level
- route level
- skill level
- step level
- project-ingestion phase level

Example phases:

- chunk ingestion
- master outline synthesis
- step execution
- final deliverable
- QA / final polish

---

## Skill details

## 1. Recap Analysis

**Purpose**

Analyze one or more novel `.txt` files and generate structured recap-fit analysis.

**Typical output**

- title
- premise
- theme
- main plot
- character summary
- adaptation suitability
- episode recommendation
- audience fit
- risks
- conclusion

**Best input**

- one novel `.txt`
- multiple `.txt` files for separate evaluation

**Execution style**

- structured report

**Use this when**

You want to evaluate whether a novel or source text is suitable for recap / explanation-style production.

---

## 2. Recap Production

**Purpose**

Generate recap-production materials in a step-based workflow.

**Typical steps**

1. output recap script
2. extract assets
3. output image-generation config

**Typical output**

- recap script
- assets / characters / props list
- image-generation configuration

**Best input**

- synopsis
- recap-ready text
- outline
- story package
- script-like source

**Execution style**

- step-based workflow with review

**Use this when**

You already know the source is suitable and want recap-production deliverables.

---

## 3. Novel 2 Script

**Purpose**

Run a multi-step end-to-end short-drama creation flow from source text or premise to downstream production materials.

**Typical steps**

1. story polish
2. episode plot
3. highlights
4. episode scripts
5. analysis
6. assets
7. image config

**Best input**

- premise
- synopsis
- source text
- early outline
- draft story package

**Execution style**

- multi-step workflow

**Use this when**

You want a broader full-pipeline workflow instead of the specialized Skill 4 → 5 → 6 path.

---

## 4. Novel Adaptation Plan

**Purpose**

Convert long-form source material into a structured short-drama adaptation plan.

This is the **planning layer** of the main adaptation workflow.

**What it does**

- reads source novel or consolidated long-text input
- extracts key set pieces
- grades and prioritizes them
- builds phase pacing
- maps content to episode structure
- produces a final adaptation-plan handoff
- includes character-bible style guidance for downstream scripting

**Typical outputs**

- adaptation brief
- set-piece candidates
- graded set pieces
- phase pacing plan
- episode binding plan
- final adaptation plan

**Important final handoff**

- `06_final_adaptation_plan.txt`

**Best input**

- raw novel `.txt`
- project-ingested long novel output
- consolidated story source

**Execution style**

- multi-step workflow
- supports project-ingested mode

**Use this when**

You want to turn a long novel into a usable short-drama blueprint.

**Recommended handoff**

```text
raw novel -> Skill 4 -> 06_final_adaptation_plan.txt
```

---

## 5. Novel-to-Drama Script

**Purpose**

Generate episode-level short-drama scripts from the adaptation plan.

This is the **script generation layer**.

**What it does**

- reads the final adaptation plan
- infers total episode count
- prompts for episode selection
- generates scripts in batches
- supports selective generation or regeneration

**Supported selections**

- blank = all
- `all`
- `1-10`
- `11-20`
- `60`
- similar valid ranges

**Batching**

Skill 5 supports configurable episodes-per-file output.

Typical behavior:

- single episode = highest detail
- small range = more detailed
- larger range = faster coverage, less detail

**Best input**

- `06_final_adaptation_plan.txt` from Skill 4

**Execution style**

- range-driven script generation workflow

**Use this when**

You want to turn the adaptation plan into actual episode script material.

**Recommended handoff**

```text
Skill 4 final adaptation plan -> Skill 5
```

---

## 6. Rewriting

**Purpose**

Create and apply a project-scoped refresh bible, then rewrite script text consistently.

This skill is best understood as a **refresh / rewrite / canon-consistency layer**, not just a cosmetic polish pass.

**What it can do**

- create a refresh bible from the adaptation plan
- enrich that bible with script evidence
- rewrite one script file or a whole script folder using that bible
- keep refreshed character, object, organization, and term usage consistent across a project

**Core workflow modes**

1. Create refresh bible
2. Rewrite using existing refresh bible
3. Create bible and rewrite

**Refresh bible**

The bible is project-scoped and can include:

- refreshed character names
- aliases / titles
- object / artifact terms
- faction / organization terms
- location terms
- naming rules
- consistency notes
- avoid terms

**Shared bible storage**

```text
outputs/rewriting/bibles/<project_name>/
  refresh_bible.json
  refresh_bible.txt
```

**Folder input**

For script folders, Skill 6 supports:

- shared project mode
- individual file mode

Shared mode is recommended for consistency.

**Best input patterns**

### Build bible first
```text
Skill 4 final adaptation plan -> Skill 6 (create refresh bible)
```

### Rewrite with bible
```text
Skill 5 script output(s) -> Skill 6 (rewrite using existing bible)
```

### Full consistency workflow
```text
Skill 4 final adaptation plan -> Skill 6 (build bible)
Skill 5 script batches -> Skill 6 (rewrite using bible)
```

**Use this when**

You want consistent refreshed naming and rewrite logic across a whole project.

---

## 7. Story Creation

**Purpose**

Generate an original microseries story package from a short brief.

**Typical output**

- title
- genre
- setting
- hook
- main characters
- story line
- core conflict
- reversals
- climax
- ending direction
- episode-direction overview
- pacing notes

**Best input**

- short idea
- genre direction
- tone guidance
- premise

**Execution style**

- generation workflow

**Use this when**

You want an original project starting point instead of adapting an existing novel.

---

## 8. Large Novel Processor

**Purpose**

Split oversized novel `.txt` files into chapters or chunk groups without using the LLM.

This is the **preprocessing utility**.

**What it does**

- reads a large `.txt`
- detects chapter structure
- splits into chapter files
- optionally groups into chunk files
- writes an `index.txt`

**Typical output**

```text
outputs/large_novel_processor/<project>__<timestamp>/
  index.txt
  chapters/
  chunks/
```

**Best input**

- very large novel `.txt`

**Execution style**

- deterministic utility script

**Use this when**

You want manual chunk control before feeding text into downstream skills.

---

## Recommended workflows

## Workflow A: standard adaptation pipeline

```text
raw novel -> Skill 4 -> Skill 5 -> Skill 6
```

Meaning:

1. Skill 4 creates the adaptation blueprint
2. Skill 5 generates episode scripts
3. Skill 6 applies the project refresh canon and rewrite logic

---

## Workflow B: consistency-first pipeline

```text
raw novel -> Skill 4
Skill 4 final adaptation plan -> Skill 6 (build refresh bible)
Skill 4 final adaptation plan -> Skill 5
Skill 5 script batches -> Skill 6 (rewrite using bible)
```

This is the best workflow when naming consistency matters across many script files.

---

## Workflow C: preprocess first

```text
raw large novel -> Skill 8
chunked output -> Skill 4 or Skill 5
```

Use this when you want explicit chunk control instead of relying entirely on automatic project ingestion.

---

## Workflow D: recap workflow

```text
novel txt -> Skill 1
recap-ready source -> Skill 2
```

---

## Practical guidance

## Skill 4 vs Skill 5 vs Skill 6

### Skill 4
Use for:
- adaptation blueprint
- pacing
- set pieces
- episode structure
- character guidance

### Skill 5
Use for:
- actual episode scripts
- episode-range generation
- batch output
- selected episode regeneration

### Skill 6
Use for:
- refresh bible creation
- project-scoped rename consistency
- rewrite using locked canon
- consistent character/object/world-term refresh

---

## Detail tradeoff in Skill 5

Smaller episode ranges produce richer script detail.

Rule of thumb:

- **1 episode** = most detailed
- **2–5 episodes** = good balance
- **10 episodes** = faster, lighter detail

This is normal and expected.

---

## Why Skill 6 can feel slow

Skill 6 can still be slow when:

- rewriting a lot of script text
- handling many `.txt` files
- reading and normalizing large inputs
- running shared project mode across a full folder

The refresh bible improves consistency and repeatability, but it does not remove the cost of processing large script volumes.

---

## Configuration

Main runtime settings live in `config.ini`.

Typical areas include:

- LLM provider/model
- model aliases
- route-based model routing
- generation defaults
- debug/review behavior

Example categories:

- `[llm]`
- `[model_aliases]`
- `[model_routing]`
- `[generation]`
- `[debug]`

---

## Outputs

Most outputs live under:

```text
outputs/<skill>/<job_or_project>/
```

Examples:

### Project-ingested run
```text
outputs/<skill>/<project>/
  intermediate/
  final/
```

### Rewriting bibles
```text
outputs/rewriting/bibles/<project_name>/
  refresh_bible.json
  refresh_bible.txt
```

---

## Adding a new skill

Typical process:

1. create a new folder under `skills/`
2. add `SKILL.md`
3. add prompt/reference files if needed
4. register it in `skills/registry.yaml`
5. run `python run.py`

You can use `skills/SKILL_TEMPLATE.md` as a starting point.

---

## Notes

- Keep secrets out of the repo where possible.
- For future `.exe` packaging, keep `skills/`, `config.ini`, and outputs path-safe and externally accessible.
- For long-novel work, the most stable serious workflow is:
  - plan first
  - generate scripts second
  - rewrite with a project-scoped refresh bible third
