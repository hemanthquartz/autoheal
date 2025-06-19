pipeline {
    agent any

    environment {
        BRANCH_NAME = 'dev'
        REPO_NAME = 'claims'
        DEST_FOLDER = 'automation'
        AWS_REGION = 'us-east-1'
        S3_BUCKET = 'your-s3-bucket-name' // replace with real bucket
    }

    stages {
        stage('Initialize') {
            steps {
                echo "Initialization..."
                echo "Repository: https://github.com/ACE-DataAnalytics/${REPO_NAME}.git"
                echo "Branch Name: ${BRANCH_NAME}"
                echo "Destination Folder: ${DEST_FOLDER}"
            }
        }

        stage('Checkout Code') {
            steps {
                git branch: "${BRANCH_NAME}",
                    url: "https://github.com/ACE-DataAnalytics/${REPO_NAME}.git"
            }
        }

        stage('Deploy to AWS (S3)') {
            steps {
                withAWS(region: "${AWS_REGION}", credentials: 'aws-credentials-id') {
                    sh """
                    echo "Copying artifacts to S3..."
                    aws s3 cp ${DEST_FOLDER}/ s3://${S3_BUCKET}/${REPO_NAME}/ --recursive
                    """
                }
            }
        }
    }

    post {
        always {
            echo "Build complete"
        }
        success {
            echo "Build and deploy completed successfully!"
        }
        failure {
            echo "Build failed. Please check logs."
        }
    }
}