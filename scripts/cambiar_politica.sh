#!/usr/bin/env bash
# Cambia el algoritmo de balanceo y recrea el contenedor de NGINX.
# Uso: bash scripts/cambiar_politica.sh round_robin | least_conn | ip_hash
set -euo pipefail
. "$(dirname "$0")/comun.sh"

POL="${1:-}"
case "$POL" in
    round_robin|least_conn|ip_hash) ;;
    *) echo "Uso: bash scripts/$(basename $0) round_robin | least_conn | ip_hash"; exit 1 ;;
esac

sed -i "s/^BALANCE_POLICY=.*/BALANCE_POLICY=$POL/" .env
echo "Política en .env: $POL"

# Al cambiar BALANCE_POLICY cambia el archivo montado, así que Compose recrea NGINX
BALANCE_POLICY=$POL $COMPOSE up -d nginx
esperar_balanceador
echo -n "El balanceador responde con: "
curl -sI "$URL/" | grep -i "x-balance-policy" || echo "(sin cabecera)"
