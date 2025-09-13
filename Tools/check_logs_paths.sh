#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/srv/luckypack/App"
RED='\033[0;31m'; YEL='\033[0;33m'; GRN='\033[0;32m'; NC='\033[0m'
bad=0; warn=0

echo "→ Scan in: $ROOT"

# 1) Запрещённые каталоги вида */logs внутри проекта (кроме .git/logs)
while IFS= read -r d; do
  if [[ "$d" == *"/.git/logs" ]]; then continue; fi
  echo -e "${RED}[BAD]${NC} directory: $d"
  bad=1
done < <(find "$ROOT" -type d -name logs 2>/dev/null)

# 2) Запрещённые относительные упоминания logs в коде
patterns=(
  '["'\'']logs/?["'\'']'       # 'logs' или "logs/"
  'Path\(\s*["'\'']logs'       # Path("logs")
  'os\.path\.join\([^)]*["'\'']logs["'\'']'  # os.path.join(..., "logs")
  'project/logs'               # явное проект/логи
)
for p in "${patterns[@]}"; do
  while IFS= read -r line; do
    file="${line%%:*}"; match="${line#*:}"
    # Пропуски
    [[ "$file" == *"/.git/"* ]] && continue
    [[ "$file" == *"/Tools/check_logs_paths.sh" ]] && continue
    echo -e "${RED}[BAD]${NC} $file : ${match}"
    bad=1
  done < <(grep -RInE --color=never -e "$p" "$ROOT" 2>/dev/null || true)
done

# 3) /app/logs — предупреждение (допустимо через volume, но лучше через ENV LOGS_DIR)
while IFS= read -r line; do
  file="${line%%:*}"; match="${line#*:}"
  [[ "$file" == *"/.git/"* ]] && continue
  echo -e "${YEL}[WARN]${NC} $file : ${match}"
  warn=1
done < <(grep -RIn --color=never '/app/logs' "$ROOT" 2>/dev/null || true)

# Итог
if [[ $bad -ne 0 ]]; then
  echo -e "${RED}FAIL${NC}: найдены запрещённые пути/каталоги logs. Исправляем и запускаем повторно."
  exit 2
fi

if [[ $warn -ne 0 ]]; then
  echo -e "${YEL}OK with warnings${NC}: есть обращения к /app/logs (монтируется в /srv/luckypack/logs). Рекомендуется перевести на ENV LOGS_DIR."
  exit 0
fi

echo -e "${GRN}OK${NC}: нарушений не найдено."
exit 0
