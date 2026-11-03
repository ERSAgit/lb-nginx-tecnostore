#!/usr/bin/env bash
# Prueba de sesión: ¿el carrito sobrevive al balanceo de carga?
#
# Para cada forma de guardar el carrito (memoria de cada backend o base de datos)
# y cada algoritmo, simula 20 compradores: cada uno agrega 3 productos y luego
# revisa su carrito. Si el carrito muestra los 3, la sesión se conservó.
#
# Resultado esperado: con el carrito en memoria solo funciona ip_hash, porque es
# el único algoritmo que manda siempre al mismo cliente al mismo backend.
# Con el carrito en la base de datos funcionan los tres.
# Uso: bash scripts/prueba_sesion.sh
set -euo pipefail
. "$(dirname "$0")/comun.sh"

POLITICA_INICIAL="$BALANCE_POLICY"
mkdir -p results
SALIDA=results/sesion.md

sesiones() {
    local ok=0
    for s in $(seq 1 20); do
        local jar
        jar=$(mktemp)
        for k in 1 2 3; do
            curl -s -c "$jar" -b "$jar" -o /dev/null -X POST \
                -d "producto_id=$((s * 3 + k))" -d "cantidad=1" "$URL/carrito/agregar"
        done
        local n
        n=$(curl -s -b "$jar" "$URL/api/carrito" | python3 -c "import sys, json; print(json.load(sys.stdin)['unidades'])")
        [ "$n" = "3" ] && ok=$((ok + 1))
        rm -f "$jar"
    done
    echo "$ok"
}

{
    echo "| Carrito guardado en | round_robin | least_conn | ip_hash |"
    echo "|---|---|---|---|"
} > "$SALIDA"

for MODO in memory db; do
    echo
    echo "=== Carrito en: $MODO ==="
    sed -i "s/^CART_STORAGE=.*/CART_STORAGE=$MODO/" .env
    CART_STORAGE=$MODO $COMPOSE up -d backend1 backend2 backend3
    for b in backend1 backend2 backend3; do esperar_backend "$b"; done
    # Los backends se recrearon y pueden tener otra IP: NGINX debe volver a resolverlas
    $COMPOSE exec -T nginx nginx -s reload

    FILA="| $MODO |"
    for POL in round_robin least_conn ip_hash; do
        bash scripts/cambiar_politica.sh "$POL" > /dev/null
        esperar_balanceador > /dev/null
        OK=$(sesiones)
        echo "  $POL: $OK de 20 carritos completos"
        FILA="$FILA $OK/20 |"
    done
    echo "$FILA" >> "$SALIDA"
done

# Dejar todo como estaba
sed -i "s/^CART_STORAGE=.*/CART_STORAGE=db/" .env
CART_STORAGE=db $COMPOSE up -d backend1 backend2 backend3
for b in backend1 backend2 backend3; do esperar_backend "$b"; done
$COMPOSE exec -T nginx nginx -s reload
bash scripts/cambiar_politica.sh "$POLITICA_INICIAL" > /dev/null

echo
cat "$SALIDA"
echo
echo "Resultado guardado en $SALIDA"
