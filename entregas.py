import os
import requests
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import psycopg2
from psycopg2.extras import RealDictCursor

# 1. CREAMOS LA APP PRIMERO
app = Flask(__name__)
app.secret_key = "una_clave_muy_secreta_y_larga_12345"

# 2. CONFIGURACIÓN DE LA BASE DE DATOS
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("Falta la variable DATABASE_URL en Render")
        
    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    return conn

def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entregas (
                id SERIAL PRIMARY KEY,
                direccion TEXT NOT NULL,
                destinatario TEXT,
                estado TEXT DEFAULT 'pendiente',
                latitud REAL,
                longitud REAL
            )
        ''')
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print("Error inicializando la base de datos:", e)

if DATABASE_URL:
    init_db()

# 3. LÓGICA DE LOGIN
CLAVE_SECRETA_APP = "Madariaga1015" 

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['password'] == CLAVE_SECRETA_APP:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return "Contraseña incorrecta. <a href='/login'>Volver a intentar</a>"
    
    return '''
        <body style="font-family: Arial; text-align: center; padding-top: 50px; background: #f4f4f4;">
            <h2>🔒 Acceso Restringido</h2>
            <form method="post">
                <input type="password" name="password" placeholder="Contraseña" style="padding: 10px; font-size: 16px; border-radius: 5px; border: 1px solid #ccc;">
                <button type="submit" style="padding: 10px 20px; font-size: 16px; background: #0056b3; color: white; border: none; border-radius: 5px; cursor: pointer;">Entrar</button>
            </form>
        </body>
    '''

@app.route("/logout")
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# 4. RUTAS DE LA APP
@app.route("/")
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template("entregas.html")

@app.route("/api/entregas", methods=["GET"])
def listar_entregas():
    if not session.get('logged_in'):
        return jsonify({"error": "No autorizado"}), 401
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM entregas WHERE estado = %s ORDER BY id ASC", ('pendiente',))
        entregas = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(entregas)
    except Exception as e:
        print("Error al listar:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/entregas", methods=["POST"])
def agregar_entrega():
    if not session.get('logged_in'):
        return jsonify({"error": "No autorizado"}), 401
    
    data = request.json
    direccion = data.get("direccion")
    
    lat, lon = obtener_coordenadas(direccion)
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO entregas (direccion, destinatario, latitud, longitud) 
            VALUES (%s, %s, %s, %s) RETURNING id
        ''', (direccion, data.get("destinatario"), lat, lon))
        
        nuevo_id = cursor.fetchone()['id']
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"mensaje": "Entrega agregada", "id": nuevo_id, "encontrado": lat is not None}), 201
    except Exception as e:
        print("Error al guardar:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/entregas/<int:id>/completar", methods=["PUT"])
def completar_entrega(id):
    if not session.get('logged_in'):
        return jsonify({"error": "No autorizado"}), 401
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE entregas SET estado = 'entregado' WHERE id = %s", (id,))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"mensaje": "Entrega completada"}), 200
    except Exception as e:
        print("Error al completar:", e)
        return jsonify({"error": str(e)}), 500

# 5. FUNCIÓN DE GEOCODIFICACIÓN (Al final, antes del main)
def obtener_coordenadas(direccion):
    url = "https://apis.datos.gob.ar/georef/api/direcciones"
    
    # CAMBIO 1: Localidad "Paso de los Libres"
    params_exacto = {
        "direccion": direccion,
        "provincia": "Corrientes",
        "localidad": "Paso de los Libres", 
        "max": 1
    }
    
    try:
        response = requests.get(url, params=params_exacto, timeout=5)
        data = response.json()
        
        if data.get("direcciones") and len(data["direcciones"]) > 0:
            ubicacion = data["direcciones"][0].get("ubicacion")
            if ubicacion:
                lat, lon = float(ubicacion["lat"]), float(ubicacion["lon"])
                # CAMBIO 2: Ajustar el rango geográfico para Paso de los Libres
                if -29.8 < lat < -29.6 and -57.2 < lon < -57.0:
                    return lat, lon
                
        # Intento 2: Si falló la altura exacta, buscar solo la calle
        calle = direccion.split()[0] 
        params_calle = {
            "direccion": calle,
            "provincia": "Corrientes",
            "localidad": "Paso de los Libres",
            "max": 1
        }
        response_calle = requests.get(url, params=params_calle, timeout=5)
        data_calle = response_calle.json()
        
        if data_calle.get("direcciones") and len(data_calle["direcciones"]) > 0:
            ubicacion_calle = data_calle["direcciones"][0].get("ubicacion")
            if ubicacion_calle:
                lat, lon = float(ubicacion_calle["lat"]), float(ubicacion_calle["lon"])
                if -29.8 < lat < -29.6 and -57.2 < lon < -57.0:
                    return lat, lon

    except Exception as e:
        print(f"Error consultando Georef para '{direccion}':", e)
    
    return None, None

if __name__ == "__main__":
    app.run(debug=True)