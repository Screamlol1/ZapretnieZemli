"""One validation boundary for personal and campaign character sheets."""
import json
import subprocess
from pathlib import Path


def validate_sheet(sheet):
    if not isinstance(sheet,dict) or sheet.get('game')!='forbidden-lands' or not isinstance(sheet.get('name'),str):
        raise ValueError('Нужен JSON из конструктора персонажей.')
    if len(json.dumps(sheet))>100000:raise ValueError('Лист слишком большой.')
    try:
        result=subprocess.run(['node',str(Path(__file__).with_name('validate-sheet.mjs'))],input=json.dumps(sheet),
                              text=True,capture_output=True,encoding='utf-8',timeout=8)
    except (OSError,subprocess.TimeoutExpired):
        raise ValueError('Не удалось проверить лист: необходим Node.js.')
    if result.returncode:raise ValueError(result.stderr.strip()[:300] or 'Некорректный лист.')
    return json.loads(result.stdout)
