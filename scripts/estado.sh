#!/usr/bin/env bash
# Muestra las métricas del módulo stub_status de NGINX.
# Uso: bash scripts/estado.sh        (una vez)
#      bash scripts/estado.sh -w     (cada 2 s, como monitor en vivo)
set -euo pipefail
. "$(dirname "$0")/comun.sh"

if [ "${1:-}" = "-w" ]; then
    watch -n 2 "curl -s $URL/nginx_status"
else
    curl -s "$URL/nginx_status"
fi
