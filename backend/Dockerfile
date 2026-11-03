# Imagen base: Python 3.12 sobre Debian "slim"
FROM python:3.12-slim

WORKDIR /app

# Primero las dependencias: si solo cambia el código, Docker reutiliza esta capa
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates ./templates

EXPOSE 8080

# Gunicorn: servidor WSGI de producción.
# Un solo proceso (worker) con varios hilos: así cada backend tiene UNA sola
# memoria, necesario para el modo CART_STORAGE=memory de la prueba de sesión.
# --keep-alive 75: el backend mantiene las conexiones inactivas MÁS tiempo que
# NGINX (60 s). Si el backend las cerrara antes, NGINX podría reutilizar una
# conexión ya cerrada y recibir un error.
CMD ["sh", "-c", "exec gunicorn --workers 1 --threads ${GUNICORN_THREADS:-32} --backlog 2048 --bind 0.0.0.0:8080 --keep-alive 75 --timeout 30 --graceful-timeout 10 app:app"]
