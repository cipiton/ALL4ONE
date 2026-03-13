from __future__ import annotations

import argparse
import sys
from pathlib import Path

from engine.analyzers import NovelEvaluationAnalyzer
from engine.formatter import finalize_report
from engine.llm_client import LLMClient, LLMConfigurationError, LLMRequestError
from engine.planner import build_execution_plan
from engine.router import InputRoutingError, read_txt_document
from engine.skill_loader import SkillLoadError, discover_skill_dir, load_reference_texts, load_skill
from engine.writer import write_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the skill-driven novel evaluation workflow.")
    parser.add_argument("input_path", nargs="?", help="Path to the source .txt file.")
    parser.add_argument(
        "--skill-dir",
        dest="skill_dir",
        help="Optional path to the extracted skill directory containing SKILL.md.",
    )
    args = parser.parse_args()
    app_root = Path(__file__).resolve().parent

    try:
        next_input = args.input_path
        while True:
            try:
                input_path = resolve_input_path(next_input)
                if input_path is None:
                    print("Exiting.")
                    return 0

                print("[1/6] Validating input...")
                document = read_txt_document(input_path)

                print("[2/6] Loading skill...")
                skill_dir = (
                    Path(args.skill_dir).expanduser().resolve()
                    if args.skill_dir
                    else discover_skill_dir(app_root)
                )
                skill_config = load_skill(skill_dir)

                print("[3/6] Building execution plan...")
                plan = build_execution_plan(skill_config, document)

                print("[4/6] Loading selected references...")
                reference_texts = load_reference_texts(plan.references_to_load)

                print("[5/6] Running staged analysis...")
                analyzer = NovelEvaluationAnalyzer(LLMClient())
                analysis_result = analyzer.run(
                    plan=plan,
                    skill_config=skill_config,
                    document=document,
                    reference_texts=reference_texts,
                )

                print("[6/6] Formatting and writing report...")
                finalized = finalize_report(
                    analysis_result,
                    skill_config=skill_config,
                    document=document,
                )
                output_path = write_report(
                    app_root / "outputs",
                    document.path,
                    finalized.final_report_text,
                )
                print(f"Success: {output_path}")
            except (InputRoutingError, SkillLoadError, LLMConfigurationError, LLMRequestError) as exc:
                print(f"Error: {exc}", file=sys.stderr)

            print()
            next_input = None
    except KeyboardInterrupt:
        print("\nExiting.", file=sys.stderr)
        return 0


def resolve_input_path(raw_path: str | None) -> Path | None:
    if raw_path is None:
        raw_path = input("Enter path to the .txt novel file (blank to exit): ").strip()

    if not raw_path:
        return None

    if raw_path.lower() in {"q", "quit", "exit"}:
        return None

    input_path = Path(raw_path).expanduser().resolve()
    if not input_path.exists():
        raise InputRoutingError(f"输入文件不存在: {input_path}")
    if input_path.suffix.lower() != ".txt":
        raise InputRoutingError(f"仅支持 .txt 输入: {input_path.name}")
    return input_path


if __name__ == "__main__":
    sys.exit(main())
