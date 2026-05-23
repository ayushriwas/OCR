## Project is in development Phase as there are some changes which I am trying to apply You will get to see the Updated version very soon! Thank you for visiting

Working 

The project's workflow is a fully automated, end-to-end system for Optical Character Recognition (OCR), designed to be scalable and resilient on AWS. It combines a user-facing web application with a complex, event-driven backend process, all managed by robust DevOps practices.

### The End-to-End Workflow

The entire process can be understood in two main parts: the user's interaction and the automated backend.

#### 1. User Interaction and Triggering the Workflow
The user-facing part of the application is a **Python Flask web app** running on **AWS EKS**. The user uploads an image through this application. The Flask app's sole responsibility is to take this image and upload it to a designated folder (`original-images`) in an **Amazon S3 bucket**. This single action kicks off the entire automated workflow.

#### 2. Automated Backend Process
Once the image is in the `original-images` S3 folder, a chain of automated events begins:

1.  **Lambda Trigger:** The S3 upload acts as a trigger, automatically invoking an **AWS Lambda function**.
2.  **Image Processing:** The Lambda function downloads the newly uploaded image and performs preprocessing tasks using the **OpenCV library**. It then saves the processed image to a separate S3 folder (`preprocessed-images`).
3.  **OCR with Textract:** The Lambda function sends this preprocessed image to **Amazon Textract** to perform the OCR and extract the text.
4.  **Storing Results:** Textract returns the extracted text to the Lambda function. The Lambda function then:
    * Generates a unique `jobId` for the task and stores metadata (status, S3 location, etc.) in an **Amazon DynamoDB** table.
    * Saves the extracted text to another S3 folder (`extracted-text`), associating it with the unique `jobId`.
5.  **Cleanup:** Finally, the Lambda function deletes the original, unprocessed image from the `original-images` S3 folder to save storage space.

---

### The Role of Key Technologies

This seamless workflow is made possible by a suite of powerful technologies:

* **IAM (Identity and Access Management):** IAM is the security framework that governs everything. It provides the permissions for all actors in the system:
    * The `terraform` user has an IAM policy that allows it to provision and manage all the AWS infrastructure.
    * The Lambda function has an IAM role that grants it permission to access S3, DynamoDB, and Textract.
    * The EKS worker nodes have an IAM role to interact with the EKS control plane and other AWS services.
    * 

* **Docker:** Docker is used to containerize the Flask web application in **Phase 2**. It packages the application code, its dependencies, and the OpenCV library into a single, portable **Docker image**. This ensures the application runs identically whether on a developer's machine or in the production EKS environment.

* **EKS (Elastic Kubernetes Service):** EKS is the highly scalable and resilient home for your Dockerized Flask application. In **Phase 3**, Terraform provisions the EKS cluster. During **Phase 5**, a Jenkins pipeline deploys the Docker image to EKS, which automatically manages the pods, handles scaling, and ensures the application remains highly available and resilient to failure.
    * 

* **Terraform & Jenkins:** These are the core **DevOps** tools. Terraform provisions the entire AWS infrastructure, while Jenkins automates the **CI/CD pipeline**, building the Docker image and deploying it to EKS. Together, they ensure the project can be set up, deployed, and managed consistently with minimal manual effort.

In essence, your project uses a containerized web app on a managed Kubernetes cluster (**EKS** and **Docker**), which triggers a serverless workflow (**Lambda**) to perform OCR (**Textract**) and data management (**S3** and **DynamoDB**), all of which is governed by a robust security model (**IAM**) and automated with infrastructure as code and CI/CD pipelines (**Terraform** and **Jenkins**).