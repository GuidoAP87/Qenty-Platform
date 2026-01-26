from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import random

FRASES_ORACULO = [
    "Lo que buscas te está buscando a ti.",
    "La intuición es el susurro del alma.",
    "Donde pones tu atención, pones tu energía.",
    "El universo no habla inglés, habla frecuencia.",
    "Tus heridas son el lugar por donde entra la luz.",
    "Confía en la magia de los nuevos comienzos."
]

app = Flask(__name__)

# --- CONFIGURACIÓN ---
app.config['SECRET_KEY'] = 'clave_secreta_qenty_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///qenty.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- MODELO DE USUARIO ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- BASE DE DATOS DE CURSOS (Solo Cursos) ---
CURSOS_DISPONIBLES = [
    {'id': 1, 'nombre': 'Tarot Evolutivo', 'precio': 45000, 'desc': 'Aprende los Arcanos Mayores y Menores con enfoque terapéutico.'},
    {'id': 2, 'nombre': 'Runas Nórdicas y Egipcias', 'precio': 38000, 'desc': 'Conecta con la sabiduría ancestral de los vikingos y faraones.'},
    {'id': 3, 'nombre': 'Velomancia Aplicada', 'precio': 30000, 'desc': 'El arte de interpretar la llama y los restos de las velas.'},
    {'id': 4, 'nombre': 'Defensa Mágica', 'precio': 42000, 'desc': 'Técnicas para proteger tu energía y limpiar espacios.'},
    {'id': 5, 'nombre': 'Chamanismo Universal', 'precio': 55000, 'desc': 'Viajes de tambor, animales de poder y conexión natural.'},
    {'id': 6, 'nombre': 'Oráculo Lenormand', 'precio': 35000, 'desc': 'Lectura predictiva precisa con el mazo de 36 cartas.'}
]

# --- RUTAS PÚBLICAS ---

@app.route('/')
def home():
    # Elegimos una frase al azar para enviarla a la portada
    mensaje_dia = random.choice(FRASES_ORACULO)
    return render_template('index.html', mensaje=mensaje_dia)

# Nota: Hemos eliminado la ruta '/tienda'

@app.route('/cursos')
def cursos():
    # Ya no hace falta filtrar, todo lo que hay son cursos
    return render_template('cursos.html', items=CURSOS_DISPONIBLES)

# --- RUTAS DE AUTENTICACIÓN ---

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        email = request.form.get('email')
        nombre = request.form.get('nombre')
        password = request.form.get('password')

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
            flash('Email o contraseña incorrectos.')
            return redirect(url_for('login'))

        login_user(user)
        return redirect(url_for('mis_cursos'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

# --- RUTA PRIVADA (AULA VIRTUAL) ---
@app.route('/mis-cursos')
@login_required
def mis_cursos():
    # Aquí mostramos los cursos disponibles para el alumno
    return render_template('dashboard.html', user=current_user, cursos=CURSOS_DISPONIBLES)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)