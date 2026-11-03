"""TecnoStore: tienda en línea que corre en cada backend del clúster.

Cada backend es una copia idéntica de esta aplicación. Todas comparten la
misma base de datos MySQL, así que no importa qué backend atienda una
petición: los productos, los carritos y los pedidos son los mismos.

El carrito se puede guardar en dos lugares (variable CART_STORAGE):
  - "db":     en la base de datos. Funciona con cualquier algoritmo de balanceo.
  - "memory": en la memoria del backend. Solo funciona si el usuario siempre
              cae en el mismo backend (ip_hash). Sirve para demostrar por qué.
"""
import os
import socket
import threading
import time
import urllib.request
import uuid
import json
from concurrent.futures import ThreadPoolExecutor

from flask import (Flask, abort, g, jsonify, redirect, render_template,
                   request, url_for)
from sqlalchemy import bindparam, create_engine, text

# ------------------------------------------------------------------ configuración
NODE = os.environ.get("BACKEND_NAME") or socket.gethostname()
CART_STORAGE = os.environ.get("CART_STORAGE", "db").lower()
CLUSTER_NODES = [n.strip() for n in os.environ.get("CLUSTER_NODES", "").split(",") if n.strip()]

DB_URL = os.environ.get("DATABASE_URL") or (
    "mysql+pymysql://{user}:{password}@{host}:{port}/{db}?charset=utf8mb4".format(
        user=os.environ.get("DB_USER", "tienda"),
        password=os.environ.get("DB_PASSWORD", "tienda123"),
        host=os.environ.get("DB_HOST", "db"),
        port=os.environ.get("DB_PORT", "3306"),
        db=os.environ.get("DB_NAME", "techstore"),
    )
)

engine = create_engine(
    DB_URL,
    pool_size=int(os.environ.get("DB_POOL_SIZE", "10")),
    max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "20")),
    pool_pre_ping=True,     # descarta conexiones caídas antes de usarlas
    pool_recycle=1800,
)

app = Flask(__name__)
POR_PAGINA = 24
ORDENES = {
    "relevancia": "p.calificacion DESC, p.id",
    "precio_asc": "p.precio ASC",
    "precio_desc": "p.precio DESC",
    "nombre": "p.nombre ASC",
}

# ------------------------------------------------------- estadísticas del nodo
_stats_lock = threading.Lock()
_stats = {"peticiones": 0, "desde": time.time()}
NO_CONTAR = ("/stats", "/health", "/api/cluster")


@app.before_request
def contar_peticion():
    g.inicio = time.perf_counter()
    if not request.path.startswith(NO_CONTAR):
        with _stats_lock:
            _stats["peticiones"] += 1


@app.after_request
def cabeceras(respuesta):
    respuesta.headers["X-Backend"] = NODE
    if getattr(g, "nuevo_carrito", None):
        respuesta.set_cookie("carrito", g.nuevo_carrito, max_age=7 * 24 * 3600,
                             httponly=True, samesite="Lax")
    return respuesta


# ---------------------------------------------------------------- utilidades
@app.template_filter("pesos")
def pesos(valor):
    return "$ " + f"{int(round(float(valor))):,}".replace(",", ".")


_cache_categorias = {"datos": None, "hasta": 0}


def categorias():
    """Las categorías casi nunca cambian: se guardan 60 s en memoria."""
    if time.time() > _cache_categorias["hasta"]:
        with engine.connect() as con:
            filas = con.execute(text("""
                SELECT c.id, c.slug, c.nombre, c.icono, COUNT(p.id) AS total
                FROM categorias c LEFT JOIN productos p ON p.categoria_id = c.id
                GROUP BY c.id ORDER BY c.id""")).mappings().all()
        _cache_categorias.update(datos=[dict(f) for f in filas], hasta=time.time() + 60)
    return _cache_categorias["datos"]


def politica_actual():
    # NGINX envía el algoritmo activo en esta cabecera (ver nginx.conf)
    return request.headers.get("X-Balance-Policy", "desconocida")


# ------------------------------------------------------------------- carrito
_carritos_memoria = {}
_carritos_lock = threading.Lock()


def carrito_id():
    cid = request.cookies.get("carrito")
    if not cid:
        cid = getattr(g, "nuevo_carrito", None) or str(uuid.uuid4())
        g.nuevo_carrito = cid
    return cid


