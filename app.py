from flask import Flask, request, jsonify, render_template
import os
import cv2
import numpy as np
import pytesseract
from PIL import Image
import io
import boto3
from dotenv import load_dotenv # For loading environment variables from .env
import uuid # Import uuid for unique filenames

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# --- Configuration ---
# Set the path to the Tesseract executable (change this if Tesseract is not in your PATH)
# For Docker, Tesseract will be in the PATH after installation in the Dockerfile.
# For local development, you might need to specify the full path like:
# pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract' # Common Linux path
# Ensure Tesseract is installed and its path is correctly set if needed.

# AWS Textract Configuration
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_REGION_NAME = os.environ.get('AWS_REGION_NAME', 'us-east-1') # Default to us-east-1

# S3 Configuration
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME') # IMPORTANT: Set this environment variable in .env
S3_REGION = os.environ.get('S3_REGION', AWS_REGION_NAME) # Use same region as Textract by default

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

# Initialize S3 client if S3 bucket name is provided and AWS credentials are set
s3_client = None
if S3_BUCKET_NAME and AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=S3_REGION
        )
        print(f"S3 client initialized successfully for bucket: {S3_BUCKET_NAME}")
    except Exception as e:
        print(f"Error initializing S3 client: {e}")
        s3_client = None
else:
    print("S3_BUCKET_NAME or AWS credentials not found. S3 upload will not be available.")


# --- Helper Functions ---

# Serve index.html from 'templates' folder
@app.route('/')
def index():
    return render_template('index.html')


def preprocess_image_from_bytes(image_bytes):
    """
    Preprocesses the image using OpenCV for better OCR accuracy.
    Converts to grayscale, applies Gaussian blur, and adaptive thresholding.
    Takes image bytes as input.
    """
    try:
        np_array = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

        if image is None:
            raise ValueError("Could not decode image bytes for preprocessing.")

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        thresh = cv2.adaptiveThreshold(blurred, 255,
                                       cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 11, 2)
        return Image.fromarray(thresh)
    except Exception as e:
        print(f"Error during image preprocessing from bytes: {e}")
        raise

def ocr_with_tesseract(image_bytes_for_tesseract):
    """
    Performs OCR on image bytes using Tesseract.
    The image bytes are assumed to be downloaded from S3 if coming from that flow.
    """
    try:
        # Preprocess the downloaded image bytes for Tesseract
        preprocessed_pil_image = preprocess_image_from_bytes(image_bytes_for_tesseract)
        text = pytesseract.image_to_string(preprocessed_pil_image)
        return text
    except pytesseract.TesseractNotFoundError:
        raise Exception("Tesseract is not installed or not found in your system's PATH. Please install it or set pytesseract.pytesseract.tesseract_cmd.")
    except Exception as e:
        raise Exception(f"Tesseract OCR failed: {e}")

def ocr_with_textract_s3(bucket_name, s3_key):
    """
    Performs OCR on an image stored in S3 using Amazon Textract.
    """
    if not textract_client:
        raise Exception("Amazon Textract client is not initialized. Check AWS credentials.")
    if not bucket_name or not s3_key:
        raise Exception("S3 bucket name or key not provided for Textract.")

    try:
        print(f"Calling Textract on s3://{bucket_name}/{s3_key}")
        response = textract_client.detect_document_text(
            Document={
                'S3Object': {
                    'Bucket': bucket_name,
                    'Name': s3_key
                }
            }
        )
        extracted_text = ""
        for item in response.get('Blocks', []):
            if item['BlockType'] == 'LINE':
                extracted_text += item['Text'] + "\n"
        return extracted_text.strip()
    except Exception as e:
        raise Exception(f"Amazon Textract OCR failed for S3 object: {e}")

def upload_to_s3(file_bytes, filename, content_type):
    """Uploads file bytes to S3 and returns the S3 key."""
    if not s3_client or not S3_BUCKET_NAME:
        raise Exception("S3 client not initialized or bucket name not set. Cannot upload to S3.")
    
    # Create a unique filename for S3 to avoid collisions
    s3_key = f"uploads/{uuid.uuid4()}-{filename}" 
    try:
        s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=s3_key, Body=file_bytes, ContentType=content_type)
        print(f"Uploaded {filename} to s3://{S3_BUCKET_NAME}/{s3_key}")
        return s3_key
    except Exception as e:
        raise Exception(f"Failed to upload image to S3: {e}")

def delete_from_s3(s3_key):
    """Deletes an object from S3."""
    if not s3_client or not S3_BUCKET_NAME:
        print("S3 client not initialized or bucket name not set. Cannot delete from S3.")
        return
    try:
        s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        print(f"Deleted s3://{S3_BUCKET_NAME}/{s3_key} from S3.")
    except Exception as e:
        print(f"Error deleting object {s3_key} from S3: {e}")


# --- Flask Routes ---

@app.route('/upload', methods=['POST'])
def upload_file():
    """
    Handles image upload, uploads to S3, and performs OCR using selected model.
    """
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400

    file = request.files['image']
    ocr_model = request.form.get('ocr_model', 'tesseract') # Default to tesseract

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    s3_key = None # Initialize s3_key to None, will be set upon successful S3 upload

    if file:
        try:
            image_bytes = file.read() # Read image content as bytes
            original_filename = file.filename
            content_type = file.content_type

            # --- Step 1: Upload image to S3 ---
            if s3_client and S3_BUCKET_NAME:
                s3_key = upload_to_s3(image_bytes, original_filename, content_type)
            else:
                # If S3 is not configured/available, return an error as S3 upload is a requirement
                return jsonify({'error': 'S3 configuration missing. Cannot upload image to S3.'}), 500

            # --- Step 2: Perform OCR based on selected model ---
            extracted_text = ""
            if ocr_model == 'tesseract':
                print("Using Tesseract OCR (downloading from S3 temporarily)...")
                # Download image from S3 for Tesseract processing
                s3_object = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
                downloaded_image_bytes = s3_object['Body'].read()
                extracted_text = ocr_with_tesseract(downloaded_image_bytes)
            elif ocr_model == 'textract':
                print("Using Amazon Textract OCR (directly from S3)...")
                extracted_text = ocr_with_textract_s3(S3_BUCKET_NAME, s3_key)
            else:
                return jsonify({'error': 'Invalid OCR model selected'}), 400

            return jsonify({'text': extracted_text}), 200

        except Exception as e:
            print(f"Server error: {e}")
            return jsonify({'error': str(e)}), 500
        finally:
            # --- Step 3: Clean up image from S3 (optional, but recommended for temporary files) ---
            if s3_key: # Only try to delete if an S3 key was successfully generated
                delete_from_s3(s3_key)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

