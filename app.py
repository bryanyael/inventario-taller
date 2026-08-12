import os
import sqlite3
import csv
from io import StringIO
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, Response
import pandas as pd
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configuración de ruta absoluta para la BD
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "inventario.db")

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Tabla de máquinas
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
    
    # Tabla de piezas asociadas a máquinas
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
    
    # NUEVA TABLA: Piezas sueltas / Stock general
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS piezas_sueltas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            modelos_compatibles TEXT,
            codigo_parte TEXT,
            cantidad INTEGER DEFAULT 1,
            ubicacion TEXT DEFAULT 'Taller',
            estado TEXT DEFAULT 'Nuevo'
        )
    ''')
    
    # Tabla de historial de movimientos
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
            foto_evidencia TEXT,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Garantizar columnas opcionales
    try:
        cursor.execute("ALTER TABLE maquinas ADD COLUMN destino TEXT;")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE maquinas ADD COLUMN tecnico_cargo TEXT;")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE historial ADD COLUMN foto_evidencia TEXT;")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

# Inicializar BD y carpetas
init_db()

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'evidencias')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# ==========================================
# RUTAS PÚBLICAS Y MÁQUINAS
# ==========================================

@app.route("/")
@app.route('/')
def inicio():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM maquinas")
    maquinas = cursor.fetchall()
    conn.close()
    return render_template('inicio.html', maquinas=maquinas)
from flask import Flask, render_template, request, session, redirect, url_for

app.secret_key = 'clave_secreta_taller'

from flask import Flask, render_template, request, session, redirect, url_for

app = Flask(__name__)
# ¡IMPORTANTE! Asegúrate de tener esta línea con una clave secreta para la sesión:
app.secret_key = 'clave_secreta_taller_inventario' 


# --- RUTA PRINCIPAL (Solo debe existir UNA vez) ---
@app.route('/')
def inicio():
    # Verificamos si la sesión actual tiene permisos de Admin
    es_admin = session.get('es_admin', False)
    # Reemplaza 'mis_maquinas' por la variable donde obtienes tus máquinas de la base de datos
    return render_template('inicio.html', maquinas=mis_maquinas, es_admin=es_admin)


# --- RUTAS DE ADMINISTRACIÓN ---
@app.route('/login_admin', methods=['POST'])
def login_admin():
    password = request.form.get('password')
    if password == "1234":  # Cambia "1234" por tu contraseña deseada
        session['es_admin'] = True
    return redirect(url_for('inicio'))

@app.route('/logout_admin')
def logout_admin():
    session.pop('es_admin', None)
    return redirect(url_for('inicio'))
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


@app.route('/maquina/rentar/<codigo>', methods=['POST'])
def rentar_maquina(codigo):
    destino = request.form.get('destino')
    tecnico = request.form.get('tecnico_cargo')

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""UPDATE maquinas 
                          SET estado = 'Rentada', destino = ?, tecnico_cargo = ? 
                          WHERE codigo = ?""", (destino, tecnico, codigo))
        conn.commit()
        conn.close()
        return redirect(url_for('inicio'))
    except Exception as e:
        return f"Error al procesar la renta de la máquina: {str(e)}", 500


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


@app.route('/devolver_pieza/<codigo>/<int:pieza_id>', methods=['POST'])
def devolver_pieza(codigo, pieza_id):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        ruta_foto_db = None

        if 'foto_evidencia' in request.files:
            foto = request.files['foto_evidencia']
            if foto and foto.filename != '':
                try:
                    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                    ext = os.path.splitext(foto.filename)[1]
                    nombre_foto = secure_filename(f"dev_{codigo}_{pieza_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}")
                    path_completo = os.path.join(app.config['UPLOAD_FOLDER'], nombre_foto)
                    foto.save(path_completo)
                    ruta_foto_db = f"evidencias/{nombre_foto}"
                except Exception as img_err:
                    print(f"Error al guardar imagen: {img_err}")

        c.execute("UPDATE piezas SET disponible = 1, estado = 'Disponible' WHERE id = ?", (pieza_id,))
        fecha_ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        c.execute("""UPDATE historial 
                     SET estado_solicitud = 'Devuelto', 
                         fecha_devuelto = ?, 
                         foto_evidencia = ? 
                     WHERE pieza_id = ? AND estado_solicitud = 'Pendiente'""", 
                  (fecha_ahora, ruta_foto_db, pieza_id))
        
        if c.rowcount == 0:
            c.execute("SELECT nombre FROM piezas WHERE id = ?", (pieza_id,))
            pz = c.fetchone()
            pz_nom = pz[0] if pz else "Pieza"
            c.execute("""INSERT INTO historial (maquina_codigo, pieza_id, pieza_nombre, tecnico, motivo, estado_solicitud, fecha_devuelto, foto_evidencia)
                         VALUES (?, ?, ?, ?, ?, 'Devuelto', ?, ?)""",
                      (codigo, pieza_id, pz_nom, 'Sistema/Taller', 'Devolución directa', fecha_ahora, ruta_foto_db))
        
        conn.commit()
        conn.close()

    except Exception as e:
        print(f"Error en devolución: {e}")
        return f"Error al procesar devolución: {str(e)}", 500

    return redirect(f"/maquina/{codigo}")


# ==========================================
# MODULO: PIEZAS SUELTAS / STOCK GENERAL
# ==========================================

@app.route('/piezas_sueltas')
def piezas_sueltas():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM piezas_sueltas ORDER BY id DESC")
    piezas = c.fetchall()
    conn.close()
    return render_template('piezas_sueltas.html', piezas=piezas)
@app.route('/piezas/tomar/<codigo_pieza>', methods=['POST'])
def tomar_pieza(codigo_pieza):
    cantidad_retirada = int(request.form.get('cantidad'))
    tecnico = request.form.get('tecnico')
    motivo = request.form.get('motivo')
    
    # 1. Descontar la cantidad en la base de datos
    # 2. Registrar el movimiento en el historial (Quién se la llevó y para qué)
    
    # Ejemplo con cursor de SQL:
    # cursor.execute("UPDATE piezas SET cantidad = cantidad - %s WHERE codigo = %s", (cantidad_retirada, codigo_pieza))
    # cursor.execute("INSERT INTO historial (tipo, pieza, tecnico, motivo, cantidad) VALUES ('SALIDA_PIEZA', %s, %s, %s, %s)", (codigo_pieza, tecnico, motivo, cantidad_retirada))
    
    return redirect('/piezas_sueltas')

@app.route('/admin/agregar_pieza_suelta', methods=['POST'])
def agregar_pieza_suelta():
    nombre = request.form.get('nombre')
    modelos = request.form.get('modelos_compatibles')
    codigo_parte = request.form.get('codigo_parte')
    cantidad = request.form.get('cantidad', 1)
    ubicacion = request.form.get('ubicacion', 'Taller')
    estado = request.form.get('estado', 'Nuevo')

    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('''INSERT INTO piezas_sueltas (nombre, modelos_compatibles, codigo_parte, cantidad, ubicacion, estado)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (nombre, modelos, codigo_parte, int(cantidad), ubicacion, estado))
        conn.commit()
        conn.close()
        return redirect(url_for('piezas_sueltas'))
    except Exception as e:
        return f"Error al agregar pieza suelta: {str(e)}", 500


@app.route('/usar_pieza_suelta/<int:pieza_id>', methods=['POST'])
def usar_pieza_suelta(pieza_id):
    tecnico = request.form.get('tecnico')
    motivo = request.form.get('motivo')
    maquina_destino = request.form.get('maquina_destino', 'Uso General')

    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute("SELECT * FROM piezas_sueltas WHERE id = ?", (pieza_id,))
        pieza = c.fetchone()

        if not pieza or pieza['cantidad'] <= 0:
            conn.close()
            return "Pieza no disponible o sin stock suficiente", 400

        # Descontar 1 unidad
        c.execute("UPDATE piezas_sueltas SET cantidad = cantidad - 1 WHERE id = ?", (pieza_id,))

        # Registrar en el historial
        nombre_historial = f"[Sueltas] {pieza['nombre']} ({pieza['codigo_parte'] or 'S/C'})"
        motivo_completo = f"{motivo} - Destino: {maquina_destino}"
        
        c.execute('''INSERT INTO historial (maquina_codigo, pieza_id, pieza_nombre, tecnico, motivo, estado_solicitud)
                     VALUES (?, ?, ?, ?, ?, 'Uso Directo')''',
                  (maquina_destino, pieza_id, nombre_historial, tecnico, motivo_completo))

        conn.commit()
        conn.close()

        return redirect(url_for('piezas_sueltas'))
    except Exception as e:
        return f"Error al usar pieza suelta: {str(e)}", 500


# ==========================================
# RUTAS DE ADMINISTRACIÓN Y HISTORIAL
# ==========================================

@app.route('/historial')
@app.route('/registros')
@app.route('/admin/registros')
def ver_historial():
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row  
        c = conn.cursor()

        c.execute("""SELECT id, 
                            fecha_registro AS fecha_registro,
                            maquina_codigo AS maquina, 
                            pieza_nombre AS pieza, 
                            tecnico, 
                            motivo, 
                            fecha_regreso AS regreso_est, 
                            estado_solicitud AS estado, 
                            fecha_devuelto AS devuelto_el, 
                            foto_evidencia AS foto_url,
                            foto_evidencia AS foto_evidencia
                     FROM historial 
                     ORDER BY id DESC""")
        registros = c.fetchall()
        conn.close()
        
        try:
            return render_template('historial.html', registros=registros, historial=registros)
        except:
            return render_template('registros.html', registros=registros, historial=registros)
            
    except Exception as e:
        print(f"Error al cargar historial: {e}")
        return f"Error al cargar el historial: {str(e)}", 500


