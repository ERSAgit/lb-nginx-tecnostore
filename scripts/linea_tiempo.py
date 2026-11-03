#!/usr/bin/env python3
"""Cuenta las peticiones de cada backend en intervalos de tiempo.

Sirve para ver en la prueba de resiliencia el momento en que un backend
deja de recibir tráfico y cuándo vuelve.
Uso: python3 scripts/linea_tiempo.py [archivo_de_log] [segundos_por_intervalo]
"""
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

log = sys.argv[1] if len(sys.argv) > 1 else "logs/nginx/access.log"
paso = int(sys.argv[2]) if len(sys.argv) > 2 else 10

patron = re.compile(r'\[([^\]]+)\] "[^"]*" (\d{3}) backend=(\S+)')
intervalos = defaultdict(Counter)
backends = set()
inicio = None

with open(log, encoding="utf-8", errors="replace") as f:
    for linea in f:
        m = patron.search(linea)
        if not m:
            continue
        t = datetime.strptime(m.group(1), "%d/%b/%Y:%H:%M:%S %z")
        inicio = inicio or t
        bloque = int((t - inicio).total_seconds()) // paso * paso
        backend = m.group(3) if m.group(3) != "-" else "sin_respuesta"
        intervalos[bloque][backend] += 1
        if not m.group(2).startswith("2"):
            intervalos[bloque]["errores"] += 1
        backends.add(backend)

if not intervalos:
    print("No hay peticiones en el log.")
    sys.exit(0)

cols = sorted(backends) + ["errores"]
print("segundos   " + "".join(f"{c:>14}" for c in cols))
for bloque in sorted(intervalos):
    fila = intervalos[bloque]
    print(f"{bloque:>4}-{bloque + paso:<5} " + "".join(f"{fila.get(c, 0):>14}" for c in cols))
