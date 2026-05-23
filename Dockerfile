# Use the official Python slim image as the base for a lightweight container
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies
# - tesseract-ocr: Required for pytesseract to work
# - libgl1 & libglib2.0-0: Required system libraries for cvzone/OpenCV
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container first to leverage Docker cache
COPY requirements.txt .

# Install the Python dependencies listed in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Create the media directory for uploaded images as defined in app.py
RUN mkdir -p ./media

# Expose the port that the Flask app runs on
EXPOSE 8000

# Command to run the application
CMD ["python", "app.py"]
