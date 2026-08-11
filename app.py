import os
import sqlite3
import csv
from io import StringIO
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, Response
import pandas as pd

app = Flask(__name__)

# Configuración de ruta absoluta para que Render encuentre la base de datos sin errores
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "inventario.db")

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS maquinas (
            codigo TEXT PRIMARY KEY,
            marca TEXT,
            modelo TEXT,
            numero_serie TEXT,
            ubicacion TEXT,
            estado TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS piezas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            maquina_codigo TEXT,
            nombre TEXT,
            codigo_pieza TEXT,
            estado TEXT,
            disponible INTEGER DEFAULT 1,
            FOREIGN KEY (maquina_codigo) REFERENCES maquinas (codigo)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            maquina_codigo TEXT,
            pieza_id INTEGER,
            pieza_nombre TEXT,
            tecnico TEXT,
            motivo TEXT,
            fecha_regreso TEXT,
            estado_solicitud TEXT DEFAULT 'Pendiente',
            fecha_devuelto TEXT,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

# Inicializamos la base de datos al arrancar
init_db()


# ==========================================
# RUTAS PÚBLICAS (TÉCNICOS)
# ==========================================

@app.route("/")
def inicio():
    return render_template("inicio.html")


@app.route("/maquina/<codigo>")
def maquina(codigo):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM maquinas WHERE codigo = ?", (codigo,))
    maq_data = cursor.fetchone()

    if not maq_data:
        conn.close()
        return "<h1>❌ Máquina no encontrada en el taller</h1>", 404

    maquina_info = {
        "marca": maq_data[1],
        "modelo": maq_data[2],
        "numero_serie": maq_data[3],
        "ubicacion": maq_data[4],
        "estado": maq_data[5]
    }

    cursor.execute("SELECT id, nombre, codigo_pieza, estado, disponible FROM piezas WHERE maquina_codigo = ?", (codigo,))
    piezas_raw = cursor.fetchall()
    
    piezas = []
    for p in piezas_raw:
        piezas.append({
            "id": p[0],
            "nombre": p[1],
            "codigo": p[2],
            "estado": p[3],
            "disponible": bool(p[4])
        })

    conn.close()
    return render_template("maquina.html", maquina=maquina_info, codigo=codigo, piezas=piezas)


@app.route("/solicitar/<codigo>/<int:pieza_id>")
def solicitar(codigo, pieza_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM maquinas WHERE codigo = ?", (codigo,))
    maq_data = cursor.fetchone()
    
    cursor.execute("SELECT id, nombre, codigo_pieza, disponible FROM piezas WHERE id = ?", (pieza_id,))
    pieza_data = cursor.fetchone()

    conn.close()

    if not maq_data or not pieza_data:
        return "<h1>❌ Recurso no encontrado</h1>", 404

    if not bool(pieza_data[3]):
        return f"""
        <div style="font-family: Arial; text-align: center; margin-top: 50px;">
            <h1 style="color: red;">❌ Pieza No Disponible</h1>
            <p>Esta pieza ya fue retirada previamente.</p>
            <br><a href="/maquina/{codigo}">← Volver a la máquina</a>
        </div>
        """, 400

    maquina_info = {"marca": maq_data[1], "modelo": maq_data[2]}
    pieza_info = {"id": pieza_data[0], "nombre": pieza_data[1], "codigo": pieza_data[2]}

    return render_template("solicitud.html", maquina=maquina_info, codigo=codigo, pieza=pieza_info)


@app.route("/enviar_solicitud", methods=["POST"])
def enviar_solicitud():
    codigo = request.form.get("codigo")
    pieza_id = request.form.get("pieza_id")
    tecnico = request.form.get("tecnico")
    motivo = request.form.get("motivo")
    fecha_regreso = request.form.get("fecha_regreso")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT nombre FROM piezas WHERE id = ?", (pieza_id,))
    res = cursor.fetchone()
    nombre_pieza = res[0] if res else "Pieza"

    nuevo_estado = f"Extraída por {tecnico} (Estimado: {fecha_regreso})"
    cursor.execute("UPDATE piezas SET disponible = 0, estado = ? WHERE id = ?", (nuevo_estado, pieza_id))

    cursor.execute('''
        INSERT INTO historial (maquina_codigo, pieza_id, pieza_nombre, tecnico, motivo, fecha_regreso, estado_solicitud)
        VALUES (?, ?, ?, ?, ?, ?, 'Pendiente')
    ''', (codigo, pieza_id, nombre_pieza, tecnico, motivo, fecha_regreso))

    conn.commit()
    conn.close()

    return f"""
    <div style="font-family: Arial; text-align: center; margin-top: 50px; padding: 20px;">
        <h1 style="color: #28a745;">✅ Pieza Retirada con Éxito</h1>
        <p>Se registró la extracción de la pieza en la máquina <strong>{codigo}</strong>.</p>
        <p><strong>Técnico:</strong> {tecnico}</p>
        <p><strong>Fecha estimada de rearmado:</strong> {fecha_regreso}</p>
        <br>
        <a href="/maquina/{codigo}" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">
            Volver a la Máquina
        </a>
    </div>
    """


@app.route("/devolver_pieza/<codigo>/<int:pieza_id>", methods=["POST"])
def devolver_pieza(codigo, pieza_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("UPDATE piezas SET disponible = 1, estado = 'Bueno' WHERE id = ?", (pieza_id,))

    fecha_actual = datetime.now().strftime("%d/%m/%Y %H:%M")
    cursor.execute('''
        UPDATE historial 
        SET estado_solicitud = 'Devuelto', fecha_devuelto = ? 
        WHERE id = (
            SELECT id FROM historial 
            WHERE pieza_id = ? 
            ORDER BY id DESC LIMIT 1
        )
    ''', (fecha_actual, pieza_id))

    conn.commit()
    conn.close()

    return redirect(url_for('maquina', codigo=codigo))
    import pandas as pd

@app.route('/admin/cargar_excel', methods=['POST'])
def cargar_excel():
    file = request.files.get('archivo_excel')
    if not file or file.filename == '':
        return "No seleccionaste ningún archivo", 400

    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        # Limpiar nombres de columnas
        df.columns = [str(c).strip() for c in df.columns]

        conn = sqlite3.connect('inventario.db')
        c = conn.cursor()

        insertados = 0
        for _, row in df.iterrows():
            # Obtener Serie y Modelo
            serie = str(row.get('SERIE DEL EQUIPO', '')).strip()
            modelo = str(row.get('MODELO', '')).strip()

            if serie and serie.lower() != 'nan':
                # 1. Registrar o actualizar la máquina
                c.execute('''INSERT OR IGNORE INTO maquinas (codigo, marca, modelo, numero_serie, ubicacion)
                             VALUES (?, ?, ?, ?, ?)''', (serie, 'Taller', modelo, serie, 'Taller'))
                
                # 2. Recorrer el resto de columnas como piezas
                columnas_piezas = [col for col in df.columns if col not in ['SERIE DEL EQUIPO', 'MODELO', 'Columna2']]
                
                for idx, col_pieza in enumerate(columnas_piezas):
                    val_pieza = str(row.get(col_pieza, '')).strip()
                    
                    # Si la celda tiene contenido o no está vacía
                    if val_pieza and val_pieza.lower() != 'nan':
                        nombre_final = f"{col_pieza} ({val_pieza})" if val_pieza.lower() not in ['si', 'x', '1', 'ok'] else col_pieza
                        cod_pieza = f"PZ-{serie}-{idx+1}"

                        c.execute('''INSERT INTO piezas (codigo_maquina, nombre, codigo, disponible, estado)
                                     VALUES (?, ?, ?, 1, 'Disponible')''', (serie, nombre_final, cod_pieza))
                
                insertados += 1

        conn.commit()
        conn.close()

        if insertados == 0:
            return "<h1>⚠️ El archivo no tenía filas con datos</h1><p>Asegúrate de llenar datos debajo de la fila de encabezados.</p><br><a href='/'>Volver</a>"

        return redirect(url_for('inicio'))

    except Exception as e:
        return f"Error al procesar el Excel: {str(e)}", 500


# ==========================================
# RUTAS DE ADMINISTRACIÓN
# ==========================================

@app.route("/admin/imprimir_qrs")
def imprimir_qrs():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT codigo, marca, modelo FROM maquinas")
    rows = cursor.fetchall()
    conn.close()

    maquinas_dict = {}
    qrs = {}
    for r in rows:
        cod = r[0]
        maquinas_dict[cod] = {"marca": r[1], "modelo": r[2]}
        url_maquina = request.host_url.rstrip('/') + url_for('maquina', codigo=cod)
        qrs[cod] = f"https://quickchart.io/qr?text={url_maquina}&size=250"

    return render_template("imprimir_qrs.html", maquinas=maquinas_dict, qrs=qrs)


@app.route("/admin/registros")
def ver_registros():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT maquina_codigo, pieza_nombre, tecnico, motivo, fecha_regreso, estado_solicitud, fecha_devuelto FROM historial ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    registros = []
    for r in rows:
        registros.append({
            "maquina": r[0],
            "pieza": r[1],
            "tecnico": r[2],
            "motivo": r[3],
            "fecha_regreso": r[4],
            "estado": r[5],
            "fecha_devuelto": r[6] if r[6] else "-"
        })

    return render_template("registros.html", registros=registros)


@app.route("/admin/exportar_excel")
def exportar_excel():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT maquina_codigo, pieza_nombre, tecnico, motivo, fecha_regreso, estado_solicitud, fecha_devuelto, fecha_registro FROM historial ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Maquina', 'Pieza', 'Tecnico', 'Motivo', 'Fecha Regreso Est.', 'Estado', 'Fecha Devuelto', 'Fecha Registro'])
    cw.writerows(rows)

    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=historial_taller.csv"}
    )


@app.route("/admin/nueva_maquina", methods=["GET", "POST"])
def nueva_maquina():
    if request.method == "POST":
        codigo = request.form.get("codigo")
        marca = request.form.get("marca")
        modelo = request.form.get("modelo")
        numero_serie = request.form.get("numero_serie")
        ubicacion = request.form.get("ubicacion")

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO maquinas VALUES (?, ?, ?, ?, ?, 'Para repuestos')", 
                           (codigo, marca, modelo, numero_serie, ubicacion))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        conn.close()
        return redirect(url_for('agregar_piezas', codigo=codigo))

    return render_template("nueva_maquina.html")


@app.route("/admin/agregar_piezas/<codigo>", methods=["GET", "POST"])
def agregar_piezas(codigo):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    if request.method == "POST":
        nombre = request.form.get("nombre")
        codigo_pieza = request.form.get("codigo_pieza")
        cursor.execute("INSERT INTO piezas (maquina_codigo, nombre, codigo_pieza, estado, disponible) VALUES (?, ?, ?, 'Bueno', 1)",
                       (codigo, nombre, codigo_pieza))
        conn.commit()

    cursor.execute("SELECT nombre, codigo_pieza FROM piezas WHERE maquina_codigo = ?", (codigo,))
    piezas = cursor.fetchall()
    conn.close()

    return render_template("agregar_piezas.html", codigo=codigo, piezas=piezas)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
