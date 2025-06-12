    #!/bin/bash

    # Define the Python version for the layer
    PYTHON_VERSION="python3.9"
    LAYER_DIR="opencv_layer_build"
    ZIP_FILE="opencv_layer.zip"
    # IMPORTANT: Replace <YOUR_S3_BUCKET_NAME> with your actual unique S3 bucket name
    S3_BUCKET_NAME="ocr-bucket--0632" # e.g., "my-ocr-lambda-layer-bucket-12345"

    echo "Starting OpenCV Lambda Layer build for ${PYTHON_VERSION}..."

    # Clean up previous build artifacts with sudo to ensure full removal
    # This prevents 'Permission denied' errors if Docker created files with root ownership.
    sudo rm -rf "${LAYER_DIR}" "${ZIP_FILE}"
    
    # Create the directory structure. This will be owned by your user.
    mkdir -p "${LAYER_DIR}/${PYTHON_VERSION}/lib/${PYTHON_VERSION}/site-packages/"

    # Use Docker to build the layer
    echo "Running Docker container for dependency build..."
    # The Docker container will run as root inside, but the mounted volume will reflect host permissions.
    # We will explicitly ensure packages are installed with permissions that allow cleanup.
    docker run --rm \
        -v "$(pwd)/${LAYER_DIR}":/${LAYER_DIR} \
        amazonlinux:2 \
        /bin/bash -c " \
            yum clean all && \
            yum update -y --disableplugin=fastestmirror && \
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
            # Install packages with user permissions where possible, though yum/pip usually installs as root in Docker
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

    # Important: Change ownership of the created files to your user to prevent future permission issues
    echo "Adjusting permissions for layer build directory..."
    sudo chown -R $(id -un):$(id -gn) "${LAYER_DIR}"

    echo "Packaging layer into ${ZIP_FILE}..."
    cd "${LAYER_DIR}" || exit 1 # Exit if cd fails
    zip -r9 "../${ZIP_FILE}" . # Use standard zip command
    cd ..

    echo "Layer ${ZIP_FILE} created successfully."
    echo "--------------------------------------------------------------------------------"
    echo "ATTENTION: opencv_layer.zip has been created in your project's root directory."
    echo "You will need to manually upload this file to your S3 bucket."
    echo "After uploading, remember to create/update your Lambda Layer in the AWS console."
    echo "--------------------------------------------------------------------------------"    
