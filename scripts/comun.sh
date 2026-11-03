# Funciones y variables compartidas por los scripts. No se ejecuta solo.
cd "$(dirname "$0")/.."

# Las pruebas usan SOLO el archivo base (sin el override de desarrollo)
COMPOSE="docker compose -f docker-compose.yml"

# Leer valores de .env sin exportarlos (para no tapar los cambios que hagan los scripts)
leer_env() { grep -E "^$1=" .env | tail -1 | cut -d= -f2-; }
PUBLIC_PORT="$(leer_env PUBLIC_PORT)"
BALANCE_POLICY="$(leer_env BALANCE_POLICY)"

URL="http://localhost:${PUBLIC_PORT}"

esperar_balanceador() {
    echo -n "Esperando a que el balanceador responda"
    for _ in $(seq 1 60); do
        if curl -sf "$URL/lb-health" >/dev/null 2>&1; then echo " listo."; return 0; fi
        echo -n "."; sleep 1
    done
    echo " no respondió a tiempo."; return 1
}

esperar_backend() {   # $1 = nombre del servicio
    echo -n "Esperando a que $1 esté healthy"
    for _ in $(seq 1 60); do
        estado=$(docker inspect -f '{{.State.Health.Status}}' "$($COMPOSE ps -q "$1")" 2>/dev/null || true)
        if [ "$estado" = "healthy" ]; then echo " listo."; return 0; fi
        echo -n "."; sleep 1
    done
    echo " no quedó healthy a tiempo."; return 1
}

limpiar_log() {
    $COMPOSE exec -T nginx sh -c ': > /var/log/nginx/access.log'
}
