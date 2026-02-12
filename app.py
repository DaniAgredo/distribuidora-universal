from flask import Flask, render_template, request, g, abort
from pathlib import Path
import sqlite3

app = Flask(__name__)
DB_PATH = Path(__file__).resolve().parent / "data" / "catalogo.db"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query_db(query, params=(), one=False):
    cur = get_db().execute(query, params)
    rows = cur.fetchall()
    cur.close()
    return rows[0] if one else rows


@app.template_filter("cop")
def format_cop(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return value
    return f"${value:,.0f}".replace(",", ".")


@app.route("/")
def inicio():
    return render_template("index.html")


@app.route("/conocenos")
def conocenos():
    return render_template("conocenos.html")


@app.route("/envios")
def envios():
    return render_template("envios.html")


@app.route("/devoluciones")
def devoluciones():
    return render_template("devoluciones.html")


@app.route("/pagos")
def pagos():
    return render_template("pagos.html")


@app.route("/cuenta")
def cuenta():
    return render_template("cuenta.html")


@app.route("/tienda")
def tienda():
    if not DB_PATH.exists():
        return render_template(
            "tienda.html",
            categorias=[],
            items=[],
            page=1,
            pages=1,
            q="",
            cat="",
            total=0,
            db_missing=True,
        )

    q = (request.args.get("q") or "").strip()
    cat = (request.args.get("cat") or "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 24
    offset = (page - 1) * per_page

    where = [
        "EXISTS (SELECT 1 FROM presentacion pz WHERE pz.producto_id = prod.id AND pz.activo = 1)"
    ]
    params = []
    if cat:
        where.append("cat.slug = ?")
        params.append(cat)
    if q:
        like = f"%{q}%"
        where.append(
            """
            (
                prod.nombre LIKE ?
                OR cat.nombre LIKE ?
                OR EXISTS (
                    SELECT 1
                    FROM presentacion pz
                    JOIN marca m ON m.id = pz.marca_id
                    WHERE pz.producto_id = prod.id
                      AND pz.activo = 1
                      AND (pz.nombre LIKE ? OR m.nombre LIKE ?)
                )
            )
            """
        )
        params.extend([like, like, like, like])

    where_sql = " AND ".join(where)

    total_row = query_db(
        f"""
        SELECT COUNT(*) as total
        FROM producto prod
        JOIN categoria cat ON cat.id = prod.categoria_id
        WHERE {where_sql}
        """,
        params,
        one=True,
    )
    total = total_row["total"] if total_row else 0
    pages = max(1, (total + per_page - 1) // per_page)
    if page > pages:
        page = pages
        offset = (page - 1) * per_page

    items = query_db(
        f"""
        SELECT
            prod.id AS producto_id,
            prod.nombre AS producto,
            cat.nombre AS categoria,
            cat.slug AS categoria_slug,
            (
                SELECT imagen
                FROM presentacion pz
                WHERE pz.producto_id = prod.id
                  AND pz.activo = 1
                  AND pz.imagen IS NOT NULL
                ORDER BY pz.id
                LIMIT 1
            ) AS imagen,
            (
                SELECT MIN(pe.precio)
                FROM presentacion pz
                JOIN precio_escalonado pe ON pe.presentacion_id = pz.id
                WHERE pz.producto_id = prod.id
                  AND pz.activo = 1
            ) AS precio_desde,
            (
                SELECT COUNT(DISTINCT pz.marca_id)
                FROM presentacion pz
                WHERE pz.producto_id = prod.id
                  AND pz.activo = 1
            ) AS marcas
        FROM producto prod
        JOIN categoria cat ON cat.id = prod.categoria_id
        WHERE {where_sql}
        ORDER BY prod.nombre
        LIMIT ? OFFSET ?
        """,
        params + [per_page, offset],
    )

    categorias = query_db(
        "SELECT nombre, slug FROM categoria ORDER BY nombre"
    )

    return render_template(
        "tienda.html",
        categorias=categorias,
        items=items,
        page=page,
        pages=pages,
        q=q,
        cat=cat,
        total=total,
        db_missing=False,
    )


@app.route("/producto/<int:producto_id>")
def producto_marcas(producto_id):
    if not DB_PATH.exists():
        abort(404)

    producto = query_db(
        """
        SELECT
            prod.id AS producto_id,
            prod.nombre AS producto,
            cat.nombre AS categoria,
            cat.slug AS categoria_slug
        FROM producto prod
        JOIN categoria cat ON cat.id = prod.categoria_id
        WHERE prod.id = ?
        """,
        (producto_id,),
        one=True,
    )
    if not producto:
        abort(404)

    presentaciones = query_db(
        """
        SELECT
            pz.id AS presentacion_id,
            marca.nombre AS marca,
            pz.nombre AS presentacion,
            pz.contenido AS contenido,
            pz.imagen AS imagen,
            (SELECT MIN(precio) FROM precio_escalonado pe WHERE pe.presentacion_id = pz.id) AS precio_desde
        FROM presentacion pz
        JOIN marca ON marca.id = pz.marca_id
        WHERE pz.producto_id = ? AND pz.activo = 1
        ORDER BY marca.nombre, pz.nombre
        """,
        (producto_id,),
    )

    return render_template(
        "producto_marcas.html",
        producto=producto,
        presentaciones=presentaciones,
    )


@app.route("/presentacion/<int:presentacion_id>")
def producto_detalle(presentacion_id):
    if not DB_PATH.exists():
        abort(404)

    item = query_db(
        """
        SELECT
            pz.id AS presentacion_id,
            prod.nombre AS producto,
            prod.id AS producto_id,
            marca.nombre AS marca,
            cat.nombre AS categoria,
            cat.slug AS categoria_slug,
            pz.nombre AS presentacion,
            pz.contenido AS contenido,
            pz.imagen AS imagen
        FROM presentacion pz
        JOIN producto prod ON prod.id = pz.producto_id
        JOIN marca ON marca.id = pz.marca_id
        JOIN categoria cat ON cat.id = prod.categoria_id
        WHERE pz.id = ?
        """,
        (presentacion_id,),
        one=True,
    )
    if not item:
        abort(404)

    precios_rows = query_db(
        """
        SELECT min_cantidad, precio
        FROM precio_escalonado
        WHERE presentacion_id = ?
        ORDER BY min_cantidad ASC
        """,
        (presentacion_id,),
    )
    precios = [dict(row) for row in precios_rows]

    relacionados = query_db(
        """
        SELECT
            pz.id AS presentacion_id,
            prod.nombre AS producto,
            marca.nombre AS marca,
            pz.nombre AS presentacion,
            pz.contenido AS contenido,
            pz.imagen AS imagen,
            (SELECT MIN(precio) FROM precio_escalonado pe WHERE pe.presentacion_id = pz.id) AS precio_desde
        FROM presentacion pz
        JOIN producto prod ON prod.id = pz.producto_id
        JOIN marca ON marca.id = pz.marca_id
        WHERE pz.producto_id = ? AND pz.id != ?
        ORDER BY pz.nombre
        LIMIT 6
        """,
        (item["producto_id"], presentacion_id),
    )

    return render_template(
        "producto.html",
        item=item,
        precios=precios,
        relacionados=relacionados,
    )


@app.route("/carrito")
def carrito():
    return render_template("carrito.html")


if __name__ == "__main__":
    app.run(debug=True)