def carrito_items(con=None):
    """Devuelve {producto_id: cantidad} del carrito del usuario."""
    cid = request.cookies.get("carrito") or getattr(g, "nuevo_carrito", None)
    if not cid:
        return {}
    if CART_STORAGE == "memory":
        with _carritos_lock:
            return dict(_carritos_memoria.get(cid, {}))
    consulta = text("SELECT producto_id, cantidad FROM carrito_items WHERE carrito_id = :c")
    if con is not None:
        filas = con.execute(consulta, {"c": cid}).all()
    else:
        with engine.connect() as c:
            filas = c.execute(consulta, {"c": cid}).all()
    return {pid: cant for pid, cant in filas}


def carrito_agregar(pid, cantidad):
    cid = carrito_id()
    if CART_STORAGE == "memory":
        with _carritos_lock:
            items = _carritos_memoria.setdefault(cid, {})
            items[pid] = items.get(pid, 0) + cantidad
        return
    with engine.begin() as con:
        con.execute(text("""
            INSERT INTO carrito_items (carrito_id, producto_id, cantidad)
            VALUES (:c, :p, :q) AS nuevo
            ON DUPLICATE KEY UPDATE cantidad = carrito_items.cantidad + nuevo.cantidad"""),
            {"c": cid, "p": pid, "q": cantidad})


def carrito_quitar(pid):
    cid = carrito_id()
    if CART_STORAGE == "memory":
        with _carritos_lock:
            _carritos_memoria.get(cid, {}).pop(pid, None)
        return
    with engine.begin() as con:
        con.execute(text("DELETE FROM carrito_items WHERE carrito_id = :c AND producto_id = :p"),
                    {"c": cid, "p": pid})


def carrito_vaciar(cid, con=None):
    if CART_STORAGE == "memory":
        with _carritos_lock:
            _carritos_memoria.pop(cid, None)
    elif con is not None:
        con.execute(text("DELETE FROM carrito_items WHERE carrito_id = :c"), {"c": cid})


def carrito_detalle():
    items = carrito_items()
    if not items:
        return [], 0, 0
    with engine.connect() as con:
        productos = con.execute(text("""
            SELECT p.id, p.nombre, p.marca, p.precio, c.icono
            FROM productos p JOIN categorias c ON c.id = p.categoria_id
            WHERE p.id IN :ids""").bindparams(bindparam("ids", expanding=True)),
            {"ids": list(items)}).mappings().all()
    lineas = []
    for p in productos:
        cantidad = items[p["id"]]
        lineas.append({**p, "cantidad": cantidad, "subtotal": p["precio"] * cantidad})
    total = sum(l["subtotal"] for l in lineas)
    unidades = sum(l["cantidad"] for l in lineas)
    return lineas, total, unidades


@app.context_processor
def variables_globales():
    try:
        unidades = sum(carrito_items().values())
    except Exception:
        unidades = 0
    return {"nodo": NODE, "politica": politica_actual(), "unidades_carrito": unidades,
            "modo_carrito": CART_STORAGE}


