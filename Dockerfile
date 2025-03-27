FROM python:3.9-slim

# Instalar dependencias del sistema para weasyprint
RUN apt-get update && apt-get install -y \
  libpango-1.0-0 \
  libpangoft2-1.0-0 \
  libpangocairo-1.0-0 \
  libcairo2 \
  libjpeg62-turbo \
  libffi-dev \
  && rm -rf /var/lib/apt/lists/*

# Establecer el directorio de trabajo
WORKDIR /app

# Copiar el archivo de requerimientos e instalar las dependencias
COPY requirements.txt requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copiar el resto de la aplicación
COPY . .

# Copiar el script de espera y darle permisos de ejecución
#COPY wait-for-db.sh /wait-for-db.sh
#RUN chmod +x /wait-for-db.sh

# Exponer el puerto en el que correrá la aplicación
EXPOSE 5000

# Usar el script wait-for-db.sh para esperar a que la base de datos esté lista y luego iniciar la app
CMD ["python", "app/app.py"]
