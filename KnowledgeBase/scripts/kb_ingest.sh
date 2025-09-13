#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="/srv/luckypack/project/KnowledgeBase"
INC="$ROOT/incoming"
SRC="$ROOT/src"
LOG="/srv/luckypack/logs/knowledgebase.log"
FAILED="$INC/_failed"
mkdir -p "$FAILED"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

echo "$(ts) [INGEST] start" >> "$LOG"

shopt -s nullglob
for f in "$INC"/*; do
  base="$(basename "$f")"
  ext="${base##*.}"
  name="${base%.*}"

  case "${ext,,}" in
    md)
      # Уже Markdown — просто переместим
      mv -f "$f" "$SRC/$base"
      echo "$(ts) [INGEST] MD moved: $base" >> "$LOG"
      ;;
    txt)
      # Оборачиваем TXT в простой MD-шаблон
      out="$SRC/${name}.md"
      {
        echo "# ${name}"
        echo
        echo "## Кратко"
        cat "$f"
        echo
        echo "## Характеристики"
        echo "- (заполнить при необходимости)"
        echo
        echo "## Преимущества"
        echo "- (заполнить при необходимости)"
        echo
        echo "## Применение"
        echo "- (заполнить при необходимости)"
        echo
        echo "## Цены и политика"
        echo "Ориентировочно; актуальность уточнять у менеджера."
      } > "$out"
      rm -f "$f"
      echo "$(ts) [INGEST] TXT -> MD: $base -> $(basename "$out")" >> "$LOG"
      ;;
    rtf)
      # Для RTF нужна внешняя утилита. Поддерживаю pandoc если установлен.
      if command -v pandoc >/dev/null 2>&1; then
        out="$SRC/${name}.md"
        if pandoc -f rtf -t gfm "$f" -o "$out"; then
          rm -f "$f"
          echo "$(ts) [INGEST] RTF -> MD via pandoc: $base -> $(basename "$out")" >> "$LOG"
        else
          mv -f "$f" "$FAILED/$base"
          echo "$(ts) [ERROR] pandoc failed: $base (moved to _failed)" >> "$LOG"
        fi
      else
        # Честно: без pandoc/unrtf корректно сконвертировать RTF — НИКАК. Складываю в _failed.
        mv -f "$f" "$FAILED/$base"
        echo "$(ts) [ERROR] No pandoc; cannot convert RTF: $base (moved to _failed)" >> "$LOG"
      fi
      ;;
    *)
      mv -f "$f" "$FAILED/$base"
      echo "$(ts) [SKIP] Unsupported: $base (moved to _failed)" >> "$LOG"
      ;;
  esac
done
echo "$(ts) [INGEST] done" >> "$LOG"
