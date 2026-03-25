from __future__ import annotations  
  
from dataclasses import dataclass  
from pathlib import Path  
  
from .config_loader import get_config_bool, get_config_value, load_repo_config  
  
  
@dataclass(slots=True)  
class RuntimeConfig:  
    write_state_json: bool = False  
    write_prompt_dump: bool = False  
    write_debug_log: bool = False  
    troubleshooting_mode: bool = False  
    auto_accept_review_steps: bool = False  
    novel_to_drama_script_default_episodes_per_file: int = 10
    novel_to_drama_script_max_episodes_per_file: int = 20
  
    @property  
    def should_write_visible_state(self) -> bool:  
        return self.troubleshooting_mode or self.write_state_json  
  
    @property  
    def should_write_prompt_dump(self) -> bool:  
        return self.troubleshooting_mode or self.write_prompt_dump  
  
    @property  
    def should_write_debug_log(self) -> bool:  
        return self.troubleshooting_mode or self.write_debug_log  
  
  
def load_runtime_config(repo_root: Path) -> RuntimeConfig:  
    parser = load_repo_config(repo_root)  
    return RuntimeConfig(  
        write_state_json=get_config_bool(parser, 'outputs', 'write_state_json', False),  
        write_prompt_dump=get_config_bool(parser, 'outputs', 'write_prompt_dump', False),  
        write_debug_log=get_config_bool(parser, 'outputs', 'write_debug_log', False),  
        troubleshooting_mode=get_config_bool(parser, 'debug', 'troubleshooting_mode', False),  
        auto_accept_review_steps=get_config_bool(parser, 'debug', 'auto_accept_review_steps', False),  
        novel_to_drama_script_default_episodes_per_file=max(
            1,
            int(get_config_value(parser, 'generation', 'novel_to_drama_script_default_episodes_per_file', '10') or '10'),
        ),
        novel_to_drama_script_max_episodes_per_file=max(
            1,
            int(get_config_value(parser, 'generation', 'novel_to_drama_script_max_episodes_per_file', '20') or '20'),
        ),
    )  
