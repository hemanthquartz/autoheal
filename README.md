{
  "workflowId": "wf-single-job-20260429",
  "jobName": "simple-file-process",
  "virtualClusterId": "REPLACE_WITH_DATATEAM_A_VIRTUAL_CLUSTER_ID",
  "executionRoleArn": "REPLACE_WITH_DATATEAM_A_EXEC_ROLE_ARN",
  "releaseLabel": "emr-7.5.0-latest",
  "entryPoint": "s3://REPLACE_WITH_BUCKET/manual-test/scripts/simple_file_processor.py",
  "entryPointArguments": [
    "s3://REPLACE_WITH_BUCKET/manual-test/input/source.csv",
    "s3://REPLACE_WITH_BUCKET/manual-test/output/"
  ],
  "sparkSubmitParameters": "--conf spark.executor.instances=1 --conf spark.executor.memory=1G --conf spark.driver.memory=1G --conf spark.executor.cores=1",
  "logUriPrefix": "s3://REPLACE_WITH_BUCKET/manual-test/logs",
  "description": "Single-step-function single-job manual EMR on EKS test"
}
