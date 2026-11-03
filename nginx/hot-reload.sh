#!/bin/sh
# Solo para desarrollo (lo usa docker-compose.override.yml).
# Arranca NGINX y lo recarga en caliente cuando cambia la configuración.

nginx -g "daemon off; worker_processes ${NGINX_WORKERS:-auto};" &
NGINX_PID=$!

trap 'nginx -s quit; exit 0' TERM INT

checksum() { cat /etc/nginx/nginx.conf /etc/nginx/upstream.conf | md5sum; }
LAST=$(checksum)
echo "[hot-reload] vigilando cambios en la configuración de NGINX..."

while kill -0 "$NGINX_PID" 2>/dev/null; do
    sleep 2
    NOW=$(checksum)
    if [ "$NOW" != "$LAST" ]; then
        LAST=$NOW
        if nginx -t -q; then
            nginx -s reload && echo "[hot-reload] configuración recargada"
        else
            echo "[hot-reload] la configuración tiene errores, NO se recarga"
        fi
    fi
done
