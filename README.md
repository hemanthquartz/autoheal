To get the count of quote_id from your Athena table, use one of the following depending on what you need:

1️⃣ Total number of rows (including duplicates)

SELECT COUNT(quote_id) AS quote_id_count
FROM "insurance_master"."home_quote_master";

2️⃣ Count of unique (distinct) quote IDs ✅ (most commonly needed)

SELECT COUNT(DISTINCT quote_id) AS unique_quote_id_count
FROM "insurance_master"."home_quote_master";

3️⃣ Verify duplicates (optional but useful)

SELECT quote_id, COUNT(*) AS cnt
FROM "insurance_master"."home_quote_master"
GROUP BY quote_id
HAVING COUNT(*) > 1;

4️⃣ Count with a condition (example)

SELECT COUNT(DISTINCT quote_id)
FROM "insurance_master"."home_quote_master"
WHERE product = 'OHH';

If you tell me whether you want total vs unique or filtered by date / product / policy status, I’ll tailor the exact query.