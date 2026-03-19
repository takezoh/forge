from __future__ import annotations

import json
from pathlib import Path


class PromptBuilder:
    def __init__(self, template_dir: Path):
        self._template_dir = template_dir

    def build(self, phase: str, context: dict) -> str:
        template_file = self._template_dir / f"{phase}.md"
        if not template_file.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_file}")

        template = template_file.read_text()

        for key, value in context.items():
            placeholder = "{{" + key + "}}"
            if placeholder in template:
                if isinstance(value, (dict, list)):
                    template = template.replace(placeholder, json.dumps(value, indent=2, ensure_ascii=False))
                else:
                    template = template.replace(placeholder, str(value))

        return template
