from __future__ import annotations  
  
import json  
import os  
import time  
from pathlib import Path  
from urllib import error, request  
  
from .config_loader import get_config_value, load_repo_config  
from .models import LLMConfig, LLMResponse, PromptMessage, SkillDefinition, SkillStep  
  
  
class LLMClientError(RuntimeError):  
    pass


ROUTE_LABELS = {
    "default": "global default",
    "step_execution": "step execution",
    "final_deliverable": "final deliverable",
    "qa_final_polish": "QA/final polish",
    "project_chunk_ingestion": "project chunk ingestion",
    "project_master_outline": "project master outline synthesis",
}


_CONTEXT_LIMIT_PATTERNS = (
    "maximum context length",
    "requested about",
    "too many tokens",
    "input too large",
    "context window",
    "context length",
    "reduce the length",
    "please reduce",
    "prompt is too long",
    "token limit",
)


def is_context_limit_error_message(message: str) -> bool:
    lowered = message.casefold()
    return any(pattern in lowered for pattern in _CONTEXT_LIMIT_PATTERNS)


def format_runtime_error_message(error: BaseException, *, troubleshooting_mode: bool = False) -> str:
    raw_message = str(error).strip() or error.__class__.__name__
    if not is_context_limit_error_message(raw_message):
        return raw_message

    lines = [
        "The input .txt file is too large for the current model's context window.",
        "Suggestion: use the 'Large Novel Processor' skill first to split the novel into chapters or chunk files, then rerun the downstream skill.",
    ]
    if troubleshooting_mode:
        lines.extend(
            [
                "",
                "Raw provider error:",
                raw_message,
            ]
        )
    return "\n".join(lines)
  
  
def load_env_file(env_path: Path) -> None:  
    if not env_path.exists():  
        return  
  
    quote = chr(34)  
    single = chr(39)  
    for raw_line in env_path.read_text(encoding='utf-8').splitlines():  
        line = raw_line.strip()  
        if not line or line.startswith('#') or '=' not in line:  
            continue  
        key, value = line.split('=', 1)  
        cleaned = value.strip().strip(quote).strip(single)  
        os.environ.setdefault(key.strip(), cleaned)  
  
  
def describe_active_model(repo_root: Path) -> str:  
    selection = _resolve_llm_selection(repo_root)  
    return f"Model: {selection['provider']} / {selection['model']}"


def describe_model_route(
    repo_root: Path,
    *,
    skill: SkillDefinition | None = None,
    step: SkillStep | None = None,
    route_role: str | None = None,
    model_override: str | None = None,
) -> str:
    selection = _resolve_llm_selection(
        repo_root,
        skill=skill,
        step=step,
        route_role=route_role,
        model_override=model_override,
    )
    label = ROUTE_LABELS.get(selection["route_role"], selection["route_role"])
    source = selection["selection_source"]
    return f"{label}: {selection['provider']} / {selection['model']} ({source})"
  
  
def load_config_from_env(
    repo_root: Path,
    *,
    skill: SkillDefinition | None = None,
    step: SkillStep | None = None,
    route_role: str | None = None,
    model_override: str | None = None,
) -> LLMConfig:
    selection = _resolve_llm_selection(
        repo_root,
        skill=skill,
        step=step,
        route_role=route_role,
        model_override=model_override,
    )
    provider = selection['provider']  
    timeout = float(selection['timeout'])  
    max_retries = int(selection['max_retries'])  
  
    openrouter_key = os.getenv('OPENROUTER_API_KEY', '').strip()  
    openai_key = os.getenv('OPENAI_API_KEY', '').strip()  
  
    if provider == 'openrouter':  
        api_key = openrouter_key or openai_key  
        if not api_key:  
            raise LLMClientError('Missing OPENROUTER_API_KEY.')  
        headers: dict[str, str] = {}  
        referer = os.getenv('OPENROUTER_HTTP_REFERER', '').strip()  
        title = os.getenv('OPENROUTER_APP_TITLE', '').strip()  
        if referer:  
            headers['HTTP-Referer'] = referer  
        if title:  
            headers['X-Title'] = title  
        return LLMConfig(  
            provider=provider,  
            api_key=api_key,  
            model=selection['model'],  
            base_url=selection['base_url'],  
            timeout=timeout,  
            max_retries=max_retries,  
            headers=headers,  
        ) 
  
    if not openai_key:  
        raise LLMClientError('Missing OPENAI_API_KEY.')  
    return LLMConfig(  
        provider=provider,  
        api_key=openai_key,  
        model=selection['model'],  
        base_url=selection['base_url'],  
        timeout=timeout,  
        max_retries=max_retries,  
        headers={},  
    )  
  
  
def _resolve_llm_selection(
    repo_root: Path,
    *,
    skill: SkillDefinition | None = None,
    step: SkillStep | None = None,
    route_role: str | None = None,
    model_override: str | None = None,
) -> dict[str, str]:
    load_env_file(repo_root / '.env')  
    parser = load_repo_config(repo_root)  
  
    config_provider = get_config_value(parser, 'llm', 'provider', '')  
    provider = os.getenv('LLM_PROVIDER', '').strip().lower() or config_provider.lower()  
  
    openrouter_key = os.getenv('OPENROUTER_API_KEY', '').strip()  
    openai_key = os.getenv('OPENAI_API_KEY', '').strip()  
    if provider not in {'openai', 'openrouter'}:  
        provider = 'openrouter' if openrouter_key else 'openai'  
  
    resolved_route_role = route_role or _infer_route_role(skill, step)
    model, selection_source = _resolve_model_name(
        parser,
        provider,
        skill=skill,
        step=step,
        route_role=resolved_route_role,
        model_override=model_override,
    )
    base_url = _resolve_base_url(parser, provider)  
    timeout = os.getenv('OPENAI_TIMEOUT', '').strip() or get_config_value(parser, 'llm', 'timeout', '90')  
    max_retries = os.getenv('OPENAI_MAX_RETRIES', '').strip() or get_config_value(parser, 'llm', 'max_retries', '3')  
  
    if provider == 'openrouter' and not model:  
        raise LLMClientError('Missing model for OPENROUTER.')  
    if provider == 'openai' and not model:  
        model = 'gpt-4.1-mini'  
  
    return {  
        'provider': provider,  
        'model': model,  
        'base_url': base_url,  
        'timeout': timeout,  
        'max_retries': max_retries,  
        'route_role': resolved_route_role,
        'selection_source': selection_source,
    }  
  
  
def _resolve_model_name(
    parser,
    provider: str,
    *,
    skill: SkillDefinition | None = None,
    step: SkillStep | None = None,
    route_role: str | None = None,
    model_override: str | None = None,
) -> tuple[str, str]:
    config_model = get_config_value(parser, 'llm', 'model', '')  
    env_model = (
        os.getenv('OPENROUTER_MODEL', '').strip()
        or os.getenv('OPENAI_MODEL', '').strip()
        if provider == 'openrouter'
        else os.getenv('OPENAI_MODEL', '').strip()
    )
    default_model = env_model or config_model

    resolved_override = _resolve_model_alias(parser, model_override)
    if resolved_override:
        return resolved_override, 'step override'

    skill_route_value = _resolve_skill_route_model(skill, route_role)
    resolved_skill_route = _resolve_model_alias(parser, skill_route_value)
    if resolved_skill_route:
        return resolved_skill_route, f"skill route '{route_role}'"

    config_route_value = get_config_value(parser, 'model_routing', f'{route_role}_model', '')
    resolved_config_route = _resolve_model_alias(parser, config_route_value)
    if resolved_config_route:
        return resolved_config_route, f"config route '{route_role}'"

    skill_default = _resolve_model_alias(parser, skill.model_routing.default_model if skill else None)
    if skill_default:
        return skill_default, "skill default"

    if provider == 'openrouter':  
        return default_model, ('env' if env_model else 'global default')
    return default_model, ('env' if env_model else 'global default')


def _resolve_model_alias(parser, value: str | None) -> str:
    candidate = (value or '').strip()
    if not candidate:
        return ''
    alias_value = get_config_value(parser, 'model_aliases', candidate, '').strip()
    return alias_value or candidate


def _resolve_skill_route_model(skill: SkillDefinition | None, route_role: str | None) -> str | None:
    if skill is None or route_role is None:
        return None
    routing = skill.model_routing
    route_map = {
        'step_execution': routing.step_execution_model,
        'final_deliverable': routing.final_deliverable_model,
        'qa_final_polish': routing.qa_final_polish_model,
        'project_chunk_ingestion': routing.project_chunk_ingestion_model,
        'project_master_outline': routing.project_master_outline_model,
    }
    return route_map.get(route_role)


