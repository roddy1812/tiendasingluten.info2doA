"""
Tienda Sin Gluten - Flask + MySQL (XAMPP).

Las paginas (inicio, registro y pago) conservan su diseno y su JavaScript.
Flask guarda las cuentas y las compras en MySQL y entrega los productos
desde la base de datos.

Uso:
    pip install -r requirements.txt
    (iniciar MySQL en XAMPP)
    python singluten.py
    abrir http://localhost:5000
"""

import hmac
from datetime import date, datetime

import os
import uuid
import re
from collections import OrderedDict

import mysql.connector
from flask import (Flask, jsonify, redirect, render_template, request, session,
                   url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from flask import request, jsonify, url_for

# ---------------------------------------------------------------- configuracion
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),  # XAMPP por defecto: sin contrasena
    "database": os.getenv("DB_NAME", "tiendanogluten"),
    "autocommit": True,  # el pedido usa start_transaction() / commit() explicitos
}

# Empleado que figura como vendedor de las ventas online (ventas.id_vendedor).
# Vacio = NULL (la tabla lo permite).
_vend = os.getenv("ID_VENDEDOR_ONLINE", "").strip()
ID_VENDEDOR_ONLINE = int(_vend) if _vend else None

METODOS = {
    "transferencia": "Transferencia",
    "tarjeta": "Tarjeta",
    "tigo": "Tigo Money",
    "efectivo": "Efectivo",
}
MAX_UNIDADES = 99
RE_TELEFONO = re.compile(r"0\d{9}", re.ASCII)
RE_RUC = re.compile(r"\d{5,8}-?\d?", re.ASCII)

# La tabla productos no tiene columna de imagen: se asocia por codigo.
# Las rutas locales van en la carpeta static/ (static/Imagenes/...).
IMAGENES = {
    11: "https://snapcalorie-webflow-website.s3.us-east-2.amazonaws.com/media/food_pics_v2/medium/alfajor_dulce_de_leche.jpg",
    12: "https://images.unsplash.com/photo-1499636136210-6f4ee915583e?w=500",
    13: "https://images.rawpixel.com/image_social_landscape/cHJpdmF0ZS9sci9pbWFnZXMvd2Vic2l0ZS8yMDI0LTAyL3Jhd3BpeGVsX29mZmljZV80M19waG90b19vZl90d29fZnVkZ3lfYnJvd25pZXNfX2lzb2xhdGVkX29uX3doaV9iNGQyNmJjMC1hZmU3LTQ1ZGMtOTRjZi01MzEyZDQzMGEyN2MuanBn.jpg",
    14: "https://laopinionaustral.com.ar/media/uploads/2025/09/pasta-frola-receta-728x728.webp",
    15: "https://images.unsplash.com/photo-1578985545062-69928b1d9587?w=500",
    21: "https://snapcalorie-webflow-website.s3.us-east-2.amazonaws.com/media/food_pics_v2/medium/veggie_sandwich.jpg",
    22: "https://s.yimg.com/ny/api/res/1.2/qAJoajyEAfWxiL2oBaKdFQ--/YXBwaWQ9aGlnaGxhbmRlcjt3PTk2MDtoPTk2MDtjZj13ZWJw/https%3A/media.zenfs.com/en/parade_250/8d260067aebd3ebc8f4833b5350e76ad",
    23: "https://www.robineau.co.uk/assets/images/product/2754.jpg",
    24: "https://www.instacart.com/assets/domains/product-image/file/large_fbc8ce83-7f5c-4e54-8b6e-63f76864bd2c.jpg",
    30: "https://digitalcontent.api.tesco.com/v2/media/ghs/2872abcd-3e14-4465-8977-7fe918aa2f84/22703f29-05c0-4149-b6b3-fe7055997edf_915223545.jpeg",
    31: "https://digitalcontent.api.tesco.com/v2/media/ghs/2872abcd-3e14-4465-8977-7fe918aa2f84/22703f29-05c0-4149-b6b3-fe7055997edf_915223545.jpeg",
    32: "Imagenes/harina de arroz.jpg",
    33: "Imagenes/harina de arroz.jpg",
    34: "https://rhbulk.com/cdn/shop/files/RHBulk_Yellow-Corn-Flour-Flat.jpg?v=1776446293",
    35: "https://rhbulk.com/cdn/shop/files/RHBulk_Yellow-Corn-Flour-Flat.jpg?v=1776446293",
    36: "https://cdn.ekokoza.com/images/0/686f8a9ab37a3126/2/micronized-rice-powder-rice-starch-5kg.webp?hash=1108330435",
    37: "https://cdn.ekokoza.com/images/0/686f8a9ab37a3126/2/micronized-rice-powder-rice-starch-5kg.webp?hash=1108330435",
    38: "Imagenes/almidon de mandioca.jpg",
    39: "Imagenes/almidon de mandioca.jpg",
}

