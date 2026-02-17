from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps # Para proteger rutas de admin
import random
import os
from dotenv import load_dotenv
import mercadopago

# Cargar claves
load_dotenv()

app = Flask(__name__)

# --- CONFIGURACIÓN ---
app.config['SECRET_KEY'] = 'clave_secreta_qenty_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///qenty.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Mercado Pago (Si no tienes el .env, esto dará error, asegúrate de tenerlo o comentar esto)
token_mp = os.getenv("MP_ACCESS_TOKEN")
if token_mp:
    sdk = mercadopago.SDK(token_mp)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- TABLAS ---
compras = db.Table('compras',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    # NUEVO: Campo para saber si es el jefe
    is_admin = db.Column(db.Boolean, default=False) 
    cursos_adquiridos = db.relationship('Course', secondary=compras, backref=db.backref('estudiantes', lazy='dynamic'))

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    precio = db.Column(db.Integer)
    desc = db.Column(db.String(200))
    icono = db.Column(db.String(50))
    video_url = db.Column(db.String(200)) # ID de YouTube

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- DECORADOR DE SEGURIDAD (El Portero) ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Si no está logueado o NO es admin, prohibir entrada (Error 403)
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
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

# --- PANEL DE ADMINISTRACIÓN (NUEVO) ---
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
    
    # Mostrar lista de cursos para gestionar
    cursos = Course.query.all()
    return render_template('admin.html', cursos=cursos)

@app.route('/admin/borrar/<int:id>')
@login_required
@admin_required
def borrar_curso(id):
    curso = Course.query.get_or_404(id)
    db.session.delete(curso)
    db.session.commit()
    flash('Curso eliminado.')
    return redirect(url_for('admin_panel'))

# --- RUTAS DE AULA Y PAGO ---
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

# (Aquí irían las rutas de Mercado Pago y Auth igual que antes...)
# Para resumir, mantén tus rutas de /login, /registro, /comprar igual que en el paso anterior.
# Solo asegúrate de que el login redirija al admin si es admin.

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            # Si es admin, lo mandamos directo a su panel
            if user.is_admin:
                return redirect(url_for('admin_panel'))
            return redirect(url_for('mis_cursos'))
    return render_template('login.html')

# (Agrega aquí /registro, /logout, /comprar igual que tenías antes)
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        user = User(email=request.form['email'], nombre=request.form['nombre'], password=generate_password_hash(request.form['password'], method='scrypt'))
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('mis_cursos'))
    return render_template('registro.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

# --- INICIALIZADOR CON ADMIN ---
def crear_admin():
    # Creamos un usuario admin por defecto si no existe
    admin_email = "admin@qenty.com"
    admin = User.query.filter_by(email=admin_email).first()
    if not admin:
        # CONTRASEÑA DEL ADMIN: "admin123" (Cámbiala después)
        nuevo_admin = User(
            email=admin_email, 
            nombre="Administrador Qenty", 
            password=generate_password_hash("admin123", method='scrypt'),
            is_admin=True # ¡El poder!
        )
        db.session.add(nuevo_admin)
        db.session.commit()
        print(">>> ¡Usuario Admin creado: admin@qenty.com / admin123!")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        crear_admin() # Ejecutamos la creación del admin
    app.run(debug=True)