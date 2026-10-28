# Qenty

Plataforma de venta de cursos online de la academia de artes místicas Qenty.
Catálogo, registro de alumnos, cobro por Mercado Pago, aula con el video de
cada curso y panel de administración con ventas.

Flask + SQLAlchemy + Flask-Login, SQLite en desarrollo y Postgres en
producción. Las plantillas son Jinja2 con CSS y JavaScript propios.

## Correrlo en tu máquina

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Queda en http://127.0.0.1:5000. Al arrancar, si la base está vacía, se cargan
seis cursos de ejemplo.

Antes hay que copiar `.env.example` a `.env` y completarlo:

| Variable | Para qué sirve |
|---|---|
| `DATABASE_URL` | URL de la base. Vacía = SQLite en `instance/qenty.db`. |
| `SECRET_KEY` | Firma las cookies de sesión. Sin ella se genera una temporal y las sesiones se pierden en cada reinicio. |
| `ADMIN_EMAIL` | Usuario del panel. Se crea, o se actualiza, en cada arranque. |
| `ADMIN_PASSWORD` | Su contraseña. |
| `ADMIN_NOMBRE` | Nombre que muestra el panel. Opcional. |
| `MP_ACCESS_TOKEN` | Access token de Mercado Pago. Sin él, el catálogo funciona pero no se puede comprar. |

`.env` no se sube al repositorio.

## Desplegarlo en Render

El repositorio trae `render.yaml`, que crea el servicio web y la base Postgres
juntos: en Render, **New > Blueprint** y elegir este repositorio. Render pide
`ADMIN_EMAIL`, `ADMIN_PASSWORD` y `MP_ACCESS_TOKEN`; el resto lo completa solo.

Para configurarlo a mano en lugar del blueprint:

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Variables de entorno: las mismas de la tabla de arriba, con la `DATABASE_URL`
  interna del Postgres.

En el primer arranque se crean las tablas vacías. **Los datos del SQLite local
no se migran solos.**

## Cosas que conviene saber

- **No hay webhook de Mercado Pago.** El curso se habilita cuando la persona
  vuelve a la app después de pagar. Si cierra el navegador antes, el pago queda
  cobrado y el curso hay que habilitarlo a mano.
- **No hay migraciones.** `db.create_all()` crea las tablas que faltan, pero no
  modifica las que ya existen. Si cambiás una columna, hay que hacerlo a mano.
- **El aula es un video por curso.** No hay módulos ni progreso real: la barra
  del dashboard está fija.
