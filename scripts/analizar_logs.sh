#!/usr/bin/env bash
# Analiza el access.log de NGINX: distribución real de peticiones por backend,
# códigos de estado y peticiones que necesitaron reintento.
# Uso: bash scripts/analizar_logs.sh [archivo_de_log]
set -euo pipefail
cd "$(dirname "$0")/.."
LOG="${1:-logs/nginx/access.log}"

TOTAL=$(grep -c 'backend=' "$LOG" || true)
if [ "$TOTAL" -eq 0 ]; then echo "El log está vacío: $LOG"; exit 0; fi

echo "Archivo: $LOG"
echo "Total de peticiones: $TOTAL"
echo
echo "== Peticiones por backend =="
grep -o 'backend=[^ ]*' "$LOG" | sed 's/^backend=//; s/^-$/(sin respuesta)/' \
    | sort | uniq -c | sort -rn \
    | awk -v t="$TOTAL" '{ printf "  %-16s %8d  %6.2f%%\n", $2, $1, 100*$1/t }'
echo
echo "== Códigos de estado HTTP =="
grep -oE '" [0-9]{3} ' "$LOG" | tr -d '" ' | sort | uniq -c | sort -rn \
    | awk -v t="$TOTAL" '{ printf "  %-16s %8d  %6.2f%%\n", $2, $1, 100*$1/t }'
echo
REINTENTOS=$(grep -c 'upstream=[^ ]*, ' "$LOG" || true)
echo "== Peticiones que se reintentaron en otro backend: $REINTENTOS =="
