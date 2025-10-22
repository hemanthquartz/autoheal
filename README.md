from pyspark.sql.types import StringType
from pyspark.sql.functions import expr

def _hextoascii3(hex_string: str) -> str:
    if not hex_string:
        return None
    s = hex_string.strip()
    # Robustness: keep only hex chars and make length even
    import re
    s = ''.join(re.findall(r'[0-9A-Fa-f]', s))
    if len(s) % 2 == 1:
        s = '0' + s
    try:
        return bytes.fromhex(s).decode('utf-8', errors='ignore')
    except Exception:
        # Fallback: return best-effort ASCII
        try:
            return bytes.fromhex(s).decode('latin-1', errors='ignore')
        except Exception:
            return None

spark.udf.register("hextoascii3", _hextoascii3, StringType())

def parse_quote_object(table, max_timestamp, refresh_type):
    st = spark.sql(f"""
        SELECT
            qte_policy_tran_id AS tran_id,
            workflow_step_nm,
            create_ts,
            update_ts,
            CAST(REGEXP_REPLACE(SUBSTR(CAST(update_ts AS STRING),1,7),'-','') AS INT) AS p_ym,
            hextoascii3(cached_data) AS quote_object
        FROM {table}
    """).where(f"p_ym >= {max_timestamp}")

    return st