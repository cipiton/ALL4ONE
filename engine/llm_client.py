from __future__ import annotations  
  
import json  
import os  
import time  
from pathlib import Path  
from urllib import error, request  
  
from .config_loader import get_config_value, load_repo_config  
from .models import LLMConfig, LLMResponse, PromptMessage  
  
  
class LLMClientError(RuntimeError):  
    pass
  
  
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
  
  
def load_config_from_env(repo_root: Path) -> LLMConfig:  
    selection = _resolve_llm_selection(repo_root)  
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
  
  
def _resolve_llm_selection(repo_root: Path) -> dict[str, str]:  
    load_env_file(repo_root / '.env')  
    parser = load_repo_config(repo_root)  
  
    config_provider = get_config_value(parser, 'llm', 'provider', '')  
    provider = os.getenv('LLM_PROVIDER', '').strip().lower() or config_provider.lower()  
  
    openrouter_key = os.getenv('OPENROUTER_API_KEY', '').strip()  
    openai_key = os.getenv('OPENAI_API_KEY', '').strip()  
    if provider not in {'openai', 'openrouter'}:  
        provider = 'openrouter' if openrouter_key else 'openai'  
  
    model = _resolve_model_name(parser, provider)  
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
    }  
  
  
def _resolve_model_name(parser, provider: str) -> str:  
    config_model = get_config_value(parser, 'llm', 'model', '')  
    if provider == 'openrouter':  
        return (  
            os.getenv('OPENROUTER_MODEL', '').strip()  
            or os.getenv('OPENAI_MODEL', '').strip()  
            or config_model  
        )  
    return os.getenv('OPENAI_MODEL', '').strip() or config_model 
  
  
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
