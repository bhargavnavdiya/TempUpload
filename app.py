import json
import boto3
import os
import html

from datetime import datetime, timedelta, timezone

# table_name = os.environ['rds_del_log_table_name']
# retain_tag_name = os.environ ['tag_name_to_retain']
#from_email = os.environ['from_email']
#to_email = os.environ['to_email']
# first_run = os.environ['first_run']
#region = os.environ ['region']
# days_purge_after = int(os.environ['days_purge_after'])

retain_tag_name = 'retain'
from_email = 'ashishupadhyay@maximus.com'
to_email = 'ashishupadhyay@maximus.com'
first_run = 'y'
region = 'us-east-1'
days_warn_from = 7
days_purge_after = 30
# environment = os.environ['environment']
#Create a Boto3 RDS client

rds_client = boto3.client('rds',region_name=region)

ses_client = boto3.client('ses',region_name=region)
dynamodb_client = boto3.client('dynamodb', region_name=region)
purge_snapshot = True
ec2_client = boto3.client('ec2', region_name = region)
client_sts = boto3.client('sts')
client_iam = boto3.client('iam')

table_name = 'ImageManualImagePurgeRepo'

client_sts = boto3.client('sts')
response_sts = client_sts.get_caller_identity()
account_id = response_sts['Account']

list_of_images = []

start_time = datetime.now(timezone.utc) - timedelta(days=7)

start_time_30 = datetime.now(timezone.utc) - timedelta(days=30)


def process_images():
    image_warn_table = []
    image_warn_head = ['Image Id', 'Description', 'Volume Size', 'Created On', 'Last Launched On', 'Image Age', 'Target Delete Date', 'Created By']
    image_warn_table.append(image_warn_head)
    email_text_warn = f'''Manual Images older than {days_purge_after} days will be deleted on the target deleted date, which is after you set the first_run environment variable to N. If you want to retain an Image, add a tag named "retain" with the value as retain date in YYYY-MM-DD format e.g. 2023-09-20.\n'''
    
    image_purge_table = []
    image_purge_head = ['Image Id', 'Description', 'Volume Size', 'Created On', 'Last Launched On', 'Image Age', 'Target Delete Date', 'Created By']
    image_warn_table.append(image_purge_head)
    image_text_purge = f'''Manual Images older than {days_purge_after} days will be deleted on the target deleted date, which is after you set the first_run environment variable to N. If you want to retain an Image, add a tag named "retain" with the value as retain date in YYYY-MM-DD format e.g. 2023-09-20.\n'''
    
    filters = [{'Name': 'owner-id', 'Values': [account_id]}] # Filter for manual images
    response = ec2_client.describe_images(Filters=filters)

    print(len(response.get('Images',[])))
    
    for image in response.get('Images', []):
        #image_id = image['ImageId']
        if is_manual_image(image) == True:
            image_age = datetime.now(timezone.utc) - image['LastLaunchedTime']
            if image_age.days > days_warn_from and image_age.days <= days_purge_after:
                process_warn_image(image, image_warn_table, image_age)
            elif image_age.days > days_purge_after:
                purge_image(image, image_purge_table, image_age)
            else:
                continue
            
    if len(image_warn_table) > 1:
        short_and_send_email(image_warn_table, image_warn_head, email_text_warn)
        
def purge_image(image, image_purge_table, image_age):
    if is_retain_tag_active(image) == True or first_run == 'y':
        target_delete_date = image['LastLaunchedTime'] + timedelta(days=1)
        created_by = get_image_creators(image['ImageId'])
        image_prov_row = [image['ImageId'], image['Description'], image['VolumeSize'], image['CreationDate'].strftime("%Y-%m-%d"), image['LastLaunchedTime'].strftime("%Y-%m-%d"), image_age.days, target_delete_date, created_by]
        image_purge_table.append(image_prov_row)
    else:
        print('in delete')
        #response = ec2_client.deregister_image(ImageId = image['ImageId'], DryRun = True)
        ec2_client.deregister_image(ImageId = image['ImageId'], DryRun = True)
        print(f"Image with Id {image['ImageId']} deleted successfully.")
        
def process_warn_image(image, image_warn_table, image_age):
    target_delete_date = image['LastLaunchedTime'] + timedelta(days = 30)
    created_by = get_image_creators(image['ImageId'])
    image_warn_row = [image['ImageId'], image['Description'], image['VolumeSize'], image['CreationDate'].strftime("%Y-%m-%d"), image['LastLaunchedTime'].strftime("%Y-%m-%d"), image_age.days, target_delete_date, created_by]
    image_warn_table.append(image_warn_row)
    
def short_and_send_email(image, header_text, email_body_text):
    if not isinstance(image, list) or len(image) == 0:
        print('Error: image is not a valid list or is empty')
        return
    image = image[1:]
    image = sorted(image, key = lambda row: row[5])
    image.insert(0, header_text)
    send_email_report(create_html_table(email_body_text, image))
    
def is_retain_tag_active(image):
    is_retain_tag_active = False
    image_id = image['ImageId']
    response = ec2_client.describe_images(ImageIds = [image_id])
    image = response['Images'][0]
    tags = image.get('Tags',[])
    
    for tag in tags:
        current_date = datetime.now()
        current_date = datetime.strptime(current_date.strftime('%Y-%m-%d'),'%Y-%m-%d')
        
        try:
            if (tag['Key'] == retain_tag_name):
                tagged_date = datetime.strptime(tag['Value'], '%Y-%m-%d')
                if tagged_date > current_date:
                    is_retain_tag_active = True
        except Exception as e:
            print('in exception')
            print(e)
            continue
        
    return is_retain_tag_active

def sort_and_send_email(email_text, header_row, image_table):
    image_table = image_table[1:]
    image_table = sorted(image_table, key = lambda row: row[5])
    image_table.insert(0, header_row)
    send_email_report(create_html_table(email_text, image_table))

def is_manual_image(image):
    is_manual_image = True
    image_id = image['ImageId']
    response = ec2_client.describe_images(ImageIds = [image_id])
    image = response['Images'][0]
    tags = image.get('Tags',[])
    
    for tag in tags:
        try:
            if (tag['Key'] == 'Created by application') and (tag['Value'] == 'CloudRanger'):
                is_manual_image = False
            elif (tag['Key'] == 'Created by application') and (tag['Value'] == 'AWSBackup'):
                is_manual_image = False
            elif (tag['Key'] == 'provisioner') and (tag['Value'] == 'terraform'):
                is_manual_image = False
            
        except Exception as e:
            print('In exception in manual image')
            print(e)
            is_manual_image = True
        
        return is_manual_image
    
def get_image_creators(image_identifier):
    user_name = 'Aged Out'
    user_name = get_image_creator_by_creat(image_identifier, 'CreateImage')
    if (user_name == 'Aged Out'):
        user_name = get_image_creator_by_creat(image_identifier, 'CopyImage')
    return user_name

def get_image_creator_by_creat(image_identifier, event_type):
    image_creators = {}
    ct_client = boto3.client('cloudtrail', region_name = region)
    
    #Define the event we're interested in (CreateImage/CopyImage)
    lookup_attributes = [{'AttributeKey' : 'EventName', 'AttributeValue': event_type}]
    
    #Use pagination and sort by event time(descending) to get the latest event
    paginator = ct_client.get_paginator('lookup_events')
    user_name = 'Aged Out'
    
    for page in paginator.paginate(LookupAttributes = lookup_attributes):
        for event in page['Events']:
            try:
                event_data = json.loads(event['CloudTrailEvent'])
                image_id = event_data['responseElements']['imageId']
                if(image_id == image_identifier):
                    
                    user_name = event_data['userIdentity']['principalId']
                    
            except Exception as e:
                print(e)
                continue
    if ':' in user_name:
        # Split the RECIPIENTS environment variable by comma to get a list of email addresses
        user_name = user_name.split(':')[1]
    return user_name

def create_html_table(header_text, array):
    
    table = "<p>" + header_text + "<p>" + "<table border = '1' style = 'border-style:solid; border-width:1px;'>"
    i = 0
    for row in array:
        if i == 0:
            table += "<tr bgcolor = '#dddddd'>"
        i = i + 1
        for column in row:
            column_str = str(column)
            table += "<td> {} </td>".format(html.escape(column_str.replace('&', '&amp;')))
        table += "</tr>"
    table += "</table>"
    return table

def is_purge_image(image):
    purge_image = True
    arn = image['OutpostArn']
    tags = rds_client.list_tags_for_resource(ResourceName = 'OutpostArn')['TagList']
    tag_names = [tag['Key'] for tag in tags]
    
    for tag in tags:
        try:
            current_date = datetime.now()
            current_date = datetime.strptime(current_date.strftime('%m/%d/%Y'), '%m/%d/%Y')
            
            if (tag['Key'] == retain_tag_name):
                tagged_date = datetime.strptime(tag['Value'], '%m/%d/%Y')
                if tagged_date > current_date:
                    purge_image = False
                elif (tag['Key'] == 'Created by application') and (tag['Value'] == 'CloudRanger'):
                    purge_image = False
                elif (tag['Key'] == 'Created by application') and (tag['Value'] == 'AWSBackup'):
                    purge_image = False
                elif (tag['Key'] == 'provisioner') and (tag['Value'] == 'terraform'):
                    purge_image = False
        except Exception as e:
            print("In exception while purging an image: ")
            print(e)
            purge_image = False
            continue
    return purge_image

# def send_email_report( body_text): 
#     response_sts = client_sts.get_caller_identity() 
#     response_iam = client_iam.list_account_aliases() 
#     session = boto3.session.Session() 
#     region = session.region_name

#     account_id = response_sts['Account'] 
#     account_name = response_iam['AccountAliases'][0] 
#     if ',' in to_email: # Split the RECIPIENTS environment variable by comma to get a list of email addresses 
#         recipients = to_email.split(',') 
#     else: # The RECIPIENTS environment variable contains only one email address 
#         recipients = to_email + ',' +to_email 
#         recipients = to_email.split(',') 
#     response = ses_client.send_email( 
#         Source = from_email,
#         Destination={'ToAddresses': recipients}, 
#         ReplyToAddresses = [from_email], 
#         Message={ 
#             'Subject': {
#             'Data': 'Important communication- purging EC2 Volume Snapshot for AWS account: '+ account_name +  '('+account_id +' '+region+') '
#             'Charset': 'utf-8'
#             },
#             'Body': {
#                 'HTML':{
#                     'Data': body_text,
#                     'Charset': 'utf-8'
#                 },
#             }
#         }
#     )