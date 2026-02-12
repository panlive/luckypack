#!/usr/bin/env bash
set -Eeuo pipefail

# --- Guard v3: forbid data/Data inside App, except whitelisted dirs ---
guard_no_app_data_v3(){
  APP="/srv/luckypack/App"; ROOT="/srv/luckypack"
  WHITELIST=( "/srv/luckypack/App/LuckyPricer/data" )
  BAD=$(find "$APP" -type d \( -iname data -o -iname Data \) -print || true)
  if [ -n "$BAD" ]; then
    for W in "${WHITELIST[@]}"; do
      BAD=$(printf "%s\n" "$BAD" | grep -v -E "^${W}(/|$)" || true)
    done
  fi
  RED="\033[1;31m"; YEL="\033[1;33m"; GRN="\033[1;32m"; BLD="\033[1m"; RST="\033[0m"
  if [ -n "$BAD" ]; then
    echo -e "${RED}🚫 DEPLOY BLOCKED${RST} — запрещены каталоги \"data\" внутри App (кроме белого списка)"
    echo -e "${YEL}Найдены:${RST}"
    echo "$BAD" | sed "s/^/  • /"
    echo
    echo -e "Разрешён только: ${BLD}$ROOT/data${RST} и whitelisted:"
    for W in "${WHITELIST[@]}"; do echo "  • $W"; done
    exit 1
  else
    echo -e "${GRN}✅ Guard OK${RST}: нет запрещённых \"data\" внутри App (учтён whitelist)"
  fi
}
guard_no_app_data_v3

# ------------------------------------------------------------------------------
# LuckyPack — deploy_with_backup.sh
# 1) git add/commit/push (обязателен аргумент-комментарий)
# 2) docker-compose build --no-cache
# 3) tar-бэкап /srv/luckypack → /srv/luckypack/backups/luckypack-*.tar.gz (ФОТО ИСКЛЮЧЕНЫ)
# Параллельные запуски — lock в /srv/luckypack/run/deploy.lock
# Храним 2 архива: текущий + предыдущий
# ------------------------------------------------------------------------------

ROOT="/srv/luckypack"
APP_DIR="$ROOT/App"
BACKUP_DIR="/srv/luckypack/backups"
TS="$(date +'%Y-%m-%d_%H-%M-%S')"

log(){ echo "[$(date +'%H:%M:%S')] $*"; }
err(){ echo "[ERR] $*" >&2; }

# ---- lock ----
mkdir -p "$ROOT/run"
exec 9>"$ROOT/run/deploy.lock"
if ! flock -n 9; then
  err "Другой deploy уже выполняется — выхожу."
  exit 0
fi

# ---- аргумент-комментарий ----
if [[ $# -lt 1 ]]; then
  err 'Не указан комментарий. Пример: ./Tools/deploy_with_backup.sh "deploy $(date +%F\ %T)"'
  exit 1
fi
MSG="$1"

# ---- проверки окружения ----
[[ -d "$APP_DIR" ]] || { err "Нет папки App: $APP_DIR"; exit 1; }
command -v docker >/dev/null || { err "Не найден docker"; exit 1; }
command -v tar    >/dev/null || { err "Не найден tar"; exit 1; }
[[ -d "$APP_DIR/.git" ]] || { err "Нет .git в App — выполните git init"; exit 1; }
mkdir -p "$BACKUP_DIR"

# ---- git commit + push ----
pushd "$APP_DIR" >/dev/null
git config user.name  >/dev/null 2>&1 || git config user.name  "LuckyPack"
git config user.email >/dev/null 2>&1 || git config user.email "dev@luckypack.local"

if [[ -n "$(git status --porcelain)" ]]; then
  log "Коммичу изменения…"
  git add -A
  git commit -m "$MSG"
  log "Коммит: $(git rev-parse --short HEAD)"
else
  log "Нет изменений — коммит пропущен"
fi

if git remote get-url origin >/dev/null 2>&1; then
  if ! git push; then
    log "⚠️ push не удался (продолжаю без ошибки)"
  fi
else
  log "⚠️ remote 'origin' не настроен — push пропущен"
fi
popd >/dev/null

# ---- docker build + recreate (только universal; vision исторически убран) ----
log "Docker compose build (no-cache)…"
docker-compose -f /srv/luckypack/App/docker-compose.yml build --no-cache luckypack_universal
log "Поднимаю контейнер…"
docker-compose -f /srv/luckypack/App/docker-compose.yml up -d --force-recreate luckypack_universal
log "Готово: контейнер пересобран и запущен"

# ---- tar backup ----
log "Бэкап без фото → ${BACKUP_DIR}/luckypack-${TS}.tar.gz"
INCLUDE=( "App" )
[[ -d "$ROOT/data" ]] && INCLUDE+=( "data" )
[[ -f "$ROOT/.env" ]] && INCLUDE+=( ".env" )

EXC=(
  # кодовые хвосты
  --exclude='App/.git'
  --exclude='App/**/__pycache__/**'
  --exclude='App/**/*.pyc'
  --exclude='App/**/*.pyo'
  --exclude='App/**/*.bak' --exclude='App/**/*.bak.*' --exclude='App/**/*.bak_*'
  --exclude='App/quarantine/**'
  --exclude='backups/**'

  # крупные данные/фото и их кэши
  --exclude='data/photos/**'     # основная фотобаза
  --exclude='data/fotos/**'
  --exclude='data/Photos/**'
  --exclude='data/Fotos/**'
  --exclude='DataFotos/**'

  # кэши пиков (PNG превью)
  --exclude='data/PhotoPicks/**'   # сюда входит _png и прочие
  --exclude='data/*/_png/**'       # на всякий случай любые *_png каталоги в data
)

ARCHIVE="${BACKUP_DIR}/luckypack-${TS}.tar.gz"
TMP="${ARCHIVE}.partial"
tar -C "$ROOT" -czf "$TMP" "${EXC[@]}" "${INCLUDE[@]}"
mv -f "$TMP" "$ARCHIVE"

# ---- keep only 2 latest archives ----
mapfile -t OLD < <(ls -1t "${BACKUP_DIR}"/luckypack-*.tar.gz 2>/dev/null | tail -n +3 || true)
if (( ${#OLD[@]} )); then
  log "Удаляю старые архивы (оставляю 2 последних): ${#OLD[@]} шт."
  rm -f "${OLD[@]}"
fi

log "Готово. git push, docker build (no-cache) и tar-бэкап завершены."

# bash /srv/luckypack/App/Tools/deploy_with_backup.sh "deploy $(date +'%F %T')"

# /srv/luckypack/App/Tools/deploy_with_backup.sh "deploy: fix data volume mapping; stabilize registration persistence; cleanup deploy script (drop vision, keep 2 backups)"