app = Flask(__name__)

CARPETA_IMAGENES = os.path.join(
    app.root_path, "static", "imagenes", "productos"
)
os.makedirs(CARPETA_IMAGENES, exist_ok=True)

EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".webp"}
TAMANO_MAXIMO_IMAGEN = 5 * 1024 * 1024
# Cambia esta clave en produccion (variable de entorno SECRET_KEY).
app.secret_key = os.getenv("SECRET_KEY", "clave-local-de-desarrollo")

CARPETA_IMAGENES = os.path.join(
    app.root_path, "static", "imagenes", "productos"
)

os.makedirs(CARPETA_IMAGENES, exist_ok=True)

EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".webp"}
TAMANO_MAXIMO_IMAGEN = 5 * 1024 * 1024  # 5 MB

app.config["MAX_CONTENT_LENGTH"] = TAMANO_MAXIMO_IMAGEN

# ---------------------------------------------------------------- utilidades

def guardar_imagen(archivo):
    if not archivo or not archivo.filename:
        return None, "Selecciona una imagen."

    nombre_seguro = secure_filename(archivo.filename)
    extension = os.path.splitext(nombre_seguro)[1].lower()

    if extension not in EXTENSIONES_IMAGEN:
        return None, "Formato no permitido. Usa JPG, PNG o WEBP."

    archivo.stream.seek(0, os.SEEK_END)
    tamano = archivo.stream.tell()
    archivo.stream.seek(0)

    if tamano == 0:
        return None, "El archivo está vacío."

    if tamano > TAMANO_MAXIMO_IMAGEN:
        return None, "La imagen no puede superar los 5 MB."

    nombre_archivo = f"{uuid.uuid4().hex}{extension}"
    ruta = os.path.join(CARPETA_IMAGENES, nombre_archivo)

    archivo.save(ruta)

    return f"imagenes/productos/{nombre_archivo}", None

def conectar():
    return mysql.connector.connect(**DB_CONFIG)


@app.template_filter("gs")
def formatear_gs(valor):
    return "Gs. " + f"{int(round(float(valor))):,}".replace(",", ".")


def url_imagen(cod):
    conn = conectar()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT imagen FROM productos WHERE cod_producto = %s",
            (cod,)
        )
        producto = cur.fetchone()

        if not producto or not producto["imagen"]:
            return ""

        ruta = producto["imagen"]

        if ruta.startswith("http"):
            return ruta

        return url_for("static", filename=ruta)

    finally:
        conn.close()


@app.context_processor
def contexto_global():
    return {"url_imagen": url_imagen}


