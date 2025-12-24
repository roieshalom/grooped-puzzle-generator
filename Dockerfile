FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Clone grooped repo
RUN git clone https://github.com/roieshalom/grooped.git grooped || true

# Expose port (Fly.io uses 8080 by default)
EXPOSE 8080

# Set environment variables
ENV FLASK_HOST=0.0.0.0
ENV FLASK_PORT=8080
ENV PYTHONUNBUFFERED=1

CMD ["flask", "run", "--host=0.0.0.0", "--port=8080"]

