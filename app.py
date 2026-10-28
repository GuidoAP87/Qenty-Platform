from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.middleware.proxy_fix import ProxyFix # Para las URLs detras del proxy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps # Necesario para proteger las rutas de admin
import random
import os
import secrets # Para generar claves cuando no hay ninguna configurada
from datetime import datetime
from dotenv import load_dotenv # Para leer las claves secretas
import mercadopago # Para cobrar

# Cargar las claves del archivo .env
load_dotenv()

app = Flask(__name__)

# Detras del proxy del hosting, Flask ve http y el host interno. Sin esto,
# las back_urls que le pasamos a Mercado Pago salen en http y el pago no
# puede volver a la app. En local no cambia nada: sin proxy no hay cabeceras
# que leer.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# --- CONFIGURACIÓN ---
# La clave de sesion nunca va escrita en el codigo (el repo es publico).
# Si no esta en .env generamos una temporal: las sesiones se pierden al
# reiniciar, pero nadie puede falsificar cookies con una clave conocida.
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")
if not app.config['SECRET_KEY']:
    app.config['SECRET_KEY'] = secrets.token_hex(32)
    print("[AVISO] No hay SECRET_KEY en .env. Se genero una temporal.")


def url_de_base_de_datos():
    # La URL sale del entorno, asi la misma app corre con SQLite en tu maquina
    # y con Postgres en el servidor sin tocar una linea de codigo.
    url = os.getenv("DATABASE_URL")

    if not url:
        print("[AVISO] No hay DATABASE_URL: usando SQLite local.")
        return 'sqlite:///qenty.db'

    # Render y Heroku entregan la URL empezando con "postgres://", un prefijo
    # que SQLAlchemy 2 ya no reconoce. Hay que pasarlo a "postgresql://".
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url

app.config['SQLALCHEMY_DATABASE_URI'] = url_de_base_de_datos()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Las bases gestionadas cortan las conexiones ociosas. Con pool_pre_ping la
# conexion muerta se descarta y se reconecta, en vez de romper la consulta.
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True}

# Configuración de Mercado Pago
token_mp = os.getenv("MP_ACCESS_TOKEN")
# Verificamos si existe el token para evitar errores si el archivo .env está vacío
if token_mp:
    sdk = mercadopago.SDK(token_mp)
else:
    sdk = None # Definido igual, asi el resto del codigo puede preguntar por el
    print("[AVISO] No se encontró el Token de Mercado Pago en .env")

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- TABLAS DE LA BASE DE DATOS ---

# Tabla intermedia para saber qué usuario compró qué curso
compras = db.Table('compras',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    # AQUÍ ESTÁ EL CAMBIO QUE CAUSABA EL ERROR:
    is_admin = db.Column(db.Boolean, default=False) 
    cursos_adquiridos = db.relationship('Course', secondary=compras, backref=db.backref('estudiantes', lazy='dynamic'))

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    precio = db.Column(db.Integer)
    desc = db.Column(db.String(200))
    icono = db.Column(db.String(50))
    video_url = db.Column(db.String(200)) # ID del video de YouTube

class Payment(db.Model):
    # Cada pago aprobado de Mercado Pago queda registrado una sola vez.
    # El payment_id es unico: asi un mismo pago no puede usarse dos veces
    # para desbloquear cursos.
    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.String(50), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    monto = db.Column(db.Integer)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- DECORADOR DE SEGURIDAD (EL PORTERO DEL ADMIN) ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Si no está logueado o NO es admin, prohibir entrada
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403) # Error 403: Prohibido
        return f(*args, **kwargs)
    return decorated_function

# --- RUTAS PÚBLICAS ---

@app.route('/')
def home():
    frases = ["Lo que buscas te está buscando.", "La intuición es el susurro del alma.", "Confía en la magia."]
    mensaje = random.choice(frases)
    cursos = Course.query.limit(3).all()
    return render_template('index.html', mensaje=mensaje, items=cursos)

@app.route('/cursos')
def cursos():
    cursos = Course.query.all()
    return render_template('cursos.html', items=cursos)

# --- PANEL DE ADMINISTRACIÓN ---

