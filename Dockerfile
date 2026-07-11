FROM python:3.13-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
RUN pip install --no-cache-dir --upgrade pip
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app/

# Run as an unprivileged user
RUN useradd --create-home --shell /usr/sbin/nologin ledgerhouse \
    && mkdir -p /app/staticfiles \
    && chown -R ledgerhouse:ledgerhouse /app
USER ledgerhouse

# Expose port
EXPOSE 8000

# Production default: gunicorn WSGI server.
# Local development (docker-compose.yml) overrides this with runserver.
CMD ["gunicorn", "ledgerhouse.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
