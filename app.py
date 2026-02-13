from flask import Flask, render_template, request, g, abort, redirect
from pathlib import Path
import sqlite3

app = Flask(__name__)
DB_PATH = Path(__file__).resolve().parent / "data" / "catalogo.db"


def resolve_db_path():
    root_db = Path(__file__).resolve().parent / "catalogo.db"
    if root_db.exists():
        return root_db
    cwd_root_db = Path.cwd() / "catalogo.db"
    if cwd_root_db.exists():
        return cwd_root_db
    if DB_PATH.exists():
        return DB_PATH
    alt = Path.cwd() / "data" / "catalogo.db"
    if alt.exists():
        return alt
    static_db = Path(__file__).resolve().parent / "static" / "data" / "catalogo.db"
    if static_db.exists():
        return static_db
    return DB_PATH


def get_db():
    if "db" not in g:
        db_path = resolve_db_path().resolve()
        # immutable=1 avoids WAL/SHM write attempts on read-only runtimes (e.g. Vercel)
        db_uri = f"file:{db_path.as_posix()}?mode=ro&immutable=1"
        g.db = sqlite3.connect(db_uri, uri=True)
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
    if one:
        return rows[0] if rows else None
    return rows


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


@app.route("/aseo")
def aseo():
    try:
        if not resolve_db_path().exists():
            return render_template("aseo.html", db_missing=True, sections=[])
    except Exception:
        return render_template("aseo.html", db_missing=True, sections=[])

    try:
        rows = query_db(
            """
            SELECT
                prod.id AS producto_id,
                prod.nombre AS producto,
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
                LOWER(
                    prod.nombre || ' ' ||
                    COALESCE((
                        SELECT GROUP_CONCAT(pz.nombre || ' ' || COALESCE(pz.contenido, ''), ' ')
                        FROM presentacion pz
                        WHERE pz.producto_id = prod.id
                          AND pz.activo = 1
                    ), '') || ' ' ||
                    COALESCE((
                        SELECT GROUP_CONCAT(m.nombre, ' ')
                        FROM presentacion pz
                        JOIN marca m ON m.id = pz.marca_id
                        WHERE pz.producto_id = prod.id
                          AND pz.activo = 1
                    ), '')
                ) AS searchable
            FROM producto prod
            JOIN categoria cat ON cat.id = prod.categoria_id
            WHERE cat.slug = 'aseo'
              AND EXISTS (
                  SELECT 1
                  FROM presentacion pz
                  WHERE pz.producto_id = prod.id
                    AND pz.activo = 1
              )
            ORDER BY prod.nombre
            """
        )

        products = []
        for row in rows:
            nombre = (row["producto"] or "").lower()
            img = row["imagen"] or "/static/images/placeholder.svg"
            if "revita" in nombre or "revitacolor" in nombre:
                img = "/static/images/ariel-revita-thumb.jpg"
            elif "ariel" in nombre:
                img = "/static/images/ariel-thumb.jpg"
            elif "fab" in nombre and "fabuloso" not in nombre:
                img = "/static/images/fab-thumb.jpg"
            elif "3d" in nombre:
                img = "/static/images/3d-thumb.jpg"
            products.append(
                {
                    "producto_id": row["producto_id"],
                    "producto": row["producto"],
                    "imagen": img,
                    "precio_desde": row["precio_desde"],
                    "searchable": row["searchable"] or "",
                }
            )

        cfg = [
            ("detergentes", "Detergentes", ["detergente", "ariel", "fab", "3d"]),
            ("lava-lozas", "Lava lozas", ["lava loza", "lavaloza", "lavaplatos"]),
            ("limpidos", "Limpidos y pisos", ["limpido", "limpieza", "piso", "fabuloso", "desinfectante"]),
            ("jabones", "Jabones", ["jabon", "jabon en barra"]),
        ]

        sections = []
        used = set()
        for slug, title, keywords in cfg:
            items = []
            for p in products:
                if p["producto_id"] in used:
                    continue
                text = p["searchable"]
                if any(k in text for k in keywords):
                    items.append(p)
                    used.add(p["producto_id"])
            sections.append({"slug": slug, "title": title, "items": items})

        others = [p for p in products if p["producto_id"] not in used]
        if others:
            sections.append({"slug": "otros", "title": "Otros de aseo", "items": others})

        return render_template("aseo.html", db_missing=False, sections=sections)
    except sqlite3.Error:
        return render_template("aseo.html", db_missing=True, sections=[])


@app.route("/drogueria")
def drogueria_redirect():
    return redirect("/tienda?cat=drogueria")


@app.route("/ferreteria")
def ferreteria_redirect():
    return redirect("/tienda?cat=ferreteria")


@app.route("/papeleria")
def papeleria_redirect():
    return redirect("/tienda?cat=papeleria")


@app.route("/tienda")
def tienda():
    try:
        if not resolve_db_path().exists():
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
                variants_by_product={},
            )
    except Exception:
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
            variants_by_product={},
        )

    try:
        q = (request.args.get("q") or "").strip()
        cat = (request.args.get("cat") or "").strip()
        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        per_page = 16
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

        categorias = query_db("SELECT nombre, slug FROM categoria ORDER BY nombre")
        # Keep the catalog lightweight on mobile: variants are loaded in dedicated product pages.
        variants_by_product = {}

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
            variants_by_product=variants_by_product,
        )
    except sqlite3.Error:
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
            variants_by_product={},
        )


@app.route("/producto/<int:producto_id>")
def producto_marcas(producto_id):
    try:
        if not resolve_db_path().exists():
            abort(404)
    except Exception:
        abort(404)

    try:
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
    except sqlite3.Error:
        abort(404)
    if not producto:
        abort(404)

    try:
        presentaciones_rows = query_db(
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
    except sqlite3.Error:
        abort(404)
    presentaciones = [dict(row) for row in presentaciones_rows]
    precios_map = {}
    if presentaciones:
        ids = [p["presentacion_id"] for p in presentaciones]
        placeholders = ",".join(["?"] * len(ids))
        try:
            precios_rows = query_db(
                f"""
                SELECT presentacion_id, min_cantidad, precio
                FROM precio_escalonado
                WHERE presentacion_id IN ({placeholders})
                ORDER BY min_cantidad ASC
                """,
                ids,
            )
        except sqlite3.Error:
            precios_rows = []
        for row in precios_rows:
            precios_map.setdefault(row["presentacion_id"], []).append(
                {"min_cantidad": row["min_cantidad"], "precio": row["precio"]}
            )
    for p in presentaciones:
        p["precios"] = precios_map.get(p["presentacion_id"], [])

    return render_template(
        "producto_marcas.html",
        producto=producto,
        presentaciones=presentaciones,
    )


@app.route("/presentacion/<int:presentacion_id>")
def producto_detalle(presentacion_id):
    try:
        if not resolve_db_path().exists():
            abort(404)
    except Exception:
        abort(404)

    try:
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
    except sqlite3.Error:
        abort(404)
    if not item:
        abort(404)

    try:
        precios_rows = query_db(
            """
            SELECT min_cantidad, precio
            FROM precio_escalonado
            WHERE presentacion_id = ?
            ORDER BY min_cantidad ASC
            """,
            (presentacion_id,),
        )
    except sqlite3.Error:
        precios_rows = []
    precios = [dict(row) for row in precios_rows]

    try:
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
    except sqlite3.Error:
        relacionados = []

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
