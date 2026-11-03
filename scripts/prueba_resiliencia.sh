#!/usr/bin/env bash
# Prueba de resiliencia: con carga constante, elimina backend2 en caliente,
# espera, lo vuelve a crear y analiza si el servicio se interrumpió.
# Uso: bash scripts/prueba_resiliencia.sh [backend]   (por defecto backend2)
set -euo pipefail
. "$(dirname "$0")/comun.sh"

VICTIMA="${1:-backend2}"
mkdir -p results
esperar_balanceador
limpiar_log

echo "$(date +%T)  Iniciando carga constante de 90 s (política: $BALANCE_POLICY)"
$COMPOSE run --rm artillery run resiliencia.yml --output /results/resiliencia.json \
    > results/resiliencia_artillery.txt 2>&1 &
CARGA=$!

sleep 30
echo "$(date +%T)  ELIMINANDO $VICTIMA en caliente"
$COMPOSE rm -sf "$VICTIMA"
$COMPOSE ps

sleep 30
echo "$(date +%T)  RECREANDO $VICTIMA"
$COMPOSE up -d "$VICTIMA"
esperar_backend "$VICTIMA"
# NGINX resuelve los nombres de los backends al arrancar. Si el contenedor
# nuevo recibió otra IP, una recarga hace que NGINX la vuelva a resolver.
$COMPOSE exec -T nginx nginx -s reload
echo "$(date +%T)  $VICTIMA de vuelta y NGINX recargado"

wait $CARGA || true
echo "$(date +%T)  Carga terminada"

cp logs/nginx/access.log results/resiliencia_access.log
bash scripts/analizar_logs.sh results/resiliencia_access.log | tee results/resiliencia_distribucion.txt
echo
echo "== Peticiones por backend cada 10 s =="
python3 scripts/linea_tiempo.py results/resiliencia_access.log 10 | tee results/resiliencia_linea_tiempo.txt
echo
python3 scripts/resumen_resultados.py results/resiliencia.json | tee results/resiliencia_resumen.md
