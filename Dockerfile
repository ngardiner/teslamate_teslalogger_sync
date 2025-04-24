# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create a non-root user
RUN addgroup --system sync_group && \
    adduser --system --ingroup sync_group sync_user

# Change ownership of the application directory
RUN chown -R sync_user:sync_group /app

# Switch to non-root user
USER sync_user

# Default command
ENTRYPOINT ["python", "main.py"]