def cargar_productos(conn):
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT cod_producto, nombre, precio, categoria, imagen
        FROM productos
        ORDER BY cod_producto
    """)
    productos = cur.fetchall()

    for p in productos:
        p["precio"] = float(p["precio"] or 0)

    return productos


# ---------------------------------------------------------------- paginas

@app.route("/")
@app.route("/inicio.html")
def inicio():
    conn = conectar()
    try:
        productos = cargar_productos(conn)
    finally:
        conn.close()

    categorias = OrderedDict()
    for p in productos:
        categorias.setdefault(p["categoria"], []).append(p)

    return render_template("inicio.html", categorias=categorias)


@app.route("/registro")
@app.route("/registro.html")
def registro():
    return render_template("registro.html")


@app.route("/pago")
@app.route("/pago.html")
def pago():
    if "n_cliente" not in session:
        return redirect(url_for("registro"))

    return render_template("pago.html")


# ---------------------------------------------------------------- cuenta
def validar_registro(v, contrasena):
    """Devuelve (id_del_campo, mensaje) del primer error, o None si todo esta bien."""
    for campo in ("nombre", "apellido", "direccion", "telefono"):
        if not v[campo]:
            return f"reg-{campo}", "Este campo es obligatorio."
    if not contrasena:
        return "reg-contrasena", "Este campo es obligatorio."

    for campo, maximo in (("nombre", 100), ("apellido", 100), ("direccion", 150)):
        if len(v[campo]) > maximo:
            return f"reg-{campo}", f"Máximo {maximo} caracteres."
    if not RE_TELEFONO.fullmatch(v["telefono"]):
        return "reg-telefono", "Debe tener 10 números y empezar por 0, sin espacios."
    if (len(contrasena) < 8 or re.search(r"\s", contrasena)
            or not re.search(r"\d", contrasena, re.ASCII)
            or not re.search(r"[a-zA-ZáéíóúÁÉÍÓÚñÑ]", contrasena)):
        return "reg-contrasena", "Mínimo 8 caracteres, sin espacios, con al menos una letra y un número."
    if v["ruc"] and not RE_RUC.fullmatch(v["ruc"]):
        return "reg-ruc", "El RUC debe contener solo números, con guion opcional antes del dígito verificador."
    return None


@app.post("/api/registro")
def api_registro():
    d = request.get_json(silent=True) or {}
    v = {k: str(d.get(k, "")).strip() for k in ("nombre", "apellido", "direccion", "telefono", "ruc")}
    contrasena = str(d.get("contrasena", ""))

    error = validar_registro(v, contrasena)
    if error:
        return jsonify(campo=error[0], error=error[1]), 400

    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM clientes WHERE telefono = %s", (v["telefono"],))
        if cur.fetchone():
            return jsonify(campo="reg-telefono", error="Ya existe una cuenta con este número."), 409
        cur.execute(
            "INSERT INTO clientes (nombre, apellido, direccion, telefono, ruc, contrasena) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (v["nombre"], v["apellido"], v["direccion"], v["telefono"],
             v["ruc"] or None, generate_password_hash(contrasena)),
        )
        n_cliente = cur.lastrowid
    except mysql.connector.IntegrityError:
        return jsonify(campo="reg-telefono", error="Ya existe una cuenta con este número."), 409
    except mysql.connector.Error:
        app.logger.exception("Error al registrar el cliente")
        return jsonify(error="No pudimos crear tu cuenta. Intenta de nuevo en unos minutos."), 500
    finally:
        conn.close()

    session.clear()
    session["n_cliente"] = n_cliente
    return jsonify(ok=True, nombre=v["nombre"])


@app.post("/api/login")
def api_login():
    d = request.get_json(silent=True) or {}
    telefono = str(d.get("telefono", "")).strip()
    contrasena = str(d.get("contrasena", ""))

    conn = conectar()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT n_cliente, nombre, contrasena FROM clientes WHERE telefono = %s", (telefono,))
        fila = cur.fetchone()
    except mysql.connector.Error:
        app.logger.exception("Error al iniciar sesion")
        return jsonify(error="No pudimos iniciar sesión. Intenta de nuevo en unos minutos."), 500
    finally:
        conn.close()

    if not fila or not fila["contrasena"] or not check_password_hash(fila["contrasena"], contrasena):
        return jsonify(error="Teléfono o contraseña incorrectos."), 401

    session.clear()
    session["n_cliente"] = fila["n_cliente"]
    return jsonify(ok=True, nombre=fila["nombre"])


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/cuenta")
def api_cuenta():
    n_cliente = session.get("n_cliente")
    if not n_cliente:
        return jsonify(error="No hay sesión iniciada."), 401

    conn = conectar()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT nombre, apellido, direccion, telefono FROM clientes WHERE n_cliente = %s",
            (n_cliente,),
        )
        fila = cur.fetchone()
    finally:
        conn.close()

    if not fila:
        session.clear()
        return jsonify(error="La cuenta ya no existe."), 401
    return jsonify(fila)


# ---------------------------------------------------------------- pedido
def registrar_pedido(conn, n_cliente, cantidades, metodo, direccion_entrega):
    """Inserta una fila en ventas por producto. Devuelve el codigo de pedido."""
    cur = conn.cursor(dictionary=True)
    conn.start_transaction()

    # ventas.codigo agrupa todas las lineas de una misma compra
    cur.execute("SELECT COALESCE(MAX(codigo), 10000) + 1 AS sig FROM ventas FOR UPDATE")
    codigo = cur.fetchone()["sig"]

    cur.executemany(
        "INSERT INTO ventas (id_product, id_comprador, codigo, u_vendidas, id_vendedor, "
        "metodo_pago, direccion_entrega) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        [(cod, n_cliente, codigo, n, ID_VENDEDOR_ONLINE, metodo, direccion_entrega)
         for cod, n in cantidades.items()],
    )
    conn.commit()
    return codigo


@app.post("/api/pedido")
def api_pedido():
    if "n_cliente" not in session:
        return jsonify(error="Inicia sesión para pagar."), 401

    d = request.get_json(silent=True) or {}
    metodo = str(d.get("metodo", ""))
    direccion = str(d.get("direccion_entrega", "")).strip()
    telefono_tigo = str(d.get("telefono_tigo", "")).strip()

    if metodo not in METODOS:
        return jsonify(error="Elige un método de pago."), 400
    if not direccion:
        return jsonify(error="Ingresa la dirección de entrega."), 400
    if len(direccion) > 150:
        return jsonify(error="La dirección de entrega es demasiado larga (máximo 150 caracteres)."), 400
    if metodo == "tigo" and not RE_TELEFONO.fullmatch(telefono_tigo):
        return jsonify(error="El número de celular debe tener 10 números y empezar por 0, sin espacios."), 400

    # El navegador manda codigos y cantidades; los precios se toman de la base.
    cantidades = {}
    try:
        for it in d.get("items", []):
            cod, cantidad = int(it["cod"]), int(it["cantidad"])
            if cantidad < 1:
                raise ValueError
            cantidades[cod] = min(cantidades.get(cod, 0) + cantidad, MAX_UNIDADES)
    except (KeyError, TypeError, ValueError):
        return jsonify(error="El carrito no es válido."), 400
    if not cantidades:
        return jsonify(error="Tu carrito está vacío."), 400

    conn = conectar()
    try:
        productos = {p["cod_producto"]: p for p in cargar_productos(conn)}
        if any(cod not in productos for cod in cantidades):
            return jsonify(error="Algún producto del carrito ya no está disponible."), 400

        total = sum(productos[cod]["precio"] * n for cod, n in cantidades.items())
        codigo = registrar_pedido(conn, session["n_cliente"], cantidades, metodo, direccion)
        return jsonify(ok=True, codigo=codigo, total=total)
    except mysql.connector.Error:
        app.logger.exception("Error al registrar el pedido")
        try:
            conn.rollback()
        except mysql.connector.Error:
            pass
        return jsonify(error="No pudimos registrar tu pedido. Intenta de nuevo en unos minutos."), 500
    finally:
        conn.close()


# BLOQUE ADMINISTRATIVO COMPLETO PARA singluten.py
# Sustituye TODO el bloque administrativo antiguo, desde ADMIN_USER = ...
# hasta las rutas /pedidos inclusive, por este archivo. No lo pegues además
# del bloque antiguo: se registrarían rutas duplicadas.
# Debe quedar ANTES del bloque final if __name__ == "__main__": app.run(...).

ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

def es_admin():
    return session.get("es_admin") is True

@app.post("/api/admin/login")
def admin_login():
    datos = request.get_json(silent=True) or {}
    usuario = str(datos.get("usuario", ""))
    contrasena = str(datos.get("contrasena", ""))
    if not ADMIN_USER or not ADMIN_PASSWORD:
        return jsonify(error="El administrador no está configurado."), 503
    if not (hmac.compare_digest(usuario, ADMIN_USER) and hmac.compare_digest(contrasena, ADMIN_PASSWORD)):
        return jsonify(error="Usuario o contraseña incorrectos."), 401
    session.clear()
    session["es_admin"] = True
    return jsonify(ok=True)

@app.post("/api/admin/logout")
def admin_logout():
    if es_admin():
        session.clear()
    return jsonify(ok=True)

@app.get("/admin/pedidos")
def pagina_pedidos():
    return render_template("pedidos.html")

@app.get("/pedidos")
def pagina_pedidos_alias():
    return render_template("pedidos.html")

# Pegar estas rutas en singluten.py después de definir ADMIN_USER,
# ADMIN_PASSWORD y es_admin(), y antes del bloque if __name__ == '__main__'.

from functools import wraps


def admin_requerido(func):
    @wraps(func)
    def envoltura(*args, **kwargs):
        if not es_admin():
            return jsonify(error="Acceso exclusivo para administradores."), 401
        return func(*args, **kwargs)
    return envoltura


@app.get("/api/admin/usuarios")
@admin_requerido
def api_admin_usuarios():
    conn = conectar()
    try:
        cur = conn.cursor(dictionary=True)
        # Nunca se devuelve la columna contrasena ni su hash.
        cur.execute("""
            SELECT n_cliente, nombre, apellido, direccion, telefono, ruc, activo
            FROM clientes ORDER BY n_cliente DESC
        """)
        return jsonify(usuarios=cur.fetchall())
    except mysql.connector.Error:
        app.logger.exception("Error al consultar usuarios")
        return jsonify(error="No se pudieron cargar los usuarios."), 500
    finally:
        conn.close()



@app.get("/api/admin/usuarios/<int:n_cliente>/compras")
@admin_requerido
def api_admin_compras_cliente(n_cliente):
    conn = conectar()
    try:
        cur = conn.cursor(dictionary=True)

        cur.execute("""
            SELECT
                v.codigo AS n_pedido,
                MAX(v.fecha_pedido) AS fecha,
                v.metodo_pago,
                v.direccion_entrega,
                SUM(
                    COALESCE(v.u_vendidas, 0) *
                    COALESCE(pr.precio, 0)
                ) AS total,
                GROUP_CONCAT(
                    CONCAT(
                        pr.nombre,
                        ' × ',
                        COALESCE(v.u_vendidas, 0)
                    )
                    ORDER BY pr.nombre SEPARATOR ', '
                ) AS productos
            FROM ventas v
            LEFT JOIN productos pr
                ON pr.cod_producto = v.id_product
            WHERE v.id_comprador = %s
            GROUP BY
                v.codigo,
                v.id_comprador,
                v.metodo_pago,
                v.direccion_entrega
            ORDER BY MAX(v.fecha_pedido) DESC
        """, (n_cliente,))

        compras = cur.fetchall()

        for compra in compras:
            if isinstance(compra.get("fecha"), (datetime, date)):
                compra["fecha"] = compra["fecha"].isoformat(sep=" ")
            compra["total"] = float(compra["total"] or 0)

        return jsonify(compras=compras)

    except mysql.connector.Error:
        app.logger.exception("Error al consultar historial del cliente")
        return jsonify(
            error="No se pudo cargar el historial de compras."
        ), 500

    finally:
        conn.close()

@app.put("/api/admin/usuarios/<int:n_cliente>")
@admin_requerido
def api_admin_editar_usuario(n_cliente):
    d = request.get_json(silent=True) or {}
    campos = {k: str(d.get(k, "")).strip() for k in
              ("nombre", "apellido", "direccion", "telefono", "ruc")}
    if not campos["nombre"] or not campos["apellido"] or not campos["telefono"]:
        return jsonify(error="Nombre, apellido y teléfono son obligatorios."), 400
    if len(campos["nombre"]) > 100 or len(campos["apellido"]) > 100:
        return jsonify(error="Nombre o apellido demasiado largo."), 400
    if len(campos["direccion"]) > 150 or len(campos["ruc"]) > 15:
        return jsonify(error="La dirección o el RUC supera la longitud permitida."), 400
    if not re.fullmatch(r"0\d{9}", campos["telefono"], re.ASCII):
        return jsonify(error="El teléfono debe tener 10 dígitos y empezar por 0."), 400

    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE clientes
            SET nombre=%s, apellido=%s, direccion=%s, telefono=%s, ruc=%s
            WHERE n_cliente=%s
        """, (campos["nombre"], campos["apellido"], campos["direccion"] or None,
              campos["telefono"], campos["ruc"] or None, n_cliente))
        if cur.rowcount == 0:
            cur.execute("SELECT 1 FROM clientes WHERE n_cliente=%s", (n_cliente,))
            if not cur.fetchone():
                return jsonify(error="El cliente no existe."), 404
        return jsonify(ok=True)
    except mysql.connector.IntegrityError:
        return jsonify(error="Ya existe una cuenta con ese teléfono."), 409
    except mysql.connector.Error:
        app.logger.exception("Error al editar cliente")
        return jsonify(error="No se pudieron guardar los cambios."), 500
    finally:
        conn.close()


@app.patch("/api/admin/usuarios/<int:n_cliente>/estado")
@admin_requerido
def api_admin_estado_usuario(n_cliente):
    d = request.get_json(silent=True) or {}
    activo = d.get("activo")
    if activo not in (True, False, 0, 1):
        return jsonify(error="Estado no válido."), 400
    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE clientes SET activo=%s WHERE n_cliente=%s",
                    (1 if activo else 0, n_cliente))
        if cur.rowcount == 0:
            cur.execute("SELECT 1 FROM clientes WHERE n_cliente=%s", (n_cliente,))
            if not cur.fetchone():
                return jsonify(error="El cliente no existe."), 404
        return jsonify(ok=True, activo=bool(activo))
    except mysql.connector.Error:
        app.logger.exception("Error al cambiar estado del cliente")
        return jsonify(error="No se pudo cambiar el estado de la cuenta."), 500
    finally:
        conn.close()


@app.delete("/api/admin/usuarios/<int:n_cliente>")
@admin_requerido
def api_admin_eliminar_usuario(n_cliente):
    # Eliminación definitiva: elimina también el historial de compras del cliente.
    # La interfaz debe pedir confirmación explícita antes de llamar a esta ruta.
    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute("SELECT n_pedido FROM pedidos WHERE id_comprador=%s", (n_cliente,))
        pedidos_cliente = [fila[0] for fila in cur.fetchall()]
        if pedidos_cliente:
            marcas = ",".join(["%s"] * len(pedidos_cliente))
            cur.execute(f"DELETE FROM ventas WHERE n_pedido IN ({marcas})", tuple(pedidos_cliente))
            cur.execute(f"DELETE FROM pedidos WHERE n_pedido IN ({marcas})", tuple(pedidos_cliente))
        cur.execute("DELETE FROM clientes WHERE n_cliente=%s", (n_cliente,))
        if cur.rowcount == 0:
            conn.rollback()
            return jsonify(error="El cliente no existe."), 404
        conn.commit()
        return jsonify(ok=True)
    except mysql.connector.Error:
        conn.rollback()
        app.logger.exception("Error al eliminar cliente")
        return jsonify(error="No se pudo eliminar la cuenta."), 500
    finally:
        conn.close()

