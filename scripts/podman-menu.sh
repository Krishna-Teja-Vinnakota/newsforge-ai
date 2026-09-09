#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

if ! command -v podman >/dev/null 2>&1; then
  echo "Podman is not installed or is not available in PATH."
  exit 1
fi

compose() { podman compose "$@"; }

while true; do
  cat <<'MENU'

NewsForge Podman control
  1) Run all services
  2) Rebuild and restart all services
  3) Restart backend
  4) Restart public frontend
  5) Restart NewsForge Studio
  6) Add or refresh dummy stories
  7) Show service status
  8) Follow all logs
  9) Stop services
  0) Exit
MENU
  read -r -p "Select an option: " choice
  case "$choice" in
    1) compose up -d ;;
    2) compose up -d --build --force-recreate ;;
    3) compose up -d --build --force-recreate backend ;;
    4) compose up -d --build --force-recreate frontend ;;
    5) compose up -d --build --force-recreate studio ;;
    6) compose up -d backend && compose exec backend python scripts/seed_dummy_stories.py ;;
    7) compose ps ;;
    8) compose logs -f ;;
    9) compose down ;;
    0) exit 0 ;;
    *) echo "Choose a number from 0 to 9." ;;
  esac
done
