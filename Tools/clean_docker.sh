#!/usr/bin/env bash
set -Eeuo pipefail

echo "[INFO] Safe Docker cleanup — started at $(date)"

# --- настройки ---
KEEP_LABEL='keep=true'     # контейнеры с этой меткой не трогаем (и даже если остановлены)
PRUNE_BUILDER=true         # чистить build-cache (чаще всего именно он ест десятки ГБ)
PRUNE_NETWORKS=true        # чистить неиспользуемые сети
PRUNE_VOLUMES=false        # ТОМA НЕ ТРОГАЕМ по умолчанию (опасно). Поменяй на true, если уверен.

# --- показать текущее состояние ---
echo
echo "[INFO] Before:"
docker system df || true
echo

# --- на всякий случай поднимем важные prod-сервисы, чтобы их образы/сети не попали под чистку ---
if command -v docker-compose >/dev/null 2>&1; then
  (cd /srv/luckypack/App && docker-compose up -d luckypack_universal luckypack_vision || true)
fi

# --- 1) остановленные контейнеры (кроме с меткой keep=true) ---
echo
echo "[INFO] Pruning stopped containers (exclude label: ${KEEP_LABEL}) ..."
docker container prune -f --filter "label!=${KEEP_LABEL}" || true

# --- 2) неиспользуемые сети ---
if [ "${PRUNE_NETWORKS}" = "true" ]; then
  echo
  echo "[INFO] Pruning unused networks ..."
  docker network prune -f || true
else
  echo "[INFO] Networks prune skipped."
fi

# --- 3) неиспользуемые образы (не только dangling). Запущенные не затронет. ---
echo
echo "[INFO] Pruning unused images (-a) ..."
docker image prune -a -f || true

# --- 4) build-cache (очень жирно). Не трогает запущенные контейнеры. ---
if [ "${PRUNE_BUILDER}" = "true" ]; then
  echo
  echo "[INFO] Pruning builder cache ..."
  docker builder prune -f || true
else
  echo "[INFO] Builder cache prune skipped."
fi

# --- 5) тома (по умолчанию — НЕТ). Включай только если знаешь, что делаешь. ---
if [ "${PRUNE_VOLUMES}" = "true" ]; then
  echo
  echo "[WARN] Pruning unused volumes (DANGEROUS if you rely on named volumes) ..."
  docker volume prune -f || true
else
  echo "[INFO] Volumes prune skipped (safety)."
fi

# --- итоговая сводка ---
echo
echo "[INFO] After:"
docker system df || true
echo
echo "[INFO] Disk usage:"
df -h / || true

echo
echo "[INFO] Done at $(date)"



# /srv/luckypack/App/Tools/clean_docker.sh