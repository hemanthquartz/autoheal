pipeline {
    agent { label 'BDD-EC2' }

    environment {
        AWS_REGION = 'us-east-1'              // Set your AWS Region
        AWS_ACCOUNT_ID = '123456789012'       // Replace with your AWS account ID
        REPO_NAME = 'your-repo-name'          // Update with your Git repo name
        BRANCH = 'main'                       // Change if you want another branch
        DEPLOY_DIR = 'deployment'             // Directory to deploy from (optional)
    }

    stages {

        stage('Checkout Code') {
            steps {
                git branch: "${BRANCH}",
                    url: "ssh://git@bitbucket.fannieeae.com:7999/APP_CODE/${REPO_NAME}.git",
                    credentialsId: 'git-ssh-key'
            }
        }

        stage('Deploy to AWS') {
            steps {
                withAWS(region: "${AWS_REGION}", credentials: 'aws-credentials-id') {
                    // Example: Deploy a CloudFormation stack
                    sh '''
                    aws cloudformation deploy \
                      --template-file ${DEPLOY_DIR}/template.yaml \
                      --stack-name sample-stack \
                      --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
                      --parameter-overrides EnvName=dev
                    '''
                }
            }
        }
    }
}