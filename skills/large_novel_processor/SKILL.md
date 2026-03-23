---
name: large_novel_processor
display_name: Large Novel Processor
description: Prepare oversized novel .txt files for downstream skills by splitting them into chapter files or grouped chunk files plus an index.
supports_resume: false
input_extensions:
  - .txt
folder_mode: non_recursive

steps:
  - number: 1
    title: Prepare Large Novel Input
    description: Split a large novel by chapter headings and optionally group chapters into chunk files.
    write_to: prepared_index
    default: true

runtime_inputs:
  - name: split_mode
    prompt: Choose split mode
    type: choice
    choices:
      - chapter
      - chunk
    default: chapter
  - name: chunk_size
    prompt: Chapters per chunk
    type: int
    default: 20
    min: 1
    max: 200
    help_text: Used only when split mode is chunk.

execution:
  strategy: utility_script
  utility_script:
    path: scripts/process_large_novel.py
    entrypoint: run

output:
  mode: text
  filename_template: index.txt
  include_prompt_dump: false
---

# Large Novel Processor

Prepare very large `.txt` novels for downstream skills before they hit model context limits.

## Purpose

This skill is a user-facing preprocessing step. It does not call the LLM and it does not generate outlines, scripts, assets, or image configs.

It only:

1. reads a large novel `.txt`
2. detects chapter headings
3. splits the source into chapter files
4. optionally groups those chapters into chunk files
5. writes an `index.txt`

Use it before downstream skills such as:

- `Script Revision`
- `Short Drama Adaption`
- `Novel To Drama Script`

## Input

Provide one `.txt` novel file with visible chapter headings.

The splitter is designed primarily for Chinese web-novel style headings, for example:

- `第1章`
- `第一章 重逢`
- `第12回`
- `序章`
- `番外`

It also tolerates simple English-style headings such as `Chapter 1`.

## Runtime Options

- `split_mode = chapter`
  Write one `.txt` file per detected chapter under `chapters/`.
- `split_mode = chunk`
  Group detected chapters into larger `.txt` files under `chunks/`.
- `chunk_size`
  Number of chapters per chunk when `split_mode = chunk`. Default: `20`.

## Output

Outputs are written under the normal shared run folder:

`outputs/large_novel_processor/<input_name>__<timestamp>/`

Artifacts:

- `index.txt`
- `chapters/*.txt` when using chapter mode
- `chunks/*.txt` when using chunk mode

`index.txt` is the primary output and records the detected chapters, generated files, and chunk grouping.

## Scope Guardrails

This skill must not:

- summarize the novel
- adapt the novel
- rewrite the novel
- generate scripts
- extract production assets
- call the LLM

It is only a reusable preparation step for oversized source text.
