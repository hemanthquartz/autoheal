pipeline {
    agent any

    environment {
        AWS_REGION = 'us-east-1'
        S3_BUCKET  = 'your-s3-bucket'
    }

    stages {
        stage('Deploy to S3') {
            steps {
                sh '''
                    export AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
                    export AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
                    export AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN}

                    aws s3 cp ./automation/ s3://${S3_BUCKET}/ --recursive --region ${AWS_REGION}
                '''
            }
        }
    }
}