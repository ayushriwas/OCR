import os
import io
import json
import boto3
import cv2
import numpy as np
from PIL import Image
import logging
import time # Using time.time() for timestamping (consider datetime for human readability)

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
# These clients are automatically configured by Lambda's execution environment role
s3_client = boto3.client('s3')
textract_client = boto3.client('textract')
dynamodb_client = boto3.client('dynamodb')

# X-Ray integration: Lambda will automatically instrument if X-Ray is enabled on the function.
# No code changes needed here beyond importing if you use a specific SDK patch.
# For standard Lambda functions, just enabling it in console/Terraform is enough.
# import aws_xray_sdk.core
# aws_xray_sdk.core.patch_all() # This line would be used if you need deeper SDK instrumentation

# Environment variables for Lambda (set via Terraform or Lambda console)
DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME')
PREPROCESSED_IMAGES_PREFIX = os.environ.get('PREPROCESSED_IMAGES_PREFIX', 'preprocessed-images/')

def preprocess_image_opencv(image_bytes):
    """
    Preprocesses the image using OpenCV for better OCR accuracy.
    Converts to grayscale, applies Gaussian blur, and adaptive thresholding.
    Returns preprocessed image bytes (PNG format).
    """
    try:
        np_array = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

        if image is None:
            logger.error("Could not decode image bytes for preprocessing.")
            raise ValueError("Could not decode image bytes.")

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Adaptive thresholding (often good for varied lighting and text clarity)
        thresh = cv2.adaptiveThreshold(blurred, 255,
                                       cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 11, 2)
        
        # Encode the preprocessed image back to bytes (PNG format for consistency)
        is_success, buffer = cv2.imencode(".png", thresh)
        if not is_success:
            logger.error("Failed to encode preprocessed image to PNG.")
            raise Exception("Failed to encode preprocessed image.")
        
        return io.BytesIO(buffer)

    except Exception as e:
        logger.error(f"Error during image preprocessing with OpenCV: {e}", exc_info=True)
        raise

def lambda_handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Expecting an S3 PutObject event
    if 'Records' not in event:
        logger.error("Event does not contain S3 records.")
        return {'statusCode': 400, 'body': 'Invalid event format'}

    s3_record = event['Records'][0]['s3']
    bucket_name = s3_record['bucket']['name']
    original_s3_key = s3_record['object']['key']

    if not DYNAMODB_TABLE_NAME:
        logger.error("DYNAMODB_TABLE_NAME environment variable not set.")
        return {'statusCode': 500, 'body': 'DynamoDB table name not configured.'}

    # Extract job_id from the S3 key
    # Assuming S3 key format is "original-images/{job_id}-{original_filename}"
    job_id_part = original_s3_key.split('/')[-1] # Gets "uuid-filename.ext"
    job_id = job_id_part.split('-')[0] # Gets "uuid"

    if not job_id:
        logger.error(f"Could not extract job_id from S3 key: {original_s3_key}. Using full key as fallback job_id.")
        job_id = original_s3_key # Fallback, though current Flask expects UUID.

    # Start X-Ray subsegment for detailed tracing of this Lambda invocation
    # with aws_xray_sdk.core.in_segment('OCR_Processing_Lambda'): # Uncomment if using SDK patch
    try:
        # 1. Download original image from S3
        logger.info(f"Downloading s3://{bucket_name}/{original_s3_key}")
        response = s3_client.get_object(Bucket=bucket_name, Key=original_s3_key)
        original_image_bytes = response['Body'].read()
        logger.info("Original image downloaded.")

        # 2. Preprocess image with OpenCV
        logger.info("Preprocessing image with OpenCV...")
        preprocessed_image_stream = preprocess_image_opencv(original_image_bytes)
        preprocessed_s3_key = f"{PREPROCESSED_IMAGES_PREFIX}{job_id}-preprocessed.png"
        
        # 3. Upload preprocessed image to S3
        logger.info(f"Uploading preprocessed image to s3://{bucket_name}/{preprocessed_s3_key}")
        s3_client.put_object(
            Bucket=bucket_name, 
            Key=preprocessed_s3_key, 
            Body=preprocessed_image_stream.getvalue(), 
            ContentType='image/png' # Force PNG as output for preprocessed image
        )
        logger.info("Preprocessed image uploaded.")

        # 4. Perform OCR with Amazon Textract on the original S3 object (Textract prefers raw)
        logger.info(f"Performing OCR with Amazon Textract on s3://{bucket_name}/{original_s3_key}")
        textract_response = textract_client.detect_document_text(
            Document={
                'S3Object': {
                    'Bucket': bucket_name,
                    'Name': original_s3_key
                }
            }
        )
        extracted_text = ""
        for item in textract_response.get('Blocks', []):
            if item['BlockType'] == 'LINE':
                extracted_text += item['Text'] + "\n"
        extracted_text = extracted_text.strip()
        logger.info("Textract OCR completed.")

        # 5. Update DynamoDB with results
        logger.info(f"Updating DynamoDB for job_id: {job_id}")
        dynamodb_client.update_item(
            TableName=DYNAMODB_TABLE_NAME,
            Key={'job_id': {'S': job_id}},
            UpdateExpression="SET #s = :status, extracted_text = :text, preprocessed_s3_key = :preprocessed_key, updated_at = :updated_at",
            ExpressionAttributeNames={'#s': 'status'}, # 'status' is a reserved keyword in DynamoDB, so using an alias
            ExpressionAttributeValues={
                ':status': {'S': 'COMPLETED'},
                ':text': {'S': extracted_text},
                ':preprocessed_key': {'S': preprocessed_s3_key},
                ':updated_at': {'S': str(time.time())}
            }
        )
        logger.info(f"DynamoDB updated for job_id: {job_id} with status COMPLETED.")

        return {'statusCode': 200, 'body': 'OCR processed and results saved.'}

    except Exception as e:
        logger.error(f"Error during Lambda execution for S3 key {original_s3_key}: {e}", exc_info=True)
        # Update DynamoDB with FAILED status
        try:
            dynamodb_client.update_item(
                TableName=DYNAMODB_TABLE_NAME,
                Key={'job_id': {'S': job_id}},
                UpdateExpression="SET #s = :status, error_message = :error_msg, updated_at = :updated_at",
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={
                    ':status': {'S': 'FAILED'},
                    ':error_msg': {'S': str(e)},
                    ':updated_at': {'S': str(time.time())}
                }
            )
            logger.info(f"DynamoDB updated for job_id: {job_id} with status FAILED.")
        except Exception as db_e:
            logger.error(f"Failed to update DynamoDB with FAILED status for job_id {job_id}: {db_e}")
        
        return {'statusCode': 500, 'body': f'Error processing image: {e}'}
