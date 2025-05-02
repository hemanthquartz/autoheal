def wait_for_execution_to_run(stepfunction_arn, timeout=500, msgid=None, db_conn=None):
    sf_client = boto3.client('stepfunctions')
    start_time = time.time()

    while True:
        try:
            response = sf_client.list_executions(
                stateMachineArn=stepfunction_arn,
                statusFilter='RUNNING'
            )

            print(response)

            if response['executions']:
                return response['executions'][0]['executionArn']

            if time.time() - start_time > timeout:
                # Before raising Exception, check in DB table tib_tran_logs
                cursor = db_conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM tib_tran_logs WHERE messageid = %s", (msgid,))
                result = cursor.fetchone()
                cursor.close()

                if result and result[0] > 0:
                    # messageid exists, don't raise exception, return response
                    return response
                else:
                    raise Exception("Timeout reached: Step function did not go into Running state")

            else:
                time.sleep(1)

        except Exception as e:
            logger.error("Error listing executions {}".format(repr(e)))
            raise Exception("Error listing executions: {}".format(repr(e)))