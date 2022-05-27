import boto3
import sys
from botocore.exceptions import ClientError
import logging
import sys
import uuid
import re

### creating a log file for the code 
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s  %(name)s  %(levelname)s: %(message)s')

file_handler = logging.FileHandler('restoreS3IntArchive.log')
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)


s3 = boto3.client("s3")
sts = boto3.client("sts")


if len(sys.argv) !=4:
    logger.info(f"Command to run the code for restoring an object from the S3 Intelligent Archive tier is - restoreS3IntArchive.py bucketname prefix/key SNSArn. Ex: restoreS3IntArchive.py s3bucket nothingtoseehere/nothing.csv0030part00 arn:aws:sns:us-east-1:123456789123:restore")
    logger.info(f"Exiting .....")
    sys.exit(1)

bucketName = sys.argv[1].strip()
key = sys.argv[2].strip()
SNSArn = sys.argv[3].strip()
if not re.search('arn:aws:sns:[a-z0-9\-]+:[a-z0-9\-]+:[a-z0-9\-]*', SNSArn):
    logger.error (f"Please check if your SNS Arn format is correct. Here is the snsarn format - arn:aws:sns:[a-z0-9\-]+:[a-z0-9\-]+:[a-z0-9\-]*. For example: arn:aws:sns:us-east-1:123456789123:restore")
    sys.exit(1)

##start of the getting and configuring S3 event configuration
# method to determine accountID 
def getAccountID():
    account_id = sts.get_caller_identity()
    return(account_id['Account'])

#global variable
ownerAccountId = getAccountID()

#creating a policy with a unique name by randomizing using uuid lib
def createRestorePolicy(bucket, Events):
    policy = {
                    'Id': "Added S3 event notification for restore - "+ bucket +"-"+str(uuid.uuid4()),
                    'TopicArn': SNSArn,
                    'Events': Events,
                }
    return policy


# putting S3 restore configuration for the bucket. Policy is generated from addOrUpdateS3Event menthod
def putEventConfiguration(bucket, policy):
    try:
        s3.put_bucket_notification_configuration(
            Bucket= bucket,
             ExpectedBucketOwner=ownerAccountId,
            NotificationConfiguration=policy
        )
    except ClientError as error:
            if error.response['Error']['Code'] == 'InvalidArgument':
                logger.error(f"Check SNS Access Policy Permissions")
            elif error.response['Error']['Code'] == 'NoSuchBucket':
                logger.info(f"Bucket {bucket} does exist or you are not the owner. exiting ...")
                sys.exit()
            else:
                logger.error(f"Something wrong with SNS configuration...Please make sure SNS topic is configured correctly")


# getting the current S3 event configuration for the bucket. It could be null or have some S3 events
# such as put, copy or even restore. This method returns the list of configured s3 events on the bucket 
# and S3 bucket event configuration.
def getEventConfiguration(bucket, key):
    configList = []
    #getting the latest configuration data
    try:
        configuration = s3.get_bucket_notification_configuration(
        Bucket=bucket,
        ExpectedBucketOwner=ownerAccountId
        )
    except ClientError as err:
        if err.response['Error']['Code'] == 'NoSuchBucket':
            logger.info(f"Bucket {bucket} does exist or you are not the owner. exiting ...")
            sys.exit()
    # if no s3 restore events are found, no update to the configDict
    if len(configuration) == 0:
        logger.info(f"No S3 event configuration is set for a bucket {bucket}. Addding a configuration for s3:ObjectRestore:Post,s3:ObjectRestore:Completed for the restore process")
        configList = []  
    else:  
        #checking to see if restore initiation and completion already set
        # deleting the value for the ResponseMetadata key from the get_bucket_notification_configuration query
        del configuration['ResponseMetadata']
        # one configuration can have mutliple values, checking both scenarios.
        for val in configuration.values():
            if len(val) > 1:
                for v in val:
                    configList.extend(v['Events'])
            else:   
                configList.extend(val[0]['Events'])
    return configList,configuration


#This method adds or append S3 event configuration of the bucket with  's3:ObjectRestore:Post', 's3:ObjectRestore:Completed'
#scenario #1: If no S3 event is configured, it adds the s3 events for S3 restore initiation and completed
#Scenario #2: Check if either of 's3:ObjectRestore:Post' or/and 's3:ObjectRestore:Completed' are not configured on the bucket. Create a list of missing S3 restore events
    #2a. if Topic Configuration exists, append the existing Topic Configuration with the S3 retore event from the list and keep rest of the S3 event policy unchanged
    #2b. if Topic Configuration does not exist, add new topic Configuration with the S3 retore event from the list and keep rest of the S3 event policy unchanged.   
        