@app.get("/api/admin/pedidos")
@admin_requerido
def api_admin_pedidos():
    conn = conectar()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT
                v.codigo AS id_pedido,
                MAX(v.fecha_pedido) AS fecha_pedido,
                v.id_comprador AS id_cliente,
                c.nombre AS nombre_cliente,
                c.apellido AS apellido_cliente,
                v.direccion_entrega AS direccion,
                v.metodo_pago AS metodos_pago,
                SUM(
                    COALESCE(v.u_vendidas, 0) *
                    COALESCE(pr.precio, 0)
                ) AS total,
                GROUP_CONCAT(
                    DISTINCT pr.nombre
                    ORDER BY pr.nombre SEPARATOR ', '
                ) AS productos,
                GROUP_CONCAT(
                    DISTINCT pr.categoria
                    ORDER BY pr.categoria SEPARATOR ', '
                ) AS categorias
            FROM ventas v
            LEFT JOIN clientes c
                ON c.n_cliente = v.id_comprador
            LEFT JOIN productos pr
                ON pr.cod_producto = v.id_product
            GROUP BY
                v.codigo,
                v.id_comprador,
                c.nombre,
                c.apellido,
                v.direccion_entrega,
                v.metodo_pago
            ORDER BY MAX(v.fecha_pedido) DESC
        """)

        pedidos = cur.fetchall()

        for p in pedidos:
            if isinstance(p.get("fecha_pedido"), (datetime, date)):
                p["fecha_pedido"] = p["fecha_pedido"].isoformat(sep=" ")
            p["total"] = float(p["total"] or 0)

        return jsonify(pedidos=pedidos)

    except mysql.connector.Error:
        app.logger.exception("Error al consultar ventas")
        return jsonify(error="No se pudieron cargar los pedidos."), 500

    finally:
        conn.close()

@app.get("/api/admin/productos")
@admin_requerido
def api_admin_productos():
    conn = conectar()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT cod_producto, descripcion, nombre, precio, categoria, costo,
                fecha, id_proveedor, activo, imagen
            FROM productos
            ORDER BY cod_producto DESC
        """)
        productos = cur.fetchall()
        for p in productos:
            p["precio"] = float(p["precio"] or 0)
            p["costo"] = float(p["costo"] or 0)
            if isinstance(p.get("fecha"), (datetime, date)):
                p["fecha"] = p["fecha"].isoformat()
        return jsonify(productos=productos)
    except mysql.connector.Error:
        app.logger.exception("Error al consultar productos")
        return jsonify(error="No se pudieron cargar los productos."), 500
    finally:
        conn.close()


