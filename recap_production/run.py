"""Drama Prep Helper interactive runner.

Run:
    python run.py

Then follow the terminal prompts.
"""

from __future__ import annotations

from pathlib import Path
import sys

from engine.llm_client import LLMClientError, call_chat_completion, load_config_from_env, load_env_file
from engine.models import RunState, SessionContext
from engine.prompts import build_messages, distill_workflow_rules
from engine.router import detect_step
from engine.skill_loader import load_skill_definition, load_step_prompt
from engine.writer import create_output_directory, load_latest_state, save_state, write_model_output, write_prompt_dump


INTRO_TEXT = (
    "Drama Prep Helper\n"
    "This tool reads SKILL.md as workflow rules, reads your input .txt, "
    "detects the correct step, runs the LLM, and saves a .txt output."
)
STYLE_CHOICES = ("写实", "2D", "3D")


def main() -> int:
    """Run the interactive terminal application."""
    root_path = Path(__file__).resolve().parent
    configure_console_streams()
    load_env_file(root_path.parent / ".env")

    print(INTRO_TEXT)

    while True:
        try:
            should_continue = run_single_interaction(root_path)
        except KeyboardInterrupt:
            print("\nCancelled.")
            return 1

        if not should_continue:
            break

    return 0


def run_single_interaction(root_path: Path) -> bool:
    """Execute one run or resume cycle, then return whether to continue looping."""
    print_progress("reading skill")
    skill_definition = load_skill_definition(root_path)

    latest_state = load_latest_state(root_path)
    if latest_state and should_offer_resume(skill_definition, latest_state):
        prompt = "Resume the latest unfinished state? [y/N]: "
        if latest_state.status == "completed_step":
            prompt = "Resume from the latest saved step? [y/N]: "
        if ask_yes_no(prompt):
            execute_resume(root_path, skill_definition, latest_state)
            return next_action_loop(root_path)

    execute_new_run(root_path, skill_definition)
    return next_action_loop(root_path)


def execute_new_run(root_path: Path, skill_definition) -> None:
    """Start a fresh run from a user-provided text file."""
    print_progress("reading input")
    input_file_path = prompt_for_text_path()
    input_text = read_text_with_fallbacks(input_file_path)

    print_progress("detecting step")
    detected_step = detect_step(input_text, skill_definition)
    print(f"Detected step {detected_step.step_number}: {skill_definition.get_step(detected_step.step_number).title}")

    context = SessionContext(
        root_path=str(root_path),
        skill_path=skill_definition.skill_path,
        input_file_path=str(input_file_path),
        input_text=input_text,
        detected_step=detected_step,
    )
    complete_run(root_path, skill_definition, context)


def execute_resume(root_path: Path, skill_definition, latest_state: RunState) -> None:
    """Resume from the latest saved state."""
    resume_input_path = Path(latest_state.output_path or latest_state.input_file_path)
    if not resume_input_path.exists():
        raise RuntimeError(f"Resume file does not exist: {resume_input_path}")

    resumed_step_hint = latest_state.detected_step
    if latest_state.status == "completed_step" and latest_state.detected_step < max(skill_definition.steps):
        resumed_step_hint = latest_state.detected_step + 1

    print_progress("reading input")
    input_text = read_text_with_fallbacks(resume_input_path)

    print_progress("detecting step")
    detected_step = detect_step(input_text, skill_definition, resumed_step_hint=resumed_step_hint)
    print(f"Resuming from {resume_input_path}")
    print(f"Selected step {detected_step.step_number}: {skill_definition.get_step(detected_step.step_number).title}")

    context = SessionContext(
        root_path=str(root_path),
        skill_path=skill_definition.skill_path,
        input_file_path=str(resume_input_path),
        input_text=input_text,
        detected_step=detected_step,
        chosen_style=latest_state.chosen_style,
        resume_source=latest_state,
        episode_count=latest_state.episode_count,
    )
    complete_run(root_path, skill_definition, context)


def complete_run(root_path: Path, skill_definition, context: SessionContext) -> None:
    """Gather required inputs, call the model, and persist all outputs."""
    timestamp, output_directory = create_output_directory(root_path)
    state = RunState(
        timestamp=timestamp,
        skill_path=context.skill_path,
        input_file_path=context.input_file_path,
        detected_step=context.detected_step.step_number,
        chosen_style=context.chosen_style,
        episode_count=context.episode_count,
        output_path=None,
        status="awaiting_user_confirmation",
        output_directory=str(output_directory),
        notes=[context.detected_step.reason],
    )
    save_state(state, output_directory)

    gather_missing_inputs(skill_definition, context, state, output_directory)

    print_progress("loading prompt")
    step_prompt = load_step_prompt(skill_definition, context.detected_step.step_number)
    workflow_rules = distill_workflow_rules(skill_definition)
    messages = build_messages(workflow_rules, step_prompt, context)

    print_progress("calling model")
    try:
        config = load_config_from_env()
        result = call_chat_completion(config, messages)
    except LLMClientError as exc:
        state.status = "error"
        state.notes.append(str(exc))
        save_state(state, output_directory)
        raise RuntimeError(str(exc)) from exc

    print_progress("saving output")
    output_path = write_model_output(output_directory, context.detected_step.step_number, result.text)
    write_prompt_dump(output_directory, result.model, messages, result.raw_response)

    state.chosen_style = context.chosen_style
    state.episode_count = context.episode_count
    state.output_path = str(output_path)
    state.status = "completed_step"
    if context.episode_count is not None:
        state.notes.append(f"Episode count: {context.episode_count}")
    save_state(state, output_directory)

    print(f"Saved output to: {output_path}")


