"""Editable analysis prompts; durable revision shared with model settings."""
import json
from pathlib import Path
from hub.execution_models import get
DEFAULTS=json.loads(Path(__file__).with_name('prompt_defaults.json').read_text(encoding='utf-8'))
def prompt(settings,kind):
 return get(settings.database).get('prompts',{}).get(kind) or DEFAULTS[kind]
def overview(settings):
 cfg=get(settings.database)
 return {k:cfg.get('prompts',{}).get(k) or v for k,v in DEFAULTS.items()}
