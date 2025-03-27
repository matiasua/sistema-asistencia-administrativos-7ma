import os
import io
from flask import Flask, request, jsonify, render_template, redirect, url_for, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_migrate import Migrate
from sqlalchemy import extract
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from openpyxl import Workbook
from weasyprint import HTML

app = Flask(__name__)

# Configuración de la base de datos usando la variable de entorno
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@db:5432/registrodb')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback_key')

db = SQLAlchemy(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Definición del modelo Registro
class Registro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    tipo_labor = db.Column(db.String(100), nullable=False)
    fecha_hora_ingreso = db.Column(db.DateTime, nullable=False)
    fecha_hora_salida = db.Column(db.DateTime, nullable=True)
    asistente_administrativo = db.Column(db.Boolean, default=False)
    viper_cuartel = db.Column(db.Boolean, default=False)
    aprobado = db.Column(db.Boolean, nullable=True)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default='ayudante')  # Puedes extender roles más adelante

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Crear la base de datos y las tablas
with app.app_context():
    db.create_all()

# Definir la ventana de emergencia (ejemplo)
HORA_INICIO_EMERGENCIA = datetime(2025, 3, 26, 8, 0, 0)
HORA_FIN_EMERGENCIA = datetime(2025, 3, 26, 18, 0, 0)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def check_asistencia(registro):
    """Verifica si el check-in se realizó dentro de la ventana de emergencia."""
    if HORA_INICIO_EMERGENCIA <= registro.fecha_hora_ingreso <= HORA_FIN_EMERGENCIA:
        return True
    return False

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Verificar si el usuario ya existe
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            # Redirigir con parámetro error=1
            return redirect(url_for('register', error=1))

        # Crear el usuario
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        # Redirigir con parámetro success=1
        return redirect(url_for('register', success=1))

    # GET: verificamos si hay parámetros success o error en la URL
    success = request.args.get('success')
    error = request.args.get('error')
    return render_template('register.html', success=success, error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            # Redirige con success=1
            return redirect(url_for('login', success=1))
        else:
            # Redirige con error=1
            return redirect(url_for('login', error=1))

    # GET: revisamos si hay success o error en la URL
    success = request.args.get('success')
    error = request.args.get('error')
    return render_template('login.html', success=success, error=error)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/registro', methods=['POST'])
def registrar():
    nombre = request.form.get('nombre')
    tipo_labor = request.form.get('tipo_labor')
    # Se espera formato 'YYYY-MM-DDTHH:MM' (tipo datetime-local)
    fecha_hora_ingreso = datetime.strptime(request.form.get('fecha_hora_ingreso'), '%Y-%m-%dT%H:%M')
    fecha_hora_salida_str = request.form.get('fecha_hora_salida')
    fecha_hora_salida = datetime.strptime(fecha_hora_salida_str, '%Y-%m-%dT%H:%M') if fecha_hora_salida_str else None

    # Recoger y convertir el valor del nuevo campo
    viper_value = request.form.get('viper_cuartel')
    viper_bool = True if viper_value == 'si' else False

    registro = Registro(
        nombre=nombre,
        tipo_labor=tipo_labor,
        fecha_hora_ingreso=fecha_hora_ingreso,
        fecha_hora_salida=fecha_hora_salida,
        asistente_administrativo=False,
        viper_cuartel=viper_bool
    )

    # Verificar si el registro entra en la ventana de emergencia
    registro.asistente_administrativo = check_asistencia(registro)

    db.session.add(registro)
    db.session.commit()

    return jsonify({"message": "Registro guardado", "registro_id": registro.id})

@app.route('/registros', methods=['GET'])
@login_required
def mostrar_registros():
    if current_user.role != 'ayudante':
        return "No tienes permiso para ver esta página.", 403

    name_filter = request.args.get('name', '')
    month_filter = request.args.get('month', '')
    page = request.args.get('page', 1, type=int)
    # Leer per_page desde la URL, con valor por defecto de 10
    per_page = request.args.get('per_page', 10, type=int)

    query = Registro.query

    if name_filter:
        query = query.filter(Registro.nombre.ilike(f"%{name_filter}%"))

    if month_filter != "":
        try:
            year_str, month_str = month_filter.split('-')
            year = int(year_str)
            month = int(month_str)
            from sqlalchemy import extract
            query = query.filter(extract('year', Registro.fecha_hora_ingreso) == year)
            query = query.filter(extract('month', Registro.fecha_hora_ingreso) == month)
        except ValueError:
            print("Error parseando el mes:", month_filter)

    # Ordena por ID ascendente
    query = query.order_by(Registro.id.asc())

    # Paginación con per_page dinámico
    paginated = query.paginate(page=page, per_page=per_page)

    return render_template(
        'registros.html',
        registros=paginated.items,
        page=page,
        total_pages=paginated.pages,
        name_filter=name_filter,
        month_filter=month_filter,
        per_page=per_page  # <-- Pasar per_page al template
    )

@app.route('/aprobar/<int:registro_id>', methods=['POST'])
@login_required
def aprobar_registro(registro_id):
    registro = Registro.query.get_or_404(registro_id)
    data = request.get_json()
    nuevo_estado = data.get('aprobado')  # None, True o False

    # Asigna directamente
    registro.aprobado = nuevo_estado
    db.session.commit()

    return jsonify({"success": True})

@app.route('/eliminar/<int:registro_id>', methods=['DELETE'])
@login_required
def eliminar_registro(registro_id):
    registro = Registro.query.get_or_404(registro_id)
    db.session.delete(registro)
    db.session.commit()
    return jsonify({"success": True})

@app.route('/export/excel', methods=['GET'])
def export_excel():
    registros = get_filtered_registros()

    wb = Workbook()
    ws = wb.active
    ws.title = "Asistencia"

    # Encabezados
    ws.append(["ID", "Nombre", "Tipo Labor", "Ingreso", "Salida", "Viper Cuartel", "Aprobado"])

    # Agregar datos
    for reg in registros:
        ws.append([
            reg.id,
            reg.nombre,
            reg.tipo_labor,
            reg.fecha_hora_ingreso.strftime("%Y-%m-%d %H:%M") if reg.fecha_hora_ingreso else "",
            reg.fecha_hora_salida.strftime("%Y-%m-%d %H:%M") if reg.fecha_hora_salida else "",
            "Sí" if reg.viper_cuartel else "No",
            "Sí" if reg.aprobado else "No"
        ])

    # Generar archivo en memoria usando BytesIO
    output = io.BytesIO()
    wb.save(output)
    excel_data = output.getvalue()

    response = make_response(excel_data)
    response.headers["Content-Disposition"] = "attachment; filename=asistencia.xlsx"
    response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return response

@app.route('/export/pdf', methods=['GET'])
def export_pdf():
    registros = get_filtered_registros()

    # Generar HTML de manera dinámica (o usar un template)
    html_content = """
    <html>
    <head>
      <meta charset="UTF-8"/>
      <style>
        h1 { text-align: center; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 8px; border: 1px solid #ccc; }
        th { background: #007bff; color: #fff; }
      </style>
    </head>
    <body>
      <h1>Listado de Asistencia</h1>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Nombre</th>
            <th>Tipo Labor</th>
            <th>Ingreso</th>
            <th>Salida</th>
            <th>Viper</th>
            <th>Aprobado</th>
          </tr>
        </thead>
        <tbody>
    """

    for reg in registros:
        html_content += f"""
        <tr>
          <td>{reg.id}</td>
          <td>{reg.nombre}</td>
          <td>{reg.tipo_labor}</td>
          <td>{reg.fecha_hora_ingreso or ''}</td>
          <td>{reg.fecha_hora_salida or ''}</td>
          <td>{"Sí" if reg.viper_cuartel else "No"}</td>
          <td>{"Sí" if reg.aprobado else "No"}</td>
        </tr>
        """

    html_content += """
        </tbody>
      </table>
    </body>
    </html>
    """

    pdf = HTML(string=html_content).write_pdf()

    response = make_response(pdf)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=asistencia.pdf"
    return response

def get_filtered_registros():
    name_filter = request.args.get('name', '')
    month_filter = request.args.get('month', '')

    query = Registro.query

    if name_filter:
        query = query.filter(Registro.nombre.ilike(f"%{name_filter}%"))

    if month_filter and "-" in month_filter:
        year_str, month_str = month_filter.split('-')
        try:
            year = int(year_str)
            month = int(month_str)
            query = query.filter(extract('year', Registro.fecha_hora_ingreso) == year)
            query = query.filter(extract('month', Registro.fecha_hora_ingreso) == month)
        except ValueError:
            pass

    # IMPORTANTE: especificar el orden
    query = query.order_by(Registro.id.asc())

    return query.all()

if __name__ == '__main__':
    # Ejecutar la aplicación en modo debug para desarrollo
    app.run(host='0.0.0.0', debug=True)
