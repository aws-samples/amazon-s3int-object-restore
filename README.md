## restoreS3INTObject
Code to restore an object from the S3 Intelligent's Archive and Deep Archive Access Tier.

Implementation Overview:

Customers make GetObject call
If HTTP 403 InvalidObjectState error is returned, make HeadObject call to check Archive state
If x-amz-archive-access = DEEP_ARCHIVE_ACCESS, check x-amz-restore
If x-amz-restore does not exist, send RestoreObject call
Before restoring, the code checks if any other S3 events is configured on a bucket -
5a. First getting the current S3 event configuration for the bucket. It could be null or have some S3 events configured such as put, copy or even restore.

5b.Adding or appending S3 event configuration of the bucket with 's3:ObjectRestore:Post', 's3:ObjectRestore:Completed' if it is not configured

**scenario #1: If no S3 event is configured, it adds the s3 events for S3 restore initiation and completed.**

**Scenario #2: Check if either of 's3:ObjectRestore:Post' or/and 's3:ObjectRestore:Completed' are not configured on the bucket.**

  Create a list of missing S3 restore events 
  
    I. if Topic Configuration exists, append the existing Topic Configuration with the S3 retore event from the list and keep rest of the S3 event policy unchanged.
             
    II. if Topic Configuration does not exist, add new topic Configuration with the S3 retore event from the list and keep rest of the S3 event policy unchanged.   
Else If x-amz-restore = true, a restore is already in progress
Else If x-amz-restore = false, object is already restored and the expiry date is also returned in this field (this shouldn’t happen if 2 occurred, but should probably be in the code just in case)
Here is the command to run the code for restoring an object from the S3 Intelligent Archive and Deep Archive Access tier - restoreS3IntArchive.py bucketname prefix/key SNSArn. Ex: restoreS3IntArchive.py 's3bucket' 'nothingtoseehere/nothing.csv0030part00' 'arn:aws:sns:us-east-1:123456789123:restore'.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.

