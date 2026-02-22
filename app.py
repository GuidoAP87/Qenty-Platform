from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps # Necesario para proteger las rutas de admin
import random
import os
from dotenv import load_dotenv # Para leer las claves secretas
import mercadopago # Para cobrar

# Cargar las claves del archivo .env
load_dotenv()

app = Flask(__name__)

# --- CONFIGURACIÓN ---
app.config['SECRET_KEY'] = 'clave_secreta_qenty_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///qenty.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuración de Mercado Pago
token_mp = os.getenv("MP_ACCESS_TOKEN")
# Verificamos si existe el token para evitar errores si el archivo .env está vacío
if token_mp:
    sdk = mercadopago.SDK(token_mp)
else:
    print("⚠️ ADVERTENCIA: No se encontró el Token de Mercado Pago en .env")

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
    except:
        flash("Error conectando con Mercado Pago. Verifica tus credenciales.")
        return redirect(url_for('cursos'))

@app.route('/pago-exitoso/<int:course_id>')
@login_required
def pago_exitoso(course_id):
    curso = Course.query.get_or_404(course_id)
    
    if curso not in current_user.cursos_adquiridos:
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
    # 1. CREAR ADMIN (Si no existe)
    admin_email = "admin@qenty.com"
    if not User.query.filter_by(email=admin_email).first():
        nuevo_admin = User(
            email=admin_email, 
            nombre="Administrador Qenty", 
            password=generate_password_hash("admin123", method='scrypt'),
            is_admin=True
        )
        db.session.add(nuevo_admin)
        print(">>> ✅ Usuario Admin creado.")

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
        print(">>> ✅ Cursos de prueba cargados.")

    db.session.commit()

with app.app_context():
    db.create_all()
    cargar_datos_iniciales()

if __name__ == '__main__':
    app.run(debug=True)