@app.route('/admin', methods=['GET', 'POST'])
@login_required
@admin_required # Solo entra el admin
def admin_panel():
    if request.method == 'POST':
        # Agregar nuevo curso desde el formulario
        nombre = request.form.get('nombre')
        precio = request.form.get('precio')
        desc = request.form.get('desc')
        icono = request.form.get('icono')
        video_url = request.form.get('video_url')
        
        nuevo_curso = Course(nombre=nombre, precio=int(precio), desc=desc, icono=icono, video_url=video_url)
        db.session.add(nuevo_curso)
        db.session.commit()
        flash('¡Curso agregado exitosamente!')
        return redirect(url_for('admin_panel'))
    
    # 1. Mostrar lista de cursos para gestionar
    cursos = Course.query.all()
    
    # 2. Obtener a todos los alumnos (los que NO son admin)
    alumnos = User.query.filter_by(is_admin=False).all()
    
    # 3. Calcular los ingresos totales de forma automática
    ingresos_totales = sum([curso.precio for alumno in alumnos for curso in alumno.cursos_adquiridos])
    
    # Mandamos todo a la plantilla
    return render_template('admin.html', cursos=cursos, alumnos=alumnos, ingresos_totales=ingresos_totales)

@app.route('/admin/borrar/<int:id>')
@login_required
@admin_required
def borrar_curso(id):
    curso = Course.query.get_or_404(id)
    db.session.delete(curso)
    db.session.commit()
    flash('Curso eliminado.')
    return redirect(url_for('admin_panel'))

# NUEVA RUTA: EDITAR CURSO
@app.route('/admin/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_curso(id):
    # Buscamos el curso exacto que queremos editar
    curso = Course.query.get_or_404(id)
    
    if request.method == 'POST':
        # Actualizamos los datos con lo que venga del formulario
        curso.nombre = request.form.get('nombre')
        curso.precio = int(request.form.get('precio'))
        curso.desc = request.form.get('desc')
        curso.icono = request.form.get('icono')
        curso.video_url = request.form.get('video_url')
        
        db.session.commit() # Guardamos los cambios en la base de datos
        flash('¡Curso actualizado exitosamente!')
        return redirect(url_for('admin_panel'))
        
    # Si es GET, mostramos el formulario con los datos actuales
    return render_template('editar_curso.html', curso=curso)

# --- RUTAS DE PAGO (MERCADO PAGO) ---

@app.route('/comprar/<int:course_id>')
@login_required
def iniciar_compra(course_id):
    curso = Course.query.get_or_404(course_id)
    
    if curso in current_user.cursos_adquiridos:
        flash('¡Ya tienes este curso!')
        return redirect(url_for('mis_cursos'))

    if sdk is None:
        flash('Los pagos no están disponibles en este momento.')
        return redirect(url_for('cursos'))

    # CREAR PREFERENCIA DE PAGO
    preference_data = {
        "items": [
            {
                "title": curso.nombre,
                "quantity": 1,
                "unit_price": float(curso.precio),
                "currency_id": "ARS"
            }
        ],
        # Atamos el pago a esta persona y a este curso. Al volver verificamos
        # que el pago aprobado tenga exactamente esta referencia.
        "external_reference": f"{current_user.id}:{curso.id}",
        "back_urls": {
            "success": url_for('pago_exitoso', course_id=curso.id, _external=True),
            "failure": url_for('cursos', _external=True),
            "pending": url_for('cursos', _external=True)
        },
        "auto_return": "approved",
    }

    try:
        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]
        return redirect(preference["init_point"])
    except Exception as e:
        print(f">>> [ERROR] Error creando la preferencia de pago: {e}")
        flash("Error conectando con Mercado Pago. Verifica tus credenciales.")
        return redirect(url_for('cursos'))

@app.route('/pago-exitoso/<int:course_id>')
@login_required
def pago_exitoso(course_id):
    # Mercado Pago nos devuelve el navegador aca. Antes de entregar el curso
    # le preguntamos a su API si el pago existe y esta aprobado: sin eso
    # cualquiera escribe esta URL en el navegador y se lleva el curso gratis.
    curso = Course.query.get_or_404(course_id)

    if curso in current_user.cursos_adquiridos:
        return redirect(url_for('mis_cursos'))

    payment_id = request.args.get('payment_id') or request.args.get('collection_id')

    if not payment_id or sdk is None:
        flash('No pudimos confirmar el pago. Si ya pagaste, escribinos.')
        return redirect(url_for('cursos'))

    # Un mismo pago no puede desbloquear un curso dos veces
    if Payment.query.filter_by(payment_id=str(payment_id)).first():
        flash('Ese pago ya fue utilizado.')
        return redirect(url_for('mis_cursos'))

    try:
        pago = sdk.payment().get(payment_id)["response"]
    except Exception as e:
        print(f">>> [ERROR] Error consultando el pago {payment_id}: {e}")
        flash('No pudimos confirmar el pago con Mercado Pago. Intentá de nuevo.')
        return redirect(url_for('cursos'))

    # El pago tiene que estar aprobado Y ser de este usuario y de este curso
    referencia_esperada = f"{current_user.id}:{curso.id}"
    if pago.get('status') != 'approved' or pago.get('external_reference') != referencia_esperada:
        flash('El pago no figura como aprobado para este curso.')
        return redirect(url_for('cursos'))

    db.session.add(Payment(
        payment_id=str(payment_id),
        user_id=current_user.id,
        course_id=curso.id,
        monto=curso.precio
    ))
    current_user.cursos_adquiridos.append(curso)
    db.session.commit()
    flash(f'¡Pago recibido! Bienvenido a {curso.nombre}')

    return redirect(url_for('mis_cursos'))

# --- AULA Y DASHBOARD ---

@app.route('/aula/<int:course_id>')
@login_required
def aula(course_id):
    curso = Course.query.get_or_404(course_id)
    # El Admin siempre puede entrar a ver, aunque no compre
    if not current_user.is_admin and curso not in current_user.cursos_adquiridos:
        flash("Debes comprar este curso para acceder.")
        return redirect(url_for('cursos'))
    return render_template('aula.html', curso=curso)

@app.route('/mis-cursos')
@login_required
def mis_cursos():
    return render_template('dashboard.html', user=current_user)

# --- LOGIN Y REGISTRO ---

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        email = request.form.get('email')
        nombre = request.form.get('nombre')
        password = request.form.get('password')
        
        # Verificar si ya existe
        user = User.query.filter_by(email=email).first()
        if user:
            flash('El email ya está registrado.')
            return redirect(url_for('registro'))

        new_user = User(email=email, nombre=nombre, password=generate_password_hash(password, method='scrypt'))
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('mis_cursos'))
    return render_template('registro.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password, password):
            flash('Datos incorrectos.')
            return redirect(url_for('login'))
            
        login_user(user)
        # Si es admin, lo mandamos directo a su panel
        if user.is_admin:
            return redirect(url_for('admin_panel'))
        return redirect(url_for('mis_cursos'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

# --- INICIALIZADOR DE DATOS ---
def cargar_datos_iniciales():
    # 1. CREAR ADMIN (desde .env, nunca con una contraseña escrita en el codigo)
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")

    if admin_email and admin_password:
        admin = User.query.filter_by(email=admin_email).first()
        if admin:
            admin.password = generate_password_hash(admin_password, method='scrypt')
            admin.is_admin = True
            print(">>> [OK] Admin actualizado desde .env.")
        else:
            db.session.add(User(
                email=admin_email,
                nombre=os.getenv("ADMIN_NOMBRE", "Administrador Qenty"),
                password=generate_password_hash(admin_password, method='scrypt'),
                is_admin=True
            ))
            print(">>> [OK] Usuario Admin creado desde .env.")
    elif not User.query.filter_by(is_admin=True).first():
        print(">>> [AVISO] No hay ningun admin. Defini ADMIN_EMAIL y ADMIN_PASSWORD en .env.")

    # 1.b. El admin viejo de contraseña conocida sigue vivo en las bases ya
    # desplegadas aunque el codigo ya no lo cree: lo desactivamos.
    viejo = User.query.filter_by(email="admin@qenty.com").first()
    if viejo and viejo.email != admin_email and check_password_hash(viejo.password, "admin123"):
        viejo.is_admin = False
        viejo.password = generate_password_hash(secrets.token_urlsafe(32), method='scrypt')
        print(">>> [SEGURIDAD] Admin por defecto (admin@qenty.com) desactivado.")

    # 2. CREAR CURSOS (Si no hay ninguno)
    if Course.query.count() == 0:
        cursos_base = [
            Course(nombre='Tarot Evolutivo', precio=45000, desc='Arcanos Mayores y Menores con enfoque terapéutico.', icono='🔮', video_url='5qap5aO4i9A'),
            Course(nombre='Runas Nórdicas', precio=38000, desc='Sabiduría ancestral de los vikingos.', icono='ᛟ', video_url='gP767_zJ7C8'),
            Course(nombre='Velomancia', precio=30000, desc='Interpretación de la llama y restos de velas.', icono='🕯️', video_url='5qap5aO4i9A'),
            Course(nombre='Defensa Mágica', precio=42000, desc='Protección energética y limpieza.', icono='🛡️', video_url='gP767_zJ7C8'),
            Course(nombre='Chamanismo', precio=55000, desc='Viajes de tambor y animales de poder.', icono='🪶', video_url='5qap5aO4i9A'),
            Course(nombre='Oráculo Lenormand', precio=35000, desc='Lectura predictiva precisa.', icono='🃏', video_url='gP767_zJ7C8')
        ]
        db.session.add_all(cursos_base)
        print(">>> [OK] Cursos de prueba cargados.")

    db.session.commit()

with app.app_context():
    db.create_all()
    cargar_datos_iniciales()

if __name__ == '__main__':
    app.run(debug=True)