#!/usr/bin/env bash
# Ejecuta la prueba de 1000 usuarios con cada algoritmo y guarda los resultados.
# Uso: bash scripts/comparar_algoritmos.sh [escenario.yml]   (por defecto carga-1000.yml)
set -euo pipefail
. "$(dirname "$0")/comun.sh"

ESCENARIO="${1:-carga-1000.yml}"
mkdir -p results

for POL in round_robin least_conn ip_hash; do
    echo
    echo "=============================================="
    echo "  Algoritmo: $POL   |   Escenario: $ESCENARIO"
    echo "=============================================="
    bash scripts/cambiar_politica.sh "$POL"
    limpiar_log
    curl -s "$URL/nginx_status" > "results/${POL}_stub_antes.txt"

    $COMPOSE run --rm artillery run "$ESCENARIO" --output "/results/${POL}_carga.json" \
        | tee "results/${POL}_artillery.txt"

    curl -s "$URL/nginx_status" > "results/${POL}_stub_despues.txt"
    bash scripts/analizar_logs.sh > "results/${POL}_distribucion.txt"
    cp logs/nginx/access.log "results/${POL}_access.log"
    cat "results/${POL}_distribucion.txt"
    sleep 5
done

python3 scripts/resumen_resultados.py \
    results/round_robin_carga.json results/least_conn_carga.json results/ip_hash_carga.json \
    | tee results/comparacion.md
echo
echo "Resultados guardados en la carpeta results/"
