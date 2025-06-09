import os
import uuid
import boto3
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import time # For polling simulation

load_dotenv()

app = Flask(__name__)

# --- AWS Configuration ---
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_REGION_NAME = os.environ.get('AWS_REGION_NAME', 'us-east-1')

S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')
DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME')

# Initialize AWS clients
s3_client = None
dynamodb_client = None

if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION_NAME
        )
        dynamodb_client = boto3.client(
            'dynamodb',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION_NAME
        )
        print("AWS S3 and DynamoDB clients initialized.")
    except Exception as e:
        print(f"Error initializing AWS clients: {e}")
else:
    print("AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY not found. AWS services will not be available.")
    # For local testing without AWS, you might want to mock these or handle gracefully.

# --- Flask Routes ---

# Ensure Flask serves index.html from a 'templates' folder
# Make sure your index.html is located in a 'templates' subfolder within your Flask app's root.
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if not s3_client or not S3_BUCKET_NAME:
        return jsonify({'error': 'S3 client not initialized or bucket name not set.'}), 500
    if not dynamodb_client or not DYNAMODB_TABLE_NAME:
        return jsonify({'error': 'DynamoDB client not initialized or table name not set.'}), 500

    try:
        image_bytes = file.read()
        original_filename = file.filename
        content_type = file.content_type

        # Generate a unique job ID
        job_id = str(uuid.uuid4())
        
        # Define S3 key for the original image. This path triggers the Lambda function.
        s3_original_key = f"original-images/{job_id}-{original_filename}"

        # 1. Upload original image to S3
        s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=s3_original_key, Body=image_bytes, ContentType=content_type)
        print(f"Uploaded original image to s3://{S3_BUCKET_NAME}/{s3_original_key}")

        # 2. Create initial DynamoDB entry
        # The job_id here is what the Lambda function will use to update the item.
        dynamodb_client.put_item(
            TableName=DYNAMODB_TABLE_NAME,
            Item={
                'job_id': {'S': job_id},
                'status': {'S': 'PENDING'},
                'original_s3_key': {'S': s3_original_key}, # Store the S3 key so Lambda can retrieve it
                'timestamp': {'S': str(time.time())} 
            }
        )
        print(f"Created DynamoDB entry for job_id: {job_id}")

        return jsonify({'job_id': job_id, 'message': 'Image uploaded and processing initiated.'}), 200

    except Exception as e:
        print(f"Error during image upload or DynamoDB creation: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/results/<job_id>', methods=['GET'])
def get_ocr_results(job_id):
    if not dynamodb_client or not DYNAMODB_TABLE_NAME:
        return jsonify({'error': 'DynamoDB client not initialized or table name not set.'}), 500
    if not s3_client or not S3_BUCKET_NAME:
        return jsonify({'error': 'S3 client not initialized or bucket name not set.'}), 500


    try:
        response = dynamodb_client.get_item(
            TableName=DYNAMODB_TABLE_NAME,
            Key={'job_id': {'S': job_id}}
        )
        
        item = response.get('Item')
        if not item:
            return jsonify({'status': 'NOT_FOUND', 'message': 'Job ID not found.'}), 404

        status = item['status']['S']
        result = {
            'job_id': item['job_id']['S'],
            'status': status
        }

        if status == 'COMPLETED':
            # Generate pre-signed URLs for display
            original_s3_key = item['original_s3_key']['S']
            preprocessed_s3_key = item.get('preprocessed_s3_key', {}).get('S')
            extracted_text = item.get('extracted_text', {}).get('S', '')

            result['extracted_text'] = extracted_text
            
            # Generate pre-signed URLs (valid for 1 hour)
            if original_s3_key and S3_BUCKET_NAME:
                result['original_image_url'] = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': S3_BUCKET_NAME, 'Key': original_s3_key},
                    ExpiresIn=3600 
                )
            if preprocessed_s3_key and S3_BUCKET_NAME:
                result['preprocessed_image_url'] = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': S3_BUCKET_NAME, 'Key': preprocessed_s3_key},
                    ExpiresIn=3600
                )
        elif status == 'FAILED':
            result['error_message'] = item.get('error_message', {}).get('S', 'Unknown error during processing.')

        return jsonify(result), 200

    except Exception as e:
        print(f"Error fetching OCR results from DynamoDB: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Flask will look for index.html inside a 'templates' folder by default.
    # Ensure your project structure is:
    # your-app/
    # ├── app.py
    # └── templates/
    #     └── index.html
    app.run(debug=True, host='0.0.0.0', port=5000)

