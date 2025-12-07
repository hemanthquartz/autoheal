if bma_dates:
    merge_sql = """
        MERGE INTO APPL_MNTH_END_SCH target
        USING (SELECT 'BMA' AS PRCS_NAME,
                      TO_DATE(:1,'MM/DD/YYYY') AS PRCS_DATE
               FROM dual) src
        ON (target.PRCS_NAME = src.PRCS_NAME
            AND target.PRCS_DATE = src.PRCS_DATE)
        WHEN NOT MATCHED THEN
            INSERT (PRCS_NAME, PRCS_DATE, PRCS_FLAG, STATUS,
                    REC_CREN_DT, REC_CREN_USR_ID,
                    REC_LAST_UPD_DT, REC_LAST_UPD_USR_ID)
            VALUES ('BMA', src.PRCS_DATE,
                    'Y','N',SYSDATE,USER,SYSDATE,USER)
    """

    inserted_count = 0   # <---- NEW: track ONLY new inserts

    for d in bma_dates:
        cur.execute(merge_sql, [d])
        if cur.rowcount == 1:
            inserted_count += 1

    print(f"Merge complete – {inserted_count} NEW BMA dates inserted automatically.")

else:
    print("****** No BMA calendar dates to process ******")