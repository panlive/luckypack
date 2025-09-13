#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="/srv/luckypack/project/KnowledgeBase"
"$ROOT/scripts/kb_ingest.sh"
python3 "$ROOT/scripts/normalize_kb_sources.py"
echo "OK: KnowledgeBase updated (if changed)."
