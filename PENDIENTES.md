# Pendientes del proyecto (para quien continúa)

Esta es la **versión 2** del proyecto. Los backends ya no son páginas simples: son una tienda en línea (**TecnoStore**) con base de datos MySQL. Todo el código está hecho y probado. Falta **correr las pruebas en el entorno Docker** y guardar los resultados para el informe. El PC donde se desarrolló (7.3 GB de RAM) se congelaba con las pruebas de 1000 usuarios, por eso las corre otra persona.

Antes de empezar, leer el `README.md` (sobre todo las secciones 2, 8 y 9).

## Requisitos del PC

- **16 GB de RAM o más** (la VM usa 4 GB).
- Unos **15 GB libres** en disco.
- VirtualBox, Vagrant y Git instalados.
- Durante las pruebas: cargador conectado, suspensión desactivada y sin programas pesados abiertos (Chrome, Discord).

## 1. Levantar el entorno

```bash
git clone https://github.com/ERSAgit/lb-nginx-tecnostore.git lb-nginx-tecnostore
cd lb-nginx-tecnostore/vagrant
vagrant up          # crea la VM e instala Docker (unos minutos la primera vez)
vagrant ssh
```

Dentro de la VM:

```bash
cd ~/lb-nginx-tecnostore
docker compose -f docker-compose.yml up -d --build
docker compose -f docker-compose.yml ps     # db, backend1..3 y nginx deben salir "healthy"
```

La primera vez se descarga MySQL y tarda entre 30 y 60 segundos en cargar los 500 productos. Si `ps` muestra los backends en `starting`, esperar un minuto y repetir.

Comprobar en el navegador del PC:

- `http://192.168.100.10:8080` → la tienda. Al recargar, la etiqueta de abajo a la derecha cambia de backend.
- `http://192.168.100.10:8080/cluster` → estado del clúster.
- `http://192.168.100.10:9091` → Prometheus.

Hacer una compra a mano (agregar al carrito → comprar) y revisar que aparezca en `/pedidos`.

## 2. Correr las pruebas (en este orden)

La primera vez que se usa Artillery se descarga su imagen, que es grande. Esperar a que termine.

```bash
# a) Ramp-up progresivo (~2 min)
docker compose -f docker-compose.yml run --rm artillery run rampa.yml --output /results/rampa.json | tee results/rampa_artillery.txt
python3 scripts/resumen_resultados.py results/rampa.json | tee results/rampa_resumen.md

# b) Comparación de los 3 algoritmos con 1000 compradores (~6 min)
bash scripts/comparar_algoritmos.sh

# c) Resiliencia: elimina backend2 en plena carga (~2 min)
bash scripts/cambiar_politica.sh round_robin
bash scripts/prueba_resiliencia.sh

# d) Sesión: carrito en memoria vs base de datos con cada algoritmo (~2 min)
bash scripts/prueba_sesion.sh
```

**Cómo saber si una prueba salió limpia:** Artillery imprime un reporte `Metrics for period to: HH:MM:SS` cada 10 segundos. Si entre dos reportes hay un salto de minutos, el PC se congeló y esa prueba hay que repetirla. También revisar que la columna de errores en `results/comparacion.md` esté en 0 o casi en 0.

**Si aparecen errores 502:** revisar `logs/nginx/error.log`. En el desarrollo pasó por el keep-alive (sección 7 del README) y ya está corregido; si vuelve a pasar, anotar el mensaje del log.

## 3. Capturas para el informe y las diapositivas

Durante la prueba **b)**, para **cada algoritmo**:

1. **`/cluster` en el navegador**: con round_robin y least_conn las tres barras van parejas, con ip_hash crece una sola.
2. **`stub_status` en vivo**: en otra terminal dentro de la VM, `bash scripts/estado.sh -w`. Capturar cuando `Active connections` esté cerca de 1000.
3. Al terminar, **`/pedidos`**: pedidos y ventas por backend.

Durante la prueba **c)**: captura de `/cluster` con **backend2 caído** y otra cuando vuelve.

### Gráficas de Prometheus (obligatorias)

Prometheus guarda las métricas de NGINX cada 5 segundos, así que las gráficas se pueden hacer **al terminar** la prueba **b)**: la de los 3 algoritmos queda en una sola gráfica, porque corren uno detrás de otro. Hacerlas **antes de apagar** los contenedores, porque al hacer `docker compose down` se pierden.

