 
from configparser import ConfigParser 
from functools import lru_cache 
from pathlib import Path 
 
@lru_cache(maxsize=4) 
def load_repo_config(repo_root: Path) -> ConfigParser: 
    parser = ConfigParser() 
    config_path = (repo_root / 'config.ini').resolve() 
    if config_path.exists(): 
        parser.read(config_path, encoding='utf-8-sig') 
    return parser 
 
def get_config_value(parser: ConfigParser, section: str, option: str, default: str = '') -> str: 
    if not parser.has_section(section) or not parser.has_option(section, option): 
        return default 
    return parser.get(section, option, fallback=default).strip() 
 
def get_config_bool(parser: ConfigParser, section: str, option: str, default: bool) -> bool: 
    if not parser.has_section(section) or not parser.has_option(section, option): 
        return default 
    return parser.getboolean(section, option, fallback=default)