def validar_producto(d):
    try:
        nombre = str(d.get("nombre", "")).strip()
        descripcion = str(d.get("descripcion", "")).strip()
        categoria = str(d.get("categoria", "")).strip()
        precio = float(d.get("precio"))
        costo = float(d.get("costo", 0))
        id_proveedor = int(d.get("id_proveedor", 1))
        fecha = str(d.get("fecha") or date.today().isoformat())
        datetime.strptime(fecha, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None, "Precio, costo, proveedor o fecha no válidos."
    if not nombre or not descripcion or not categoria:
        return None, "Nombre, descripción y categoría son obligatorios."
    if len(nombre) > 150 or len(descripcion) > 150 or len(categoria) > 50:
        return None, "Uno de los campos de texto supera la longitud permitida."
    if precio < 0 or costo < 0 or id_proveedor < 1:
        return None, "Precio, costo y proveedor deben ser valores válidos."
    return {"nombre": nombre, "descripcion": descripcion, "categoria": categoria,
            "precio": precio, "costo": costo, "fecha": fecha,
            "id_proveedor": id_proveedor}, None


@app.post("/api/admin/productos")
@admin_requerido
def api_admin_crear_producto():
    d, error = validar_producto(request.get_json(silent=True) or {})
    if error:
        return jsonify(error=error), 400
    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO productos (descripcion, nombre, precio, categoria, costo, fecha, id_proveedor, activo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
        """, (d["descripcion"], d["nombre"], d["precio"], d["categoria"],
              d["costo"], d["fecha"], d["id_proveedor"]))
        return jsonify(ok=True, cod_producto=cur.lastrowid), 201
    except mysql.connector.IntegrityError:
        return jsonify(error="El proveedor indicado no existe."), 400
    except mysql.connector.Error:
        app.logger.exception("Error al crear producto")
        return jsonify(error="No se pudo crear el producto."), 500
    finally:
        conn.close()


@app.put("/api/admin/productos/<int:cod_producto>")
@admin_requerido
def api_admin_editar_producto(cod_producto):
    d, error = validar_producto(request.get_json(silent=True) or {})
    if error:
        return jsonify(error=error), 400
    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE productos SET descripcion=%s, nombre=%s, precio=%s, categoria=%s,
                costo=%s, fecha=%s, id_proveedor=%s WHERE cod_producto=%s
        """, (d["descripcion"], d["nombre"], d["precio"], d["categoria"],
              d["costo"], d["fecha"], d["id_proveedor"], cod_producto))
        if cur.rowcount == 0:
            cur.execute("SELECT 1 FROM productos WHERE cod_producto=%s", (cod_producto,))
            if not cur.fetchone():
                return jsonify(error="El producto no existe."), 404
        return jsonify(ok=True)
    except mysql.connector.IntegrityError:
        return jsonify(error="El proveedor indicado no existe."), 400
    except mysql.connector.Error:
        app.logger.exception("Error al editar producto")
        return jsonify(error="No se pudo guardar el producto."), 500
    finally:
        conn.close()


@app.post("/api/admin/productos/<int:cod_producto>/imagen")
@admin_requerido
def api_admin_subir_imagen_producto(cod_producto):
    archivo = request.files.get("imagen")

    if not archivo or not archivo.filename:
        return jsonify(error="Selecciona una imagen."), 400

    ruta_relativa, error = guardar_imagen(archivo)

    if error:
        return jsonify(error=error), 400

    ruta_archivo = os.path.join(
        CARPETA_IMAGENES,
        os.path.basename(ruta_relativa)
    )

    conn = conectar()

    try:
        cur = conn.cursor(dictionary=True)

        cur.execute(
            "SELECT imagen FROM productos WHERE cod_producto=%s",
            (cod_producto,)
        )
        producto = cur.fetchone()

        if not producto:
            if os.path.exists(ruta_archivo):
                os.remove(ruta_archivo)

            return jsonify(error="El producto no existe."), 404

        imagen_anterior = producto.get("imagen")

        cur.execute(
            "UPDATE productos SET imagen=%s WHERE cod_producto=%s",
            (ruta_relativa, cod_producto)
        )

        conn.commit()

        # Eliminar la imagen anterior si era un archivo local
        # dentro de la carpeta de imágenes de productos.
        if imagen_anterior:
            nombre_anterior = os.path.basename(imagen_anterior)
            ruta_anterior = os.path.join(
                CARPETA_IMAGENES,
                nombre_anterior
            )

            if (
                os.path.isfile(ruta_anterior)
                and os.path.dirname(imagen_anterior).replace("\\", "/")
                    == "imagenes/productos"
                and nombre_anterior != os.path.basename(ruta_relativa)
            ):
                try:
                    os.remove(ruta_anterior)
                except OSError:
                    app.logger.warning(
                        "No se pudo eliminar la imagen anterior: %s",
                        ruta_anterior
                    )

        return jsonify(
            ok=True,
            imagen=url_for("static", filename=ruta_relativa)
        )

    except mysql.connector.Error:
        conn.rollback()

        if os.path.exists(ruta_archivo):
            os.remove(ruta_archivo)

        app.logger.exception(
            "Error al guardar la imagen del producto"
        )
        return jsonify(
            error="No se pudo guardar la imagen."
        ), 500

    finally:
        conn.close()
@app.patch("/api/admin/productos/<int:cod_producto>/estado")
@admin_requerido
def api_admin_estado_producto(cod_producto):
    d = request.get_json(silent=True) or {}
    activo = d.get("activo")
    if activo not in (True, False, 0, 1):
        return jsonify(error="Estado no válido."), 400
    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE productos SET activo=%s WHERE cod_producto=%s",
                    (1 if activo else 0, cod_producto))
        if cur.rowcount == 0:
            cur.execute("SELECT 1 FROM productos WHERE cod_producto=%s", (cod_producto,))
            if not cur.fetchone():
                return jsonify(error="El producto no existe."), 404
        return jsonify(ok=True, activo=bool(activo))
    except mysql.connector.Error:
        app.logger.exception("Error al cambiar estado del producto")
        return jsonify(error="No se pudo cambiar el estado del producto."), 500
    finally:
        conn.close()


