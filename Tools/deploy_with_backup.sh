#!/usr/bin/env bash
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# LuckyPack — deploy_with_backup.sh
# 1) git add/commit/push (обязателен аргумент-комментарий)
# 2) docker build --no-cache  (теги: latest + timestamp)
# 3) tar-бэкап /srv/luckypack → /srv/backups/luckypack-*.tar.gz (ФОТО ИСКЛЮЧЕНЫ)
# Параллельные запуски — lock в /srv/luckypack/run/deploy.lock
# ------------------------------------------------------------------------------

ROOT="/srv/luckypack"
APP_DIR="$ROOT/App"
BACKUP_DIR="/srv/luckypack/backups"
IMAGE_NAME="luckypack_universal"
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

# ---- docker build ----
log "Docker compose build (no-cache)…"
docker-compose -f /srv/luckypack/App/docker-compose.yml build --no-cache
log "Поднимаю контейнеры…"
docker-compose -f /srv/luckypack/App/docker-compose.yml up -d --force-recreate luckypack_universal luckypack_vision
log "Готово: контейнеры пересобраны и запущены"
log "Бэкап без фото → ${BACKUP_DIR}/luckypack-${TS}.tar.gz"
INCLUDE=( "App" )
[[ -d "$ROOT/data" ]] && INCLUDE+=( "data" )
[[ -f "$ROOT/.env" ]] && INCLUDE+=( ".env" )

EXC=(
  --exclude='App/.git'
  --exclude='App/__pycache__'
  --exclude='App/*.bak' --exclude='App/*.bak.*'
  --exclude='App/quarantine/**'
  --exclude='backups/**'
  # фото
  --exclude='data/photos/**'
  --exclude='data/fotos/**'
  --exclude='data/Photos/**'
  --exclude='data/Fotos/**'
  --exclude='DataFotos/**'
)
ARCHIVE="${BACKUP_DIR}/luckypack-${TS}.tar.gz"
TMP="${ARCHIVE}.partial"
tar -C "$ROOT" -czf "$TMP" "${EXC[@]}" "${INCLUDE[@]}"
mv -f "$TMP" "$ARCHIVE"

# оставляем только один последний архив
mapfile -t OLD < <(ls -1t "${BACKUP_DIR}"/luckypack-*.tar.gz 2>/dev/null | tail -n +2 || true)
if (( ${#OLD[@]} )); then
  log "Удаляю старые архивы: ${#OLD[@]} шт."
  rm -f "${OLD[@]}"
fi

log "Готово. git push, docker build (no-cache) и tar-бэкап завершены."




# bash /srv/luckypack/App/Tools/deploy_with_backup.sh "deploy $(date +'%F %T')"