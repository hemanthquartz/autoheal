def main():
    bma_dates = get_bma_dates(holidays_file)

    if not bma_dates:
        print("***** No BMA calendar dates to process *****")
        return

    # ---------------------------------------------
    # 1. Extract distinct years from file
    # ---------------------------------------------
    bma_years = sorted({d.split("/")[-1] for d in bma_dates})

    print(f"BMA Years identified from file: {', '.join(bma_years)}")

    cur = essdb_con.cursor()

    # ---------------------------------------------
    # 2. Delete existing records for those years only
    # ---------------------------------------------
    delete_sql = """
        DELETE FROM APPL_MNTH_END_SCH
        WHERE PRCS_NAME = 'BMA'
        AND EXTRACT(YEAR FROM PRCS_DATE) = :1
    """

    deleted_count = 0
    for year in bma_years:
        cur.execute(delete_sql, [year])
        deleted_count += cur.rowcount

    # ---------------------------------------------
    # 3. Insert all BMA dates from file
    # ---------------------------------------------
    insert_sql = """
        INSERT INTO APPL_MNTH_END_SCH (
            PRCS_NAME,
            PRCS_DATE,
            PRCS_FLAG,
            STATUS,
            REC_CREN_DT,
            REC_CREN_USR_ID,
            REC_LAST_UPD_DT,
            REC_LAST_UPD_USR_ID
        )
        VALUES (
            'BMA',
            TO_DATE(:1, 'MM/DD/YYYY'),
            'Y',
            'N',
            SYSDATE,
            USER,
            SYSDATE,
            USER
        )
    """

    inserted_count = 0
    for d in bma_dates:
        cur.execute(insert_sql, [d])
        inserted_count += 1

    # ---------------------------------------------
    # 4. Commit once
    # ---------------------------------------------
    essdb_con.commit()

    # ---------------------------------------------
    # 5. Final audit log
    # ---------------------------------------------
    print(
        f"BMA calendar refresh complete | "
        f"Years processed: {', '.join(bma_years)} | "
        f"Rows deleted: {deleted_count} | "
        f"Rows inserted: {inserted_count}"
    )