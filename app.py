import os
import sqlite3
import csv
from io import StringIO
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, Response
import pandas as pd
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, session, redirect, url_for

app = Flask(__name__)
# Carpeta donde se guardarán las fotos de evidencia
UPLOAD_FOLDER = 'static/evidencias'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
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

app = Flask(__name__)
app.secret_key = 'clave_secreta_taller_inventario'

# --- RUTA PRINCIPAL (Integrada con SQLite y Admin) ---
@app.route('/')
def inicio():
    # 1. Verificamos si es admin
    es_admin = session.get('es_admin', False)
    
    # 2. Consultamos la base de datos SQLite
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Máquinas LISTAS para renta (Solo las que están 'Disponible')
    cursor.execute("SELECT * FROM maquinas WHERE estado = 'Disponible'")
    maquinas = cursor.fetchall()
    
    # Máquinas INCOMPLETAS o en taller/mantenimiento (Para separarlas)
    cursor.execute("SELECT * FROM maquinas WHERE estado != 'Disponible'")
    maquinas_incompletas = cursor.fetchall()
    
    conn.close()
    
    # 3. Enviamos ambas listas al HTML
    return render_template(
        'inicio.html', 
        maquinas=maquinas, 
        maquinas_incompletas=maquinas_incompletas, 
        es_admin=es_admin
    )
# --- RUTAS DE ADMINISTRACIÓN ---
@app.route('/login_admin', methods=['POST'])
def login_admin():
    password = request.form.get('password')
    if password == "1234":  # Tu contraseña para entrar
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

# Módulos de piezas sueltas

@app.route('/piezas/tomar/<codigo>', methods=['POST'])
def tomar_pieza_suelta(codigo):
    tecnico = request.form.get('tecnico', 'Taller')
    motivo = request.form.get('motivo', 'Uso en taller / campo')
    try:
        cantidad_tomada = int(request.form.get('cantidad', 1))
    except (ValueError, TypeError):
        cantidad_tomada = 1

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Buscar la pieza por código o ID
    c.execute("SELECT id, nombre, COALESCE(stock, cantidad, 0) FROM piezas_sueltas WHERE codigo = ? OR id = ?", (codigo, codigo))
    pieza = c.fetchone()

    if pieza:
        pieza_id, nombre_pieza, stock_actual = pieza[0], pieza[1], pieza[2]

        if stock_actual >= cantidad_tomada:
            nuevo_stock = stock_actual - cantidad_tomada
            
            try:
                c.execute("UPDATE piezas_sueltas SET stock = ? WHERE id = ?", (nuevo_stock, pieza_id))
            except sqlite3.OperationalError:
                c.execute("UPDATE piezas_sueltas SET cantidad = ? WHERE id = ?", (nuevo_stock, pieza_id))

            fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            motivo_completo = f"{motivo} (Cantidad: {cantidad_tomada})"
            
            try:
                c.execute("""INSERT INTO historial 
                             (maquina_codigo, pieza_id, tecnico, motivo, estado_solicitud, fecha_registro)
                             VALUES (?, ?, ?, ?, 'Entregado', ?)""",
                          ('REPUESTO-SUELTO', pieza_id, tecnico, motivo_completo, fecha_actual))
            except sqlite3.OperationalError:
                c.execute("""INSERT INTO historial 
                             (maquina_codigo, pieza_id, tecnico, motivo, estado_solicitud, fecha)
                             VALUES (?, ?, ?, ?, 'Entregado', ?)""",
                          ('REPUESTO-SUELTO', pieza_id, tecnico, motivo_completo, fecha_actual))

            conn.commit()

    conn.close()
    return redirect('/piezas_sueltas')

@app.route('/maquina/rentar/<codigo>', methods=['POST'])
def rentar_maquina(codigo):
    destino = request.form.get('destino')
    tecnico = request.form.get('tecnico_cargo')

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # 1. Cambiamos el estado de la máquina
        cursor.execute("""
            UPDATE maquinas 
            SET estado = 'Rentada', destino = ?, tecnico_cargo = ? 
            WHERE codigo = ?
        """, (destino, tecnico, codigo))
        
        # 2. Guardamos la renta EN TU TABLA 'historial' EXISTENTE
        cursor.execute("""
            INSERT INTO historial (
                fecha_registro, 
                maquina_codigo, 
                tecnico, 
                motivo, 
                estado_solicitud
            )
            VALUES (
                DATETIME('now', 'localtime'), 
                ?, 
                ?, 
                ?, 
                'Rentada'
            )
        """, (codigo, tecnico, destino))

        conn.commit()
        conn.close()
        return redirect(url_for('inicio'))
    except Exception as e:
        return f"Error al procesar la renta de la máquina: {str(e)}", 500


@app.route("/enviar_solicitud", methods=["POST"])
@app.route("/extraer_pieza", methods=["POST"])
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


# Carpeta donde se guardarán las fotos de evidencia
UPLOAD_FOLDER = 'static/uploads'

@app.route('/devolver_pieza_suelta/<int:pieza_id>', methods=['POST'])
def devolver_pieza_suelta(pieza_id):
    sigue_sirviendo = request.form.get('sigue_sirviendo', 'si')
    try:
        cantidad_devuelta = int(request.form.get('cantidad', 1))
    except (ValueError, TypeError):
        cantidad_devuelta = 1

    # Procesar la foto opcional
    foto_nombre = None
    if 'foto' in request.files:
        file = request.files['foto']
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            foto_nombre = filename

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 1. Obtener datos de la pieza
    c.execute("SELECT * FROM piezas_sueltas WHERE id = ?", (pieza_id,))
    pieza = c.fetchone()

    if not pieza:
        conn.close()
        return "Pieza no encontrada", 404

    pieza_dict = dict(pieza)
    cantidad_actual = int(pieza_dict.get('cantidad') if pieza_dict.get('cantidad') is not None else pieza_dict.get('stock', 0))

    # 2. Si sigue sirviendo, sumamos al stock físico
    if sigue_sirviendo == 'si':
        nuevo_stock = cantidad_actual + cantidad_devuelta
        c.execute("UPDATE piezas_sueltas SET cantidad = ? WHERE id = ?", (nuevo_stock, pieza_id))
    
    # 3. Definir el texto del estado según tu elección
    if sigue_sirviendo == 'si':
        estado_texto = "Disponible (En Taller)"
    else:
        estado_texto = "Inservible / Dañado"

    nuevo_motivo = f"Devolución registrada. Cantidad: {cantidad_devuelta}"

    # 4. Actualizar el registro pendiente en el historial (para que sea una sola fila limpia)
    c.execute('''SELECT id FROM historial 
                 WHERE pieza_id = ? AND (estado_solicitud LIKE '%Retirada%' OR estado_solicitud LIKE '%Pendiente%')
                 ORDER BY id DESC LIMIT 1''', (pieza_id,))
    registro_previo = c.fetchone()

    if registro_previo:
        if foto_nombre:
            c.execute('''UPDATE historial 
                         SET motivo = ?, estado_solicitud = ?, accion = 'Completado', evidencia = ?
                         WHERE id = ?''', 
                      (nuevo_motivo, estado_texto, foto_nombre, registro_previo['id']))
        else:
            c.execute('''UPDATE historial 
                         SET motivo = ?, estado_solicitud = ?, accion = 'Completado'
                         WHERE id = ?''', 
                      (nuevo_motivo, estado_texto, registro_previo['id']))
    else:
        # Plan de respaldo si no encuentra la línea previa
        c.execute('''SELECT id FROM historial WHERE pieza_id = ? ORDER BY id DESC LIMIT 1''', (pieza_id,))
        ultimo_cualquiera = c.fetchone()
        if ultimo_cualquiera:
            if foto_nombre:
                c.execute('''UPDATE historial SET motivo = ?, estado_solicitud = ?, evidencia = ? WHERE id = ?''',
                          (nuevo_motivo, estado_texto, foto_nombre, ultimo_cualquiera['id']))
            else:
                c.execute('''UPDATE historial SET motivo = ?, estado_solicitud = ? WHERE id = ?''',
                          (nuevo_motivo, estado_texto, ultimo_cualquiera['id']))

    conn.commit()
    conn.close()

    return redirect(url_for('piezas_sueltas'))