def _infer_route_role(skill: SkillDefinition | None, step: SkillStep | None) -> str:
    if step is not None:
        if step.model_role:
            return step.model_role
        title = f"{step.title} {step.step_id}".casefold()
        if any(token in title for token in ('qa', '质检', 'polish', 'final check', '统一')):
            return 'qa_final_polish'
        if skill is not None and step.number == skill.final_step_number:
            return 'final_deliverable'
        return 'step_execution'
    if skill is None:
        return 'default'
    return 'step_execution'
  
  
def _resolve_base_url(parser, provider: str) -> str:  
    config_base_url = get_config_value(parser, 'llm', 'base_url', '')  
    if provider == 'openrouter':  
        return (  
            os.getenv('OPENROUTER_BASE_URL', '').strip()  
            or os.getenv('OPENAI_BASE_URL', '').strip()  
            or config_base_url  
            or 'https://openrouter.ai/api/v1'  
        )  
    return os.getenv('OPENAI_BASE_URL', '').strip() or config_base_url or 'https://api.openai.com/v1'  
  
  
def call_chat_completion(  
    config: LLMConfig,  
    messages: list[PromptMessage],  
    *,  
    json_mode: bool = False,  
    temperature: float = 0.2,  
) -> LLMResponse:  
    endpoint = f"{config.base_url.rstrip('/')}/chat/completions"
    payload: dict[str, object] = {  
        'model': config.model,  
        'messages': [message.to_dict() for message in messages],  
        'temperature': temperature,  
    }  
    if json_mode:  
        payload['response_format'] = {'type': 'json_object'}  
  
    headers = {  
        'Authorization': f'Bearer {config.api_key}',  
        'Content-Type': 'application/json',  
        **config.headers,  
    }  
  
    last_error: Exception | None = None  
    for attempt in range(1, config.max_retries + 1):  
        http_request = request.Request(  
            endpoint,  
            data=json.dumps(payload).encode('utf-8'),  
            headers=headers,  
            method='POST',  
        )  
        try:  
            with request.urlopen(http_request, timeout=config.timeout) as response:  
                response_text = response.read().decode('utf-8')  
            response_json = json.loads(response_text)  
            output_text = _extract_output_text(response_json)  
            if not output_text.strip():  
                raise LLMClientError('The model returned an empty response.')  
            return LLMResponse(  
                text=output_text,  
                model=str(response_json.get('model', config.model)),  
                raw_response=response_json,  
            ) 
        except error.HTTPError as exc:  
            body = exc.read().decode('utf-8', errors='replace')  
            last_error = LLMClientError(f'Provider returned HTTP {exc.code}: {body}')  
        except error.URLError as exc:  
            last_error = LLMClientError(f'Could not reach provider: {exc.reason}')  
        except json.JSONDecodeError:  
            last_error = LLMClientError('Provider returned invalid JSON.')  
        except Exception as exc:  # noqa: BLE001  
            last_error = exc  
  
        if attempt < config.max_retries:  
            time.sleep(min(2 ** attempt, 8))  
  
    raise LLMClientError(str(last_error)) from last_error  
  
  
def parse_json_response(response: LLMResponse) -> dict[str, object]:  
    cleaned = response.text.strip()  
    if cleaned.startswith('```'):  
        cleaned = cleaned.strip('`')  
        if '\n' in cleaned:  
            cleaned = cleaned.split('\n', 1)[1]  
        if cleaned.endswith('```'):  
            cleaned = cleaned[:-3]  
    try:  
        parsed = json.loads(cleaned)  
    except json.JSONDecodeError as exc:  
        raise LLMClientError(f'Model returned invalid JSON: {response.text}') from exc  
    if not isinstance(parsed, dict):  
        raise LLMClientError('Model JSON response was not an object.')  
    return parsed  
  
  
def _extract_output_text(response_json: dict[str, object]) -> str:  
    choices = response_json.get('choices')  
    if not isinstance(choices, list) or not choices:  
        return ''  
  
    first_choice = choices[0]  
    if not isinstance(first_choice, dict):  
        return ''  
    message = first_choice.get('message', {})  
    if not isinstance(message, dict):  
        return ''  
    content = message.get('content', '')  
    if isinstance(content, str):  
        return content  
    if isinstance(content, list):  
        parts: list[str] = []  
        for item in content:  
            if isinstance(item, dict) and item.get('type') == 'text':  
                text = item.get('text')  
                if isinstance(text, str):  
                    parts.append(text)  
        return '\n'.join(parts)  
    return ''  