def gather_missing_inputs(skill_definition, context: SessionContext, state: RunState, output_directory: Path) -> None:
    """Prompt only when the current step requires more information."""
    if context.detected_step.step_number == 2 and not context.chosen_style:
        state.status = "awaiting_missing_input"
        state.notes.append("Waiting for style choice.")
        save_state(state, output_directory)
        context.chosen_style = prompt_for_style()
        state.chosen_style = context.chosen_style
        state.status = "awaiting_user_confirmation"
        save_state(state, output_directory)

    needs_episode_count = context.detected_step.needs_episode_count or (
        context.detected_step.step_number == 1
        and context.episode_count is None
        and context.resume_source is not None
        and context.resume_source.status == "awaiting_missing_input"
    )
    if context.detected_step.step_number == 1 and needs_episode_count:
        state.status = "awaiting_missing_input"
        state.notes.append("Waiting for episode count.")
        save_state(state, output_directory)
        context.episode_count = prompt_for_episode_count()
        state.episode_count = context.episode_count
        state.notes.append(f"Episode count chosen: {context.episode_count}")
        state.status = "awaiting_user_confirmation"
        save_state(state, output_directory)

    if context.detected_step.step_number not in skill_definition.steps:
        state.status = "error"
        state.notes.append("Selected step missing from SKILL.md.")
        save_state(state, output_directory)
        raise RuntimeError("Selected step is not defined by SKILL.md.")


def prompt_for_text_path() -> Path:
    """Prompt until the user provides an existing .txt file."""
    while True:
        raw_value = input("Enter the path to your .txt file: ").strip().strip('"')
        if not raw_value:
            print("A .txt file path is required.")
            continue
        candidate = Path(raw_value).expanduser()
        if not candidate.exists():
            print("File not found. Please try again.")
            continue
        if candidate.suffix.lower() != ".txt":
            print("Only .txt files are supported.")
            continue
        return candidate.resolve()


def read_text_with_fallbacks(file_path: Path) -> str:
    """Read text using UTF-8 first, then common fallbacks."""
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Could not decode file: {file_path}")


def prompt_for_style() -> str:
    """Prompt for one of the supported asset styles."""
    print("Choose an asset style:")
    for index, style in enumerate(STYLE_CHOICES, start=1):
        print(f"{index}. {style}")
    while True:
        raw_value = input("> ").strip()
        if raw_value in {"1", "2", "3"}:
            return STYLE_CHOICES[int(raw_value) - 1]
        if raw_value in STYLE_CHOICES:
            return raw_value
        print("Please choose 1, 2, 3, or type the style name.")


def prompt_for_episode_count() -> int:
    """Prompt for a reasonable positive episode count."""
    while True:
        raw_value = input("How many episodes should be planned? ").strip()
        try:
            episode_count = int(raw_value)
        except ValueError:
            print("Enter a whole number.")
            continue
        if episode_count <= 0:
            print("Episode count must be greater than zero.")
            continue
        if episode_count > 100:
            print("That is likely too many episodes. Please choose a smaller number.")
            continue
        return episode_count


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    """Prompt for a yes/no answer."""
    while True:
        raw_value = input(prompt).strip().lower()
        if not raw_value:
            return default
        if raw_value in {"y", "yes"}:
            return True
        if raw_value in {"n", "no"}:
            return False
        print("Please answer y or n.")


def next_action_loop(root_path: Path) -> bool:
    """Offer the end-of-run menu."""
    print()
    print("What would you like to do next?")
    print("1. Run another file")
    print("2. Resume latest state")
    print("3. Exit")

    while True:
        choice = input("> ").strip()
        if choice == "1":
            return True
        if choice == "2":
            latest_state = load_latest_state(root_path)
            if latest_state is None:
                print("No saved state was found. Starting a new run instead.")
                return True
            skill_definition = load_skill_definition(root_path)
            execute_resume(root_path, skill_definition, latest_state)
            return next_action_loop(root_path)
        if choice == "3":
            return False
        print("Choose 1, 2, or 3.")


def should_offer_resume(skill_definition, latest_state: RunState) -> bool:
    """Return True when the latest state can still help continue the workflow."""
    if latest_state.status != "completed_step":
        return True
    return latest_state.detected_step < max(skill_definition.steps)


def print_progress(label: str) -> None:
    """Print a concise progress update."""
    print(f"[...] {label}")


def configure_console_streams() -> None:
    """Prefer UTF-8 console output and avoid crashing on unsupported glyphs."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