@app.delete("/api/admin/productos/<int:cod_producto>")
@admin_requerido
def api_admin_eliminar_producto(cod_producto):
    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM ventas WHERE id_product=%s", (cod_producto,))
        if cur.fetchone()[0]:
            return jsonify(error="Este producto tiene ventas asociadas. Desactívalo para conservar el historial."), 409
        cur.execute("DELETE FROM productos WHERE cod_producto=%s", (cod_producto,))
        if cur.rowcount == 0:
            return jsonify(error="El producto no existe."), 404
        return jsonify(ok=True)
    except mysql.connector.Error:
        app.logger.exception("Error al eliminar producto")
        return jsonify(error="No se pudo eliminar el producto."), 500
    finally:
        conn.close()


@app.get("/api/admin/estadisticas")
@admin_requerido

def api_admin_estadisticas():
    desde = request.args.get("desde", "").strip()
    hasta = request.args.get("hasta", "").strip()

    try:
        if desde:
            datetime.strptime(desde, "%Y-%m-%d")
        if hasta:
            datetime.strptime(hasta, "%Y-%m-%d")
    except ValueError:
        return jsonify(error="Fechas no válidas."), 400

    if desde and hasta and desde > hasta:
        return jsonify(
            error="La fecha inicial no puede ser posterior a la final."
        ), 400

    condiciones = []
    parametros = []

    if desde:
        condiciones.append("DATE(v.fecha_pedido) >= %s")
        parametros.append(desde)

    if hasta:
        condiciones.append("DATE(v.fecha_pedido) <= %s")
        parametros.append(hasta)

    where = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""

    conn = conectar()

    try:
        cur = conn.cursor(dictionary=True)

        # Resumen general basado en las ventas registradas.
        cur.execute("""
            SELECT
                COUNT(DISTINCT v.codigo) AS pedidos,
                COALESCE(
                    SUM(
                        COALESCE(v.u_vendidas, 0) *
                        COALESCE(pr.precio, 0)
                    ), 0
                ) AS facturacion,
                COUNT(DISTINCT v.id_comprador) AS clientes
            FROM ventas v
            LEFT JOIN productos pr
                ON pr.cod_producto = v.id_product
        """ + where, tuple(parametros))

        resumen = cur.fetchone()
        resumen["pedidos"] = int(resumen["pedidos"] or 0)
        resumen["clientes"] = int(resumen["clientes"] or 0)
        resumen["facturacion"] = float(resumen["facturacion"] or 0)

        # Productos más vendidos.
        cur.execute("""
            SELECT
                pr.nombre,
                COALESCE(SUM(v.u_vendidas), 0) AS unidades,
                COALESCE(
                    SUM(
                        COALESCE(v.u_vendidas, 0) *
                        COALESCE(pr.precio, 0)
                    ), 0
                ) AS facturacion
            FROM ventas v
            JOIN productos pr
                ON pr.cod_producto = v.id_product
        """ + where + """
            GROUP BY pr.cod_producto, pr.nombre
            ORDER BY unidades DESC
            LIMIT 8
        """, tuple(parametros))

        mas_vendidos = cur.fetchall()

        for fila in mas_vendidos:
            fila["unidades"] = int(fila["unidades"] or 0)
            fila["facturacion"] = float(fila["facturacion"] or 0)

        # Ventas agrupadas por día.
        cur.execute("""
            SELECT
                DATE(v.fecha_pedido) AS dia,
                COUNT(DISTINCT v.codigo) AS pedidos,
                COALESCE(
                    SUM(
                        COALESCE(v.u_vendidas, 0) *
                        COALESCE(pr.precio, 0)
                    ), 0
                ) AS facturacion
            FROM ventas v
            LEFT JOIN productos pr
                ON pr.cod_producto = v.id_product
        """ + where + """
            GROUP BY DATE(v.fecha_pedido)
            ORDER BY dia DESC
            LIMIT 30
        """, tuple(parametros))

        por_dia = cur.fetchall()

        for fila in por_dia:
            fila["dia"] = fila["dia"].isoformat() if fila["dia"] else ""
            fila["pedidos"] = int(fila["pedidos"] or 0)
            fila["facturacion"] = float(fila["facturacion"] or 0)

        return jsonify(
            resumen=resumen,
            mas_vendidos=mas_vendidos,
            por_dia=por_dia
        )

    except mysql.connector.Error:
        app.logger.exception("Error al calcular estadísticas")
        return jsonify(
            error="No se pudieron cargar las estadísticas."
        ), 500

    finally:
        conn.close()


def pedidos():
    return render_template('pedidos.html')

if __name__ == "__main__":
    app.run(debug=True)