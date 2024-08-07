import boto3
import subprocess
import json
import time
import os

# Define paths and configuration
CREDENTIALS_FILE = '/path/to/credentials.txt'
TEMPLATE_FILE = '/path/to/template.yaml'
STACK_NAME = 'my-stack'
LAMBDA_FUNCTION_NAME = 'MyLambdaFunction'
PROFILE_SUFFIX = 'profile'  # Suffix to append to account IDs

# List of AWS account IDs
ACCOUNT_IDS = ['123456789012', '098765432109']  # Replace with your actual account IDs

# Function to parse credentials file
def parse_credentials(credentials_file):
    credentials = {}
    with open(credentials_file, 'r') as file:
        lines = file.readlines()
        for line in lines:
            if line.strip():  # Ignore empty lines
                parts = line.strip().split(',')
                profile_name = parts[0].strip()
                access_key = parts[1].strip()
                secret_key = parts[2].strip()
                session_token = parts[3].strip()
                credentials[profile_name] = {
                    'aws_access_key_id': access_key,
                    'aws_secret_access_key': secret_key,
                    'aws_session_token': session_token
                }
    return credentials

# Function to deploy the SAM template
def deploy_stack(profile, region):
    print(f"Deploying to account with profile {profile} in region {region}...")
    
    # Set AWS profile environment variables
    os.environ['AWS_PROFILE'] = profile
    os.environ['AWS_REGION'] = region

    # Run SAM deploy command
    deploy_command = [
        'sam', 'deploy',
        '--template-file', TEMPLATE_FILE,
        '--stack-name', STACK_NAME,
        '--capabilities', 'CAPABILITY_IAM',
        '--region', region,
        '--parameter-overrides', 'ExistingRoleArn=""'
    ]

    result = subprocess.run(deploy_command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Deployment failed for profile {profile} in region {region}")
        print(result.stderr)
        raise RuntimeError(f"Deployment failed: {result.stderr}")

    print(f"Deployment successful for profile {profile} in region {region}")

# Function to invoke the Lambda function
def invoke_lambda(profile, region):
    print(f"Invoking Lambda function in account with profile {profile} in region {region}...")
    
    # Set AWS profile environment variables
    os.environ['AWS_PROFILE'] = profile
    os.environ['AWS_REGION'] = region

    # Create Lambda client
    lambda_client = boto3.client('lambda')

    # Get the Lambda function ARN
    response = lambda_client.get_function(FunctionName=LAMBDA_FUNCTION_NAME)
    lambda_arn = response['Configuration']['FunctionArn']

    # Invoke the Lambda function
    response = lambda_client.invoke(
        FunctionName=lambda_arn,
        InvocationType='Event',  # 'Event' for asynchronous invocation
        Payload=json.dumps({})
    )

    if response['StatusCode'] != 202:
        print(f"Failed to invoke Lambda function in profile {profile} in region {region}")
        print(response)
        raise RuntimeError(f"Failed to invoke Lambda: {response}")

    print(f"Lambda function invoked successfully for profile {profile} in region {region}")

# Main function
def main():
    # Fetch credentials from file
    credentials = parse_credentials(CREDENTIALS_FILE)
    
    # Define regions to deploy
    regions = ['us-east-1', 'us-west-2']  # Add more regions as needed

    for account_id in ACCOUNT_IDS:
        profile = f"{account_id}-{PROFILE_SUFFIX}"
        if profile not in credentials:
            print(f"Credentials for profile {profile} not found in {CREDENTIALS_FILE}")
            continue

        # Set AWS credentials for the profile
        boto3.setup_default_session(
            aws_access_key_id=credentials[profile]['aws_access_key_id'],
            aws_secret_access_key=credentials[profile]['aws_secret_access_key'],
            aws_session_token=credentials[profile]['aws_session_token']
        )

        for region in regions:
            # Deploy the template
            deploy_stack(profile, region)

            # Wait for deployment to complete (optional, adjust as needed)
            print("Waiting for stack to stabilize...")
            time.sleep(30)

            # Invoke the Lambda function
            invoke_lambda(profile, region)

    print("All operations completed.")

if __name__ == '__main__':
    main()
