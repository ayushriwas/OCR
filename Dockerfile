# Use a Python 3.9 slim-buster image as the base
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install system dependencies for Tesseract OCR
# This includes tesseract-ocr and necessary language packs (e.g., eng for English)
RUN apt-get update && \
    apt-get install -y tesseract-ocr libtesseract-dev tesseract-ocr-eng && \
    rm -rf /var/lib/apt/lists/*

# Copy the Python requirements file into the container
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
# This includes app.py (backend) and the templates folder (containing index.html)
COPY . .

# Expose the port that Flask will run on
EXPOSE 5000

# Set environment variables for Flask
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

# Command to run the Flask application
# Use 'python -m flask run' or 'gunicorn' for production
CMD ["python", "app.py"]