@app.route('/usar_pieza_suelta/<int:pieza_id>', methods=['POST'])
def usar_pieza_suelta(pieza_id):
    tecnico = request.form.get('tecnico', 'Taller')
    motivo = request.form.get('motivo', 'Uso directo')
    maquina_destino = request.form.get('maquina_destino', 'Uso General')
    
    try:
        cantidad_tomada = int(request.form.get('cantidad', 1))
    except (ValueError, TypeError):
        cantidad_tomada = 1

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Buscamos la pieza por su ID exacto
    c.execute("SELECT * FROM piezas_sueltas WHERE id = ?", (pieza_id,))
    pieza = c.fetchone()

    if not pieza:
        conn.close()
        return "Pieza no encontrada", 404

    # Forzamos a usar siempre 'cantidad' (y si por alguna razón antigua existe 'stock', la tomamos como respaldo)
    pieza_dict = dict(pieza)
    cantidad_actual = int(pieza_dict.get('cantidad') if pieza_dict.get('cantidad') is not None else pieza_dict.get('stock', 0))

    if cantidad_actual < cantidad_tomada:
        conn.close()
        return "No hay suficiente stock disponible", 400

    nuevo_stock = cantidad_actual - cantidad_tomada

    # Actualizamos directamente la columna 'cantidad' en la base de datos
    c.execute("UPDATE piezas_sueltas SET cantidad = ? WHERE id = ?", (nuevo_stock, pieza_id))

    # Registramos en el historial
    nombre_hist = pieza_dict.get('nombre', 'Pieza')
    motivo_completo = f"{motivo} (Cantidad tomada: {cantidad_tomada})"
    c.execute('''INSERT INTO historial (maquina_codigo, pieza_id, pieza_nombre, tecnico, motivo, estado_solicitud)
                 VALUES (?, ?, ?, ?, ?, 'Uso Directo')''',
              (maquina_destino, pieza_id, nombre_hist, tecnico, motivo_completo))

    conn.commit()
    conn.close()

    return redirect(url_for('piezas_sueltas'))
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

        c.execute("SELECT * FROM historial ORDER BY id DESC")
        rows = c.fetchall()
        conn.close()

        registros = []
        for r in rows:
            reg = dict(r)
            
            # Mapeos de nombres de campos
            reg['fecha_registro'] = reg.get('fecha_registro') or reg.get('fecha_devuelto') or reg.get('fecha_regreso')
            reg['maquina'] = reg.get('maquina_codigo') or reg.get('maquina')
            reg['pieza'] = reg.get('pieza_nombre') or reg.get('pieza')
            
            # Normalización del estado
            estado_raw = str(reg.get('estado_solicitud', '')).lower()
            if 'devuel' in estado_raw or 'dispon' in estado_raw:
                reg['estado_solicitud'] = 'Disponible'
            else:
                reg['estado_solicitud'] = 'Retirada a Campo'
            
            # Formateo de la foto de evidencia
            foto = reg.get('foto_evidencia') or reg.get('foto_url')
            if foto and foto not in ['None', 'Sin foto', '']:
                nombre_archivo = foto.split('/')[-1].split('\\')[-1]
                reg['foto_evidencia'] = f"/static/evidencias/{nombre_archivo}"
                reg['foto_url'] = f"/static/evidencias/{nombre_archivo}"
            else:
                reg['foto_evidencia'] = None
                reg['foto_url'] = None

            registros.append(reg)

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
    file = request.files.get('archivo_excel') or request.files.get('archivo') or request.files.get('file')
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

        # =========================================================================
        # DETECCIÓN AUTOMÁTICA PARA EXCEL DE "PIEZAS SUELTAS / REPUESTOS"
        # =========================================================================
        if 'stock' in df.columns or 'cantidad' in df.columns or ('nombre' in df.columns and 'codigo' not in df.columns and 'Serie del equipo' not in df.columns):
            # 1. Creamos la tabla si no existe (usando 'cantidad' como columna estándar)
            c.execute("""CREATE TABLE IF NOT EXISTS piezas_sueltas (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            codigo TEXT,
                            nombre TEXT,
                            ubicacion TEXT,
                            cantidad INTEGER DEFAULT 1
                        )""")

            # 2. Verificar y agregar automáticamente las columnas que falten en SQLite
            c.execute("PRAGMA table_info(piezas_sueltas)")
            cols_existentes = [col[1] for col in c.fetchall()]

            columnas_necesarias = {
                'codigo': 'TEXT',
                'nombre': 'TEXT',
                'ubicacion': 'TEXT',
                'cantidad': 'INTEGER DEFAULT 1'
            }

            for col_nombre, col_tipo in columnas_necesarias.items():
                if col_nombre not in cols_existentes:
                    try:
                        c.execute(f"ALTER TABLE piezas_sueltas ADD COLUMN {col_nombre} {col_tipo}")
                    except Exception as ex:
                        print(f"Columna {col_nombre} ya existe o no requirió cambio: {ex}")

            # 3. Insertar registros del Excel leyendo los valores reales por fila
            for idx, row in df.iterrows():
                nombre = str(row.get('nombre', row.get('Nombre', row.get('Pieza', '')))).strip()
                if nombre and nombre.lower() != 'nan':
                    modelo = str(row.get('Modelo de procedencia', row.get('Modelo', ''))).strip()
                    ubicacion = str(row.get('ubicacion', row.get('Ubicación', 'Taller'))).strip()
                    
                    # Intentamos leer el código directamente del Excel si existe, sino creamos uno único por fila
                    codigo_excel = str(row.get('codigo', row.get('Codigo', row.get('ID', '')))).strip()
                    if codigo_excel and codigo_excel.lower() != 'nan':
                        cod_suelta = codigo_excel
                    else:
                        cod_suelta = f"PS-{idx + 1:04d}" # Genera PS-0001, PS-0002, etc. de forma única

                    # Buscamos el stock/cantidad real en el Excel de forma flexible
                    stock_val = 1
                    for col_stk in ['stock', 'Stock', 'cantidad', 'Cantidad', 'EXISTENCIA', 'existencia']:
                        if col_stk in df.columns:
                            try:
                                val_s = row.get(col_stk)
                                if pd.notna(val_s):
                                    stock_val = int(float(val_s))
                                    break
                            except (ValueError, TypeError):
                                pass

                    if modelo and modelo.lower() != 'nan':
                        nombre_completo = f"{nombre} ({modelo})"
                    else:
                        nombre_completo = nombre

                    if not ubicacion or ubicacion.lower() == 'nan':
                        ubicacion = 'Taller'

                    c.execute("""INSERT INTO piezas_sueltas (codigo, nombre, ubicacion, cantidad)
                                 VALUES (?, ?, ?, ?)""",
                              (cod_suelta, nombre_completo, ubicacion, stock_val))

            conn.commit()
            conn.close()
            return redirect(url_for('inicio'))

        # =========================================================================
        # CÓDIGO ORIGINAL: Carga de Máquinas y Desglose de Piezas
        # =========================================================================
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
                
                # --- DETECTOR AUTOMÁTICO DE ESTADO AL 100% ---
                es_completa = True
                for col_pieza in df.columns:
                    if col_pieza not in cols_ignorar:
                        val_pieza = str(row.get(col_pieza, '')).strip().lower()
                        if val_pieza and val_pieza != 'nan':
                            palabras_no = ['no', 'sin unidad', 'falta', '0', 'falta fijado', 'sin protector', 'sin']
                            if val_pieza in palabras_no or any(p in val_pieza for p in ['falta', 'sin', 'no ']):
                                es_completa = False
                                break

                # Si NO está completa, cambiamos su estado a 'Incompleto'
                if not es_completa and estado_maq == 'Disponible':
                    estado_maq = 'Incompleto'

                # Guardamos o actualizamos la máquina con su estado real
                c.execute('''INSERT INTO maquinas (codigo, marca, modelo, numero_serie, ubicacion, estado)
                             VALUES (?, ?, ?, ?, ?, ?)
                             ON CONFLICT(codigo) DO UPDATE SET
                                marca = excluded.marca,
                                modelo = excluded.modelo,
                                numero_serie = excluded.numero_serie,
                                ubicacion = excluded.ubicacion,
                                estado = excluded.estado''', 
                          (codigo_maq, marca_maq, modelo_maq, num_serie_maq, ubicacion_maq, estado_maq))
                
                # Guardamos el desglose de cada pieza en la tabla piezas
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
