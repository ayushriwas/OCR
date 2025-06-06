# app.py
from flask import Flask, request, jsonify
import os
import cv2
import numpy as np
import pytesseract
from PIL import Image
import io
import boto3
from dotenv import load_dotenv # For loading environment variables from .env

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# --- Configuration ---
# Set the path to the Tesseract executable (change this if Tesseract is not in your PATH)
# For Docker, Tesseract will be in the PATH after installation in the Dockerfile.
# For local development, you might need to specify the full path like:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe' # Windows example
# pytesseract.pytesseract.tesseract_cmd = '/usr/local/bin/tesseract' # macOS example (if installed via brew)
# Ensure Tesseract is installed and its path is correctly set if needed.

# AWS Textract Configuration
# It's highly recommended to use environment variables or IAM roles for production.
# For local testing, you can set these in a .env file or directly in your environment.
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_REGION_NAME = os.environ.get('AWS_REGION_NAME', 'us-east-1') # Default to us-east-1

# Initialize Textract client if AWS credentials are provided
textract_client = None
if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    try:
        textract_client = boto3.client(
            'textract',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION_NAME
        )
        print("Amazon Textract client initialized successfully.")
    except Exception as e:
        print(f"Error initializing Textract client: {e}")
        textract_client = None
else:
    print("AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY not found. Amazon Textract will not be available.")

# --- Helper Functions ---

def preprocess_image(image_bytes):
    """
    Preprocesses the image using OpenCV for better OCR accuracy.
    Converts to grayscale, applies Gaussian blur, and adaptive thresholding.
    """
    try:
        # Convert image bytes to numpy array
        np_array = np.frombuffer(image_bytes, np.uint8)
        # Decode image
        image = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

        if image is None:
            raise ValueError("Could not decode image bytes.")

        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Apply Gaussian blur to remove noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Apply adaptive thresholding for binarization
        # ADAPTIVE_THRESH_GAUSSIAN_C is often good for varied lighting
        # THRESH_BINARY_INV can be used if text is dark on a light background, otherwise THRESH_BINARY
        thresh = cv2.adaptiveThreshold(blurred, 255,
                                       cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 11, 2)

        # Return the preprocessed image (as a Pillow Image object for pytesseract)
        return Image.fromarray(thresh)
    except Exception as e:
        print(f"Error during image preprocessing: {e}")
        raise

def ocr_with_tesseract(image_pil):
    """
    Performs OCR on a PIL Image object using Tesseract.
    """
    try:
        # Perform OCR using pytesseract
        text = pytesseract.image_to_string(image_pil)
        return text
    except pytesseract.TesseractNotFoundError:
        raise Exception("Tesseract is not installed or not found in your system's PATH.")
    except Exception as e:
        raise Exception(f"Tesseract OCR failed: {e}")

def ocr_with_textract(image_bytes):
    """
    Performs OCR on image bytes using Amazon Textract.
    """
    if not textract_client:
        raise Exception("Amazon Textract client is not initialized. Check AWS credentials.")
    try:
        response = textract_client.detect_document_text(
            Document={
                'Bytes': image_bytes
            }
        )
        # Extract text from the Textract response
        extracted_text = ""
        for item in response.get('Blocks', []):
            if item['BlockType'] == 'LINE':
                extracted_text += item['Text'] + "\n"
        return extracted_text.strip()
    except Exception as e:
        raise Exception(f"Amazon Textract OCR failed: {e}")

# --- Flask Routes ---

@app.route('/')
def home():
    return "Image to Text Converter Backend is running!" # Basic health check or placeholder

@app.route('/upload', methods=['POST'])
def upload_file():
    """
    Handles image upload, pre-processing, and OCR using selected model.
    """
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400

    file = request.files['image']
    ocr_model = request.form.get('ocr_model', 'tesseract') # Default to tesseract

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file:
        try:
            image_bytes = file.read() # Read image content as bytes

            # Perform image preprocessing (using OpenCV)
            preprocessed_pil_image = preprocess_image(image_bytes)

            extracted_text = ""
            if ocr_model == 'tesseract':
                print("Using Tesseract OCR...")
                extracted_text = ocr_with_tesseract(preprocessed_pil_image)
            elif ocr_model == 'textract':
                print("Using Amazon Textract OCR...")
                # Textract needs raw image bytes, not PIL object
                extracted_text = ocr_with_textract(image_bytes)
            else:
                return jsonify({'error': 'Invalid OCR model selected'}), 400

            return jsonify({'text': extracted_text}), 200

        except Exception as e:
            print(f"Server error: {e}")
            return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # When running locally, Flask will pick up .env variables if python-dotenv is installed.
    # For production or Docker, ensure environment variables are set.
    app.run(debug=True, host='0.0.0.0', port=5000)