def addOrUpdateS3Event(bucket,key):
    eventsList = ['s3:ObjectRestore:Post', 's3:ObjectRestore:Completed']
    restoreList= []
    cfList, config = getEventConfiguration(bucket, key)
    #If no S3 event is set, it adds the s3 events for S3 restore initiation and completed
    if cfList == []:
        # create a S3 event restore policy for initiation and complete
        s3EventPolicy = createRestorePolicy(bucket, eventsList)
        eventDt= {'TopicConfigurations': [s3EventPolicy]}
        #configure S3 events for restoring object with SNS topic
        putEventConfiguration(bucket, eventDt)
        logger.info(f"No S3 event Configuration found. Added a new restore s3 event policy for the bucket {bucket}")
    else:
        #Check if either of 's3:ObjectRestore:Post' or/and 's3:ObjectRestore:Completed' are not configured on the bucket 
        # create a restoreList of the restore S3 event(s) not configured
        for event in eventsList:
            if event not in cfList:
                restoreList.append(event)
        #if restoreList is not empty, that means restore s3 events needs to configured either or initiation or completed or both.    
        if restoreList != []:
            s3EventPolicy = createRestorePolicy(bucket, restoreList)
            eventDt= {'TopicConfigurations': [s3EventPolicy]}
            #TopicConfiguration already exists then append the existing TopicConfiguraton with the S3 restore event(s) recorded in the  restoreList
            if 'TopicConfigurations' in config.keys():
                config['TopicConfigurations'].extend(eventDt['TopicConfigurations'])
                putEventConfiguration(bucket, config)
                logger.info(f"Appended Existing Topic Configuration for S3 restore event policy for the bucket {bucket}")
            else:
                #TopicConfiguration does not exist then added TopicConfiguraton with the S3 restore event(s) recorded in the  restoreList
                config.update(eventDt)
                putEventConfiguration(bucket,config)
                logger.info(f"Added Topic Configuration for S3 restore event policy for the bucket {bucket}")
## end of the getting and configuring S3 event configuration 

## start of restoring objects

#If you were able to get the object, then this code does nothing. the user should be able to get the object without any issue.
# if the object status is invalid, then check the object metadata with the head call to the object metadata
def getObject(bucket, key):
    try:
        s3.get_object(
            Bucket = bucket,
            Key = key)
    # checking if bucket exist, else exit.
    except s3.exceptions.NoSuchBucket:
        logger.error (f"Bucket '{bucket}' does not exists. Exiting ...")
        sys.exit()
    #check to see if key provided exists, else exit.
    except s3.exceptions.NoSuchKey:
        logger.info (f"{key} does not exists in the {bucket}")
        sys.exit()
    # if get call returns InvalidObjectState error is returned, make HeadObject call to check Archive state
    except s3.exceptions.InvalidObjectState:
        logger.error (f"the object '{key}' in the bucket '{bucket}' is in Invalid Object state, ... checking object status")
        headObject(bucket,key)
    else:
        logger.info (f"the object '{key}' in the bucket '{bucket}' is not in an S3 Intelligent Archive/Deep Archive storage class")
    #except ClientError as error:
        #logger.error{f"Please ensure the arguments are properly configured with the appropriate values"}
#Retriving object metadata to check its archive status.
# need to add a policy with To use HEAD, you must have READ access to the object.
def headObject(bucket, key):
    try:
        response = s3.head_object(
        Bucket = bucket,
        Key = key)
    #Checking if bucket exists. If not, exiting out
    except s3.exceptions.NoSuchBucket:
        logger.error (f"Bucket '{bucket}' does not exists. Exiting out ...")
        sys.exit()
    #else checking archive status
    logger.info(f"The object '{key}' is archived as '{response['ArchiveStatus']}' in an/a '{response['StorageClass']}' of an S3 storage")
    #find the status of x-amz-restore. If x-amz-restore does not exist, run RestoreObject call
    restoreStatus = response['ResponseMetadata']['HTTPHeaders'].get('x-amz-restore')
    # if object archive status is "DEEP_ARCHIVE_ACCESS" or "ARCHIVE_ACCESS"
    if response['ArchiveStatus'] == "DEEP_ARCHIVE_ACCESS" or response['ArchiveStatus'] == "ARCHIVE_ACCESS":
        # 'x-amz-restore" does not exists then restore object.
        if restoreStatus is None:
            executeRestore(bucket, key,response['ArchiveStatus'])
        # if restore status is true, restore is in progress    
        elif restoreStatus == 'ongoing-request="true"':
            logger.info(f"A restore of an Object '{key}' is already in progress")
        # if restore status is false, object is already restored. 
        else:
            logger.info(f"An object '{key}' is already restored")
    #return response['ArchiveStatus'], response['StorageClass']

#To use this operation, you must have permissions to perform the s3:RestoreObject action
def executeRestore(bucket, key,restoreStatus): 
    #adding/appending/updating S3 event configuration for the S3 bucket for restoring object.
    addOrUpdateS3Event(bucketName,key)
    if restoreStatus == "DEEP_ARCHIVE_ACCESS":
            logger.info(f"Restoring an object {key} from the'DEEP_ARCHIVE_ACCESS' tier to S3 INT FA. It will be back into Amazon S3 within 12 hours")
    else:
        logger.info(f"Restoring an object {key} from the'ARCHIVE_ACCESS' tier to S3 INT FA.It will be back into Amazon S3 INT FA within 3-5 hours")
#restoring an object from the S3 INT Archive/Deep Archive Access.
    try:
        s3.restore_object(
            Bucket=bucket,
            Key=key,
            RestoreRequest={})
    except s3.exceptions.ObjectAlreadyInActiveTierError:
        logger.error(f"Restore action is not allowed against this storage tier {restoreStatus}.")

### end of restoring S3 objects 


def main():
    getObject(bucketName,key) # getObject calls headObject which calls executeRestore.


if __name__ == "__main__":
    main()