# --------------------------------------------------------------------- páginas
@app.route("/")
def catalogo():
    q = request.args.get("q", "").strip()
    cat = request.args.get("categoria", "")
    orden = request.args.get("orden", "relevancia")
    pagina = max(int(request.args.get("pagina", 1) or 1), 1)

    filtros, params = [], {}
    if q:
        filtros.append("(p.nombre LIKE :q OR p.marca LIKE :q)")
        params["q"] = f"%{q}%"
    if cat:
        filtros.append("c.slug = :cat")
        params["cat"] = cat
    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    order_by = ORDENES.get(orden, ORDENES["relevancia"])

    with engine.connect() as con:
        total = con.execute(text(f"""
            SELECT COUNT(*) FROM productos p JOIN categorias c ON c.id = p.categoria_id {where}"""),
            params).scalar()
        productos = con.execute(text(f"""
            SELECT p.id, p.nombre, p.marca, p.precio, p.calificacion, p.stock,
                   c.nombre AS categoria, c.icono, c.slug
            FROM productos p JOIN categorias c ON c.id = p.categoria_id
            {where} ORDER BY {order_by}
            LIMIT :limite OFFSET :offset"""),
            {**params, "limite": POR_PAGINA, "offset": (pagina - 1) * POR_PAGINA}).mappings().all()

    paginas = max((total + POR_PAGINA - 1) // POR_PAGINA, 1)
    return render_template("catalogo.html", productos=productos, categorias=categorias(),
                           q=q, cat=cat, orden=orden, pagina=pagina, paginas=paginas, total=total)


@app.route("/producto/<int:pid>")
def producto(pid):
    with engine.connect() as con:
        p = con.execute(text("""
            SELECT p.*, c.nombre AS categoria, c.icono, c.slug
            FROM productos p JOIN categorias c ON c.id = p.categoria_id
            WHERE p.id = :id"""), {"id": pid}).mappings().first()
        if not p:
            abort(404)
        relacionados = con.execute(text("""
            SELECT p.id, p.nombre, p.marca, p.precio, p.calificacion, c.icono
            FROM productos p JOIN categorias c ON c.id = p.categoria_id
            WHERE p.categoria_id = :cat AND p.id <> :id
            ORDER BY p.calificacion DESC LIMIT 4"""),
            {"cat": p["categoria_id"], "id": pid}).mappings().all()
    return render_template("producto.html", p=p, relacionados=relacionados)


@app.route("/carrito")
def carrito():
    lineas, total, unidades = carrito_detalle()
    return render_template("carrito.html", lineas=lineas, total=total, unidades=unidades,
                           error=request.args.get("error"))


@app.route("/carrito/agregar", methods=["POST"])
def agregar():
    pid = request.form.get("producto_id", type=int)
    cantidad = max(min(request.form.get("cantidad", 1, type=int), 10), 1)
    if not pid:
        abort(400)
    carrito_agregar(pid, cantidad)
    return redirect(url_for("carrito"), code=303)


@app.route("/carrito/quitar", methods=["POST"])
def quitar():
    pid = request.form.get("producto_id", type=int)
    if pid:
        carrito_quitar(pid)
    return redirect(url_for("carrito"), code=303)


# Después de un POST se redirige con 303 ("See Other"): el navegador o el cliente
# hace la siguiente petición con GET y recargar la página no repite la compra.
@app.route("/checkout", methods=["POST"])
def checkout():
    cid = request.cookies.get("carrito")
    if not cid:
        return redirect(url_for("carrito"), code=303)
    try:
        with engine.begin() as con:   # una sola transacción: todo o nada
            items = carrito_items(con)
            if not items:
                return redirect(url_for("carrito"), code=303)
            precios = dict(con.execute(text("SELECT id, precio FROM productos WHERE id IN :ids")
                                       .bindparams(bindparam("ids", expanding=True)),
                                       {"ids": list(items)}).all())
            for pid, cantidad in items.items():
                # Descuenta el stock solo si alcanza (evita vender de más
                # aunque dos backends procesen compras al mismo tiempo)
                r = con.execute(text("""UPDATE productos SET stock = stock - :q
                                        WHERE id = :p AND stock >= :q"""), {"p": pid, "q": cantidad})
                if r.rowcount == 0:
                    raise ValueError("sin_stock")
            total = sum(precios[pid] * cant for pid, cant in items.items())
            unidades = sum(items.values())
            pedido_id = con.execute(text("""
                INSERT INTO pedidos (carrito_id, total, unidades, backend)
                VALUES (:c, :t, :u, :b)"""), {"c": cid, "t": total, "u": unidades, "b": NODE}).lastrowid
            con.execute(text("""
                INSERT INTO pedido_items (pedido_id, producto_id, cantidad, precio_unitario)
                VALUES (:pedido, :p, :q, :precio)"""),
                [{"pedido": pedido_id, "p": pid, "q": cant, "precio": precios[pid]}
                 for pid, cant in items.items()])
            carrito_vaciar(cid, con)
    except ValueError:
        return redirect(url_for("carrito", error="sin_stock"), code=303)
    if CART_STORAGE == "memory":
        carrito_vaciar(cid)
    return redirect(url_for("pedido", pedido_id=pedido_id), code=303)


@app.route("/pedido/<int:pedido_id>")
def pedido(pedido_id):
    with engine.connect() as con:
        ped = con.execute(text("SELECT * FROM pedidos WHERE id = :id"),
                          {"id": pedido_id}).mappings().first()
        if not ped:
            abort(404)
        items = con.execute(text("""
            SELECT pi.cantidad, pi.precio_unitario, p.nombre, c.icono
            FROM pedido_items pi
            JOIN productos p ON p.id = pi.producto_id
            JOIN categorias c ON c.id = p.categoria_id
            WHERE pi.pedido_id = :id"""), {"id": pedido_id}).mappings().all()
    return render_template("pedido.html", pedido=ped, items=items)


@app.route("/pedidos")
def pedidos():
    with engine.connect() as con:
        lista = con.execute(text("""
            SELECT id, total, unidades, backend, creado FROM pedidos
            ORDER BY id DESC LIMIT 25""")).mappings().all()
        por_backend = con.execute(text("""
            SELECT backend, COUNT(*) AS pedidos, SUM(total) AS ventas
            FROM pedidos GROUP BY backend ORDER BY backend""")).mappings().all()
    return render_template("pedidos.html", pedidos=lista, por_backend=por_backend)


@app.route("/cluster")
def cluster():
    return render_template("cluster.html")


# ------------------------------------------------------------------ API REST
@app.route("/api/productos")
def api_productos():
    q = request.args.get("q", "").strip()
    cat = request.args.get("categoria", "")
    limite = max(min(request.args.get("limite", 20, type=int), 50), 1)
    filtros, params = [], {"limite": limite}
    if q:
        filtros.append("(p.nombre LIKE :q OR p.marca LIKE :q)")
        params["q"] = f"%{q}%"
    if cat:
        filtros.append("c.slug = :cat")
        params["cat"] = cat
    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    with engine.connect() as con:
        filas = con.execute(text(f"""
            SELECT p.id, p.nombre, p.marca, p.precio, p.stock, c.slug AS categoria
            FROM productos p JOIN categorias c ON c.id = p.categoria_id
            {where} ORDER BY p.calificacion DESC, p.id LIMIT :limite"""), params).mappings().all()
    return jsonify(backend=NODE, productos=[{**f, "precio": float(f["precio"])} for f in filas])


@app.route("/api/productos/<int:pid>")
def api_producto(pid):
    with engine.connect() as con:
        p = con.execute(text("""
            SELECT p.id, p.nombre, p.marca, p.descripcion, p.precio, p.stock,
                   p.calificacion, c.slug AS categoria
            FROM productos p JOIN categorias c ON c.id = p.categoria_id
            WHERE p.id = :id"""), {"id": pid}).mappings().first()
    if not p:
        return jsonify(error="producto no encontrado"), 404
    return jsonify(backend=NODE, producto={**p, "precio": float(p["precio"]),
                                           "calificacion": float(p["calificacion"])})


@app.route("/api/carrito")
def api_carrito():
    items = carrito_items()
    return jsonify(backend=NODE, modo=CART_STORAGE, unidades=sum(items.values()),
                   items=[{"producto_id": k, "cantidad": v} for k, v in items.items()])


# --------------------------------------------------------- estado del clúster
@app.route("/stats")
def stats():
    with _stats_lock:
        datos = dict(_stats)
    return jsonify(backend=NODE, peticiones=datos["peticiones"],
                   activo_seg=int(time.time() - datos["desde"]), carrito=CART_STORAGE)


@app.route("/stats/reset", methods=["POST"])
def stats_reset():
    with _stats_lock:
        _stats.update(peticiones=0, desde=time.time())
    return jsonify(backend=NODE, reiniciado=True)


def _consultar_nodo(nodo, metodo="GET", ruta="/stats"):
    try:
        req = urllib.request.Request(f"http://{nodo}{ruta}", method=metodo)
        with urllib.request.urlopen(req, timeout=1.5) as r:
            return {"nodo": nodo, "activo": True, **json.loads(r.read())}
    except Exception:
        return {"nodo": nodo, "backend": nodo.split(":")[0], "activo": False, "peticiones": None}


@app.route("/api/cluster")
def api_cluster():
    """El backend que atiende pregunta a todos los nodos por la red interna."""
    with ThreadPoolExecutor(max_workers=max(len(CLUSTER_NODES), 1)) as ex:
        nodos = list(ex.map(_consultar_nodo, CLUSTER_NODES))
    total = sum(n["peticiones"] or 0 for n in nodos)
    return jsonify(atendido_por=NODE, politica=politica_actual(), total=total, nodos=nodos)


@app.route("/api/cluster/reset", methods=["POST"])
def api_cluster_reset():
    with ThreadPoolExecutor(max_workers=max(len(CLUSTER_NODES), 1)) as ex:
        list(ex.map(lambda n: _consultar_nodo(n, "POST", "/stats/reset"), CLUSTER_NODES))
    return jsonify(reiniciado=True)


@app.route("/health")
def health():
    try:
        with engine.connect() as con:
            con.execute(text("SELECT 1"))
        return jsonify(estado="ok", backend=NODE, base_de_datos="ok")
    except Exception:
        return jsonify(estado="error", backend=NODE, base_de_datos="sin conexión"), 503


@app.errorhandler(404)
def no_encontrado(_):
    return render_template("error.html", codigo=404, mensaje="No encontramos lo que buscas."), 404


@app.errorhandler(500)
def error_interno(_):
    return render_template("error.html", codigo=500, mensaje="Algo salió mal en este backend."), 500
