| Prueba | Usuarios | Peticiones | Req/s | Media (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Máx (ms) | Errores | % error |
|---|---|---|---|---|---|---|---|---|---|---|
| round_robin_carga | 250 | 15000 | 235 | 4.7 | 3.0 | 8.9 | 24.8 | 192.0 | 0 | 0.00% |
| least_conn_carga | 250 | 15000 | 235 | 4.0 | 3.0 | 7.0 | 18.0 | 58.0 | 0 | 0.00% |
| ip_hash_carga | 250 | 15000 | 230 | 31.1 | 13.9 | 120.3 | 175.9 | 591.0 | 0 | 0.00% |
