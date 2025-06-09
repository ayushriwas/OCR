# Use a Python 3.9 slim-buster image as the base
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install system dependencies for Tesseract OCR (though not directly used by current app.py, kept for completeness if needed)
# and general build tools for Python packages.
# Note: Tesseract is no longer directly performing OCR in app.py in this new architecture,
# but it's still good practice to ensure system dependencies for typical Python ML packages are available.
RUN apt-get update && \
    apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    tesseract-ocr-eng \
    build-essential \
    libssl-dev \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    wget \
    curl \
    llvm \
    libncursesw5-dev \
    xz-utils \
    tk-dev \
    libxml2-dev \
    libxmlsec1-dev \
    libffi-dev \
    liblzma-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy the Python requirements file into the container
COPY requirements.txt .

# Install the Python dependencies
# Use --break-system-packages if encountering PEP 668 errors in Docker, though ideally this shouldn't be needed in a clean Docker image.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
# This includes app.py and the templates folder (containing index.html)
COPY . .

# Expose the port that Flask will run on
EXPOSE 5000

# Set environment variables for Flask
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

# Command to run the Flask application
# Using 'gunicorn' is better for production, but 'python app.py' is fine for development
CMD ["python", "app.py"]

