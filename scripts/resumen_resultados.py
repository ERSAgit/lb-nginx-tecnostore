#!/usr/bin/env python3
"""Resume los JSON que genera Artillery en una tabla Markdown.

Uso: python3 scripts/resumen_resultados.py results/round_robin_carga.json results/least_conn_carga.json ...
     python3 scripts/resumen_resultados.py results/*_carga.json
"""
import json
import os
import sys


def resumir(ruta):
    with open(ruta, encoding="utf-8") as f:
        datos = json.load(f)["aggregate"]
    c = datos.get("counters", {})
    s = datos.get("summaries", {}).get("http.response_time", {})
    r = datos.get("rates", {})
    # Error = respuesta 4xx/5xx o fallo de red. Las redirecciones (3xx) son normales.
    errores_http = sum(v for k, v in c.items()
                       if k.startswith("http.codes.4") or k.startswith("http.codes.5"))
    errores_red = sum(v for k, v in c.items() if k.startswith("errors."))
    peticiones = c.get("http.requests", 0)
    tasa_error = 100 * (errores_red + errores_http) / peticiones if peticiones else 0
    return {
        "prueba": os.path.basename(ruta).replace(".json", ""),
        "usuarios": c.get("vusers.created", 0),
        "peticiones": peticiones,
        "rps": r.get("http.request_rate", 0),
        "media": s.get("mean", 0),
        "p50": s.get("median", s.get("p50", 0)),
        "p95": s.get("p95", 0),
        "p99": s.get("p99", 0),
        "max": s.get("max", 0),
        "errores": errores_red + errores_http,
        "tasa_error": tasa_error,
    }


filas = [resumir(p) for p in sys.argv[1:]]
if not filas:
    print(__doc__)
    sys.exit(1)

print("| Prueba | Usuarios | Peticiones | Req/s | Media (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Máx (ms) | Errores | % error |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for f in filas:
    print(f"| {f['prueba']} | {f['usuarios']} | {f['peticiones']} | {f['rps']} | {f['media']:.1f} | "
          f"{f['p50']:.1f} | {f['p95']:.1f} | {f['p99']:.1f} | {f['max']:.1f} | {f['errores']} | {f['tasa_error']:.2f}% |")
