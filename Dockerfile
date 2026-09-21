# Build stage
FROM python:3.10-slim as builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.10-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    openssl \
    libpq-dev \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# EGR omits its intermediate. The live leaf uses AlphaSSL CA 2025 (AIA).
# GlobalSign publishes DER; update-ca-certificates requires PEM. Validate the
# intermediate against the distribution roots before adding it to the bundle.
RUN curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    https://secure.globalsign.com/cacert/gsgccr6alphasslca2025.crt \
    -o /tmp/egr-intermediate.der \
    && openssl x509 -inform DER -in /tmp/egr-intermediate.der \
       -out /usr/local/share/ca-certificates/globalsign-gcc-r6-alphassl-ca-2025.crt \
    && openssl verify -CAfile /etc/ssl/certs/ca-certificates.crt \
       /usr/local/share/ca-certificates/globalsign-gcc-r6-alphassl-ca-2025.crt \
    && update-ca-certificates

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -m -d /home/appuser appuser

# Copy installed packages from builder to appuser home
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local

# Copy source code
COPY --chown=appuser:appuser . .

# Copy and set executable permissions for entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh \
    && chmod +x /usr/local/bin/docker-entrypoint.sh \
    && if [ -f /app/scripts/init/run_sql_and_monitoring.sh ]; then sed -i 's/\r$//' /app/scripts/init/run_sql_and_monitoring.sh && chmod +x /app/scripts/init/run_sql_and_monitoring.sh; fi

# Environment variables
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONPATH=/app:$PYTHONPATH
ENV PYTHONUNBUFFERED=1
# Системный bundle после update-ca-certificates (в т.ч. intermediate для egr.gov.by)
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Set entrypoint
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
