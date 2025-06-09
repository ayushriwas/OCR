#!/bin/bash

# Define the Python version for the layer
PYTHON_VERSION="python3.9"
LAYER_DIR="opencv_layer_build"
ZIP_FILE="opencv_layer.zip"
S3_BUCKET_NAME="<YOUR_S3_BUCKET_NAME>" # Use your S3 bucket name

echo "Starting OpenCV Lambda Layer build for ${PYTHON_VERSION}..."

# Clean up previous build artifacts
rm -rf ${LAYER_DIR} ${ZIP_FILE}
mkdir -p ${LAYER_DIR}/${PYTHON_VERSION}/lib/${PYTHON_VERSION}/site-packages/

# Use Docker to build the layer
# We use a public Amazon Linux 2 image to simulate Lambda's environment
# This ensures native dependencies are compiled correctly.
docker run --rm \
    -v "$(pwd)/${LAYER_DIR}":/${LAYER_DIR} \
    amazonlinux:2 \
    /bin/bash -c " \
        yum update -y && \
        yum install -y \
            python3 \
            python3-pip \
            gcc-c++ \
            cmake \
            unzip \
            libuuid-devel \
            libgthread-devel \
            glibc-devel \
            mesa-libGL-devel \
            mesa-libGLU-devel \
            atlas-devel \
            blas-devel \
            lapack-devel \
            libpng-devel \
            libjpeg-turbo-devel \
            libtiff-devel && \
        pip3 install --target=/${LAYER_DIR}/${PYTHON_VERSION}/lib/${PYTHON_VERSION}/site-packages \
            opencv-python-headless \
            numpy \
            --no-cache-dir && \
        # Clean up unnecessary files to reduce layer size
        find /${LAYER_DIR}/${PYTHON_VERSION}/lib/${PYTHON_VERSION}/site-packages/ -name '__pycache__' -type d -exec rm -rf {} + && \
        find /${LAYER_DIR}/${PYTHON_VERSION}/lib/${PYTHON_VERSION}/site-packages/ -name '*.pyc' -delete && \
        # Attempt to strip binaries for smaller size. Ignore errors if strip is not found/applicable.
        find /${LAYER_DIR}/${PYTHON_VERSION}/lib/${PYTHON_VERSION}/site-packages/ -type f -name '*.so*' -print0 | xargs -0 --no-run-if-empty strip --strip-unneeded || true \
    "

echo "Packaging layer into ${ZIP_FILE}..."
cd ${LAYER_DIR}
zip -r9 ../${ZIP_FILE} .
cd ..

echo "Layer ${ZIP_FILE} created successfully."

# Upload the zip file to S3
echo "Uploading ${ZIP_FILE} to s3://${S3_BUCKET_NAME}/lambda-layers/"
aws s3 cp ${ZIP_FILE} s3://${S3_BUCKET_NAME}/lambda-layers/${ZIP_FILE}

echo "Custom OpenCV layer build and upload complete. You can now create the Lambda Layer using the uploaded zip file."