**Antes de empezar las pruebas**, comprobar que Prometheus está recibiendo datos:

1. En el navegador del PC abrir `http://192.168.100.10:9091`.
2. Menú **Status → Target health** (en versiones viejas, **Status → Targets**). El target `nginx` debe estar en **UP**. Si sale DOWN, revisar `docker compose -f docker-compose.yml ps`.

**Cuando termine la prueba b)**:

1. En `http://192.168.100.10:9091` ir a **Query** (en versiones viejas, **Graph**).
2. Escribir la consulta en la caja de texto, dar clic en **Execute** y luego en la pestaña **Graph**.
3. Ajustar el rango de tiempo a **15m** (el selector que está encima de la gráfica), para que se vean los 3 algoritmos.
4. Tomar captura de pantalla y guardarla en `resultados/capturas/` con el nombre que dice la tabla.

| Consulta | Qué muestra | Nombre de la captura |
|---|---|---|
| `rate(nginx_http_requests_total[30s])` | Peticiones por segundo que atiende NGINX. Se ven tres "montañas", una por algoritmo | `prometheus_req_por_segundo.png` |
| `nginx_connections_active` | Conexiones abiertas en cada momento. Debe subir cerca de 1000 en cada algoritmo | `prometheus_conexiones_activas.png` |

**Cuando termine la prueba c)**: repetir las dos consultas con rango de **5m** y guardarlas como `prometheus_resiliencia_req.png` y `prometheus_resiliencia_conexiones.png`. Aquí el total de peticiones casi no debe caer cuando se elimina backend2, porque los otros dos lo cubren.

En el informe, estas gráficas van en la sección de resultados, al lado de la tabla de comparación.

## 4. Mostrar la recarga en caliente (para el informe y la demo)

```bash
docker compose -f docker-compose.yml down
docker compose up -d                # sin -f: aplica docker-compose.override.yml
docker compose logs -f nginx        # dejar abierto
```

En otra terminal, editar `nginx/nginx.conf` (por ejemplo cambiar `proxy_read_timeout 5s;` por `6s;`) y guardar. En los logs debe aparecer `[hot-reload] configuración recargada`. Si se introduce un error de sintaxis, debe aparecer `la configuración tiene errores, NO se recarga`. Al terminar, dejar el valor como estaba.

## 5. Subir los resultados a GitHub

La carpeta `results/` no se sube (está en `.gitignore`). Copiar los resultados a `resultados/`, **sin los `.log`**, que son muy pesados:

```bash
mkdir -p resultados/docker
find results -maxdepth 1 -type f \( -name '*.json' -o -name '*.txt' -o -name '*.md' \) -exec cp {} resultados/docker/ \;
```

Guardar las capturas de pantalla en `resultados/capturas/`. Luego:

```bash
git add resultados
git commit -m "Resultados de las pruebas en Docker"
git push
```

## Lo que se espera ver (pruebas de desarrollo, sin Docker)

| Prueba | Resultado de referencia |
|---|---|
| 1000 compradores, round_robin | 0 errores, 33.33 % por backend, p99 ≈ 1.3 s |
| 1000 compradores, least_conn | 0 errores, ≈ 33 % por backend, p99 ≈ 1.25 s |
| 1000 compradores, ip_hash | 0 errores, 100 % a un solo backend, p99 ≈ 1.6 s |
| Sesión, carrito en memoria | Solo ip_hash conserva el carrito (20/20); los otros 0/20 |
| Sesión, carrito en base de datos | Los tres algoritmos 20/20 |
| Resiliencia | 0 errores, algunas peticiones reintentadas, backend2 en 0 mientras estuvo eliminado |

Los números de latencia van a cambiar con el PC; lo importante es que la tabla final del informe salga de **una sola corrida limpia de los 3 algoritmos en el mismo PC**.

## Si algo sale mal

- **Volver a empezar con la base limpia:** `docker compose down -v` y luego `up -d --build`.
- **Ver los logs de un servicio:** `docker compose -f docker-compose.yml logs --tail 50 backend1` (o `db`, `nginx`).
- **Un backend no llega a healthy:** casi siempre es porque MySQL todavía está cargando. Revisar `logs db`.