@app.route('/admin/limpiar_bd', methods=['POST'])
def limpiar_bd():
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM piezas")
        c.execute("DELETE FROM maquinas")
        c.execute("DELETE FROM piezas_sueltas")
        c.execute("DELETE FROM historial")
        conn.commit()
        conn.close()
        return redirect(url_for('inicio'))
    except Exception as e:
        return f"Error al limpiar la base de datos: {str(e)}", 500


@app.route('/admin/cargar_excel', methods=['POST'])
def cargar_excel():
    file = request.files.get('archivo_excel')
    if not file or file.filename == '':
        return "No seleccionaste ningún archivo", 400

    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file, sheet_name=0)

        df.columns = [str(c).strip() for c in df.columns]

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        c.execute("PRAGMA table_info(piezas)")
        cols_bd = [col[1] for col in c.fetchall()]

        col_fk = 'maquina_codigo'
        if 'codigo_maquina' in cols_bd:
            col_fk = 'codigo_maquina'

        col_cod_pz = None
        for posible in ['codigo_pieza', 'codigo', 'cod_pieza']:
            if posible in cols_bd:
                col_cod_pz = posible
                break

        cols_ignorar = ['Serie del equipo', 'Modelo', 'Observaciones', 'Fecha', 'Técnico', 'Entregado por', 'Firma', 'RENTADA', 'codigo', 'marca', 'modelo', 'numero_serie', 'ubicacion', 'estado']

        for _, row in df.iterrows():
            codigo_maq = str(row.get('codigo', row.get('Serie del equipo', ''))).strip()
            marca_maq = str(row.get('marca', 'Kyocera')).strip()
            modelo_maq = str(row.get('modelo', row.get('Modelo', ''))).strip()
            num_serie_maq = str(row.get('numero_serie', row.get('Serie del equipo', ''))).strip()
            ubicacion_maq = str(row.get('ubicacion', row.get('Observaciones', 'Taller'))).strip()
            estado_maq = str(row.get('estado', 'Disponible')).strip()

            if not ubicacion_maq or ubicacion_maq.lower() == 'nan':
                ubicacion_maq = 'Taller'
            if not estado_maq or estado_maq.lower() == 'nan':
                estado_maq = 'Disponible'

            if codigo_maq and codigo_maq.lower() != 'nan':
                c.execute('''INSERT OR IGNORE INTO maquinas (codigo, marca, modelo, numero_serie, ubicacion, estado)
                             VALUES (?, ?, ?, ?, ?, ?)''', 
                          (codigo_maq, marca_maq, modelo_maq, num_serie_maq, ubicacion_maq, estado_maq))
                
                idx_pieza = 1
                for col_pieza in df.columns:
                    if col_pieza not in cols_ignorar:
                        val_pieza = str(row.get(col_pieza, '')).strip()
                        
                        if val_pieza and val_pieza.lower() != 'nan':
                            val_lower = val_pieza.lower().strip()
                            palabras_no = ['no', 'sin unidad', 'falta', '0', 'falta fijado', 'sin protector', 'sin']
                            
                            if val_lower in palabras_no or any(p in val_lower for p in ['falta', 'sin', 'no ']):
                                disponible = 0
                                estado_texto = "No hay existencia"
                            else:
                                disponible = 1
                                estado_texto = "Disponible"

                            nombre_pieza = col_pieza
                            cod_pieza = f"PZ-{codigo_maq}-{idx_pieza}"

                            if col_cod_pz:
                                query = f'''INSERT INTO piezas ({col_fk}, nombre, {col_cod_pz}, disponible, estado)
                                           VALUES (?, ?, ?, ?, ?)'''
                                c.execute(query, (codigo_maq, nombre_pieza, cod_pieza, disponible, estado_texto))
                            else:
                                query = f'''INSERT INTO piezas ({col_fk}, nombre, disponible, estado)
                                           VALUES (?, ?, ?, ?)'''
                                c.execute(query, (codigo_maq, nombre_pieza, disponible, estado_texto))

                            idx_pieza += 1

        conn.commit()
        conn.close()
        return redirect(url_for('inicio'))

    except Exception as e:
        return f"Error al procesar el Excel: {str(e)}", 500


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


@app.route('/admin/nueva_maquina', methods=['GET', 'POST'])
def nueva_maquina():
    if request.method == 'POST':
        codigo = request.form.get('codigo')
        marca = request.form.get('marca')
        modelo = request.form.get('modelo')
        numero_serie = request.form.get('numero_serie')
        ubicacion = request.form.get('ubicacion', 'Taller')
        estado = request.form.get('estado', 'Disponible')

        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO maquinas (codigo, marca, modelo, numero_serie, ubicacion, estado)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (codigo, marca, modelo, numero_serie, ubicacion, estado))
            conn.commit()
            conn.close()
            return redirect(url_for('inicio'))
            
        except sqlite3.IntegrityError:
            return "Error: El código de la máquina ya existe en la base de datos.", 400
        except Exception as e:
            return f"Error en el servidor al guardar la máquina: {str(e)}", 500

    return render_template('nueva_maquina.html')


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
