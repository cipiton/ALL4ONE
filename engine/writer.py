from __future__ import annotations  
  
import json  
import re  
from datetime import datetime  
from pathlib import Path  
from typing import Any  
  
from .models import InputDocument, SkillDefinition  
  
  
def create_session_directory(  
    outputs_root: Path,  
    skill_name: str,  
    input_root_path: Path | None = None,  
) -> tuple[str, Path]:  
    skill_root = outputs_root / skill_name  
    skill_root.mkdir(parents=True, exist_ok=True)  
  
    base_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')  
    session_prefix = safe_stem(_derive_session_label(input_root_path))  
    attempt = 0  
    while True:  
        timestamp = base_timestamp if attempt == 0 else f'{base_timestamp}_{attempt:02d}'  
        session_name = f'{session_prefix}__{timestamp}' if session_prefix else timestamp  
        session_dir = skill_root / session_name  
        try:  
            session_dir.mkdir(parents=True, exist_ok=False)  
            return timestamp, session_dir  
        except FileExistsError:  
            attempt += 1  
  
  
def _derive_session_label(input_root_path: Path | None) -> str:  
    if input_root_path is None:  
        return 'run'  
    candidate = input_root_path.name if input_root_path.suffix == '' else input_root_path.stem  
    return candidate or 'run'  
  
  
def create_document_directory(session_dir: Path, document: InputDocument) -> Path:  
    directory = session_dir / 'documents' / f'{document.index:03d}_{safe_stem(document.path.stem)}'  
    directory.mkdir(parents=True, exist_ok=True)  
    return directory  
  
  
def create_internal_directory(base_dir: Path) -> Path:  
    internal_dir = base_dir / '.internal'  
    internal_dir.mkdir(parents=True, exist_ok=True)  
    return internal_dir  
  
  
def render_output_filename(  
    template: str,  
    document: InputDocument,  
    *,  
    step_number: int | None = None,  
) -> str:  
    rendered = template.format(  
        input_name=document.path.name,  
        input_stem=safe_stem(document.path.stem),  
        step_number=step_number if step_number is not None else '',  
    )  
    return rendered or f'{safe_stem(document.path.stem)}.txt' 
  
  
def write_text_file(output_dir: Path, filename: str, content: str) -> Path:  
    output_dir.mkdir(parents=True, exist_ok=True)  
    target = output_dir / filename  
    target.write_text(content, encoding='utf-8')  
    return target  
  
  
def write_json_file(output_dir: Path, filename: str, payload: Any) -> Path:  
    output_dir.mkdir(parents=True, exist_ok=True)  
    target = output_dir / filename  
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')  
    return target  
  
  
def render_section_report(  
    skill: SkillDefinition,  
    document: InputDocument,  
    sections: dict[str, Any],  
    *,  
    model_name: str,  
) -> str:  
    lines = [  
        f'Skill: {skill.display_name}',  
        f'Input file: {document.path.name}',  
        f'Model: {model_name}',  
        '',  
    ]  
    ordered_sections = skill.output_config.sections or list(sections)  
    seen: set[str] = set()  
  
    for section_name in ordered_sections:  
        seen.add(section_name)  
        lines.append(section_name)  
        lines.append(stringify(sections.get(section_name)))  
        lines.append('')  
  
    for section_name, value in sections.items():  
        if section_name in seen:  
            continue  
        lines.append(section_name)  
        lines.append(stringify(value))  
        lines.append('')  
  
    return '\n'.join(lines).rstrip() + '\n'  
  
  
def safe_stem(value: str) -> str:  
    slug = re.sub(r'[^0-9A-Za-z\u4e00-\u9fff._-]+', '_', value.strip())  
    slug = slug.strip('._') or 'document'  
    return slug[:80]  
  
  
def stringify(value: Any) -> str:  
    if value is None:  
        return '未明确提及'  
    if isinstance(value, str):  
        stripped = value.strip()  
        return stripped or '未明确提及'  
    if isinstance(value, list):  
        parts = [stringify(item) for item in value]  
        return ';'.join(part for part in parts if part and part != '未明确提及') or '未明确提及'  
    return str(value).strip() or '未明确提及'  

