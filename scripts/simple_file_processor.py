import sys

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    concat_ws,
    current_timestamp,
    lit,
    month,
    regexp_replace,
    to_date,
    trim,
    upper,
    when,
    year,
)


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: simple_file_processor.py <source-s3-uri> <destination-s3-prefix>",
            file=sys.stderr,
        )
        return 1

    source_path = sys.argv[1]
    destination_path = sys.argv[2]

    spark = SparkSession.builder.appName("simple-insurance-processor").getOrCreate()

    quotes_df = (
        spark.read.option("header", True)
        .option("inferSchema", True)
        .csv(source_path)
    )

    normalized_df = quotes_df.select(
        trim(col("quote_id")).alias("quote_id"),
        trim(col("prospect_id")).alias("prospect_id"),
        trim(col("first_name")).alias("first_name"),
        trim(col("middle_name")).alias("middle_name"),
        trim(col("last_name")).alias("last_name"),
        upper(trim(col("status"))).alias("status"),
        col("premium").cast("double").alias("premium"),
        trim(col("phone")).alias("phone"),
        col("vehicle_count").cast("int").alias("vehicle_count"),
        upper(trim(col("state"))).alias("state"),
        to_date(col("quote_date")).alias("quote_date"),
    )

    transformed_df = (
        normalized_df.withColumn(
            "full_name",
            concat_ws(" ", col("first_name"), col("middle_name"), col("last_name")),
        )
        .withColumn(
            "premium_tier",
            when(col("premium") >= 1500, lit("PREMIUM"))
            .when(col("premium") >= 1000, lit("STANDARD"))
            .otherwise(lit("BASIC")),
        )
        .withColumn(
            "risk_score",
            when(col("status") == "BOUND", lit(20))
            .when(col("status") == "QUOTED", lit(45))
            .otherwise(lit(70))
            + when(col("premium") >= 1500, lit(15)).otherwise(lit(5))
            + when(col("vehicle_count") > 1, lit(10)).otherwise(lit(0)),
        )
        .withColumn("phone_clean", regexp_replace(col("phone"), "[^0-9]", ""))
        .withColumn(
            "multi_policy_indicator",
            when(col("vehicle_count") > 1, lit("Y")).otherwise(lit("N")),
        )
        .withColumn("quote_year", year(col("quote_date")))
        .withColumn("quote_month", month(col("quote_date")))
        .withColumn("data_source", lit("MANUAL_TEST"))
        .withColumn("processed_at", current_timestamp())
    )

    result_df = transformed_df.filter(col("quote_id").isNotNull() & col("premium").isNotNull())

    record_count = result_df.count()

    result_df.write.mode("overwrite").partitionBy("quote_year", "quote_month").parquet(destination_path)

    print(
        f"Processed {record_count} insurance quote rows from {source_path} to {destination_path}"
    )

    spark.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())