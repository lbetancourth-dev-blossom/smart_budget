-- smart_budget_monthly_spend.sql
--
-- Query de extracción mantenida por Data Engineering (Dough).
-- Fuente canónica: https://github.com/homecu/dwh_dough/blob/main/QA%20scripts/category_expenditure_per_month.sql
--
-- Materializa la tabla Glue:
--   dlh_gold_dough_dev.smart_budget_transactions
--
-- Output grain: (idclient, idcompany, idmember, idaccount, category_id, category_name,
--                type_category, txn_month, total_amount, year, month)
--
-- El endpoint Smart Budget consulta esta tabla directamente via Athena/pyathena.
-- No modificar esta query sin coordinar con el equipo DE (Dough).

WITH olbbusinessuser_dedup AS (
    SELECT *
    FROM (
        SELECT *,
            ROW_NUMBER() OVER (PARTITION BY idolbuser ORDER BY createdat DESC) AS rn
        FROM "AwsDataCatalog"."dlh_silver_olb_dev"."olbbusinessuser"
    )
    WHERE rn = 1
),

bridge_member_account AS (
    -- Personal accounts
    SELECT
        CAST(ua.idolbuser AS VARCHAR) AS idmember,
        CONCAT('INT', CAST(ua.idolbaccountnumber AS VARCHAR)) AS idaccount,
        '1' AS idclient,
        CAST(SUBSTR(CAST(ua.createdat AS VARCHAR), 1, 10) AS DATE) AS createdat,
        CAST(SUBSTR(CAST(ua.deletedat AS VARCHAR), 1, 10) AS DATE) AS deletedat
    FROM "AwsDataCatalog"."dlh_silver_olb_dev"."olbuseraccount" AS ua

    UNION ALL

    -- Business accounts
    SELECT
        CAST(bu_dedup.idolbuser AS VARCHAR) AS idmember,
        CONCAT('INT', CAST(btn.idolbaccountnumber AS VARCHAR)) AS idaccount,
        '1' AS idclient,
        CAST(SUBSTR(CAST(btn.createdat AS VARCHAR), 1, 10) AS DATE) AS createdat,
        CAST(SUBSTR(CAST(btn.deletedat AS VARCHAR), 1, 10) AS DATE) AS deletedat
    FROM "AwsDataCatalog"."dlh_silver_olb_dev"."olbbusinesstinaccountnumber" AS btn
    LEFT JOIN olbbusinessuser_dedup AS bu_dedup
        ON btn.idolbbusiness = bu_dedup.idolbbusiness

    UNION ALL

    -- External accounts (Dough)
    SELECT
        CAST(m.externalid AS VARCHAR) AS idmember,
        CONCAT('EXT', CAST(ma.idaccount AS VARCHAR)) AS idaccount,
        '1' AS idclient,
        CAST(SUBSTR(CAST(ma.createdat AS VARCHAR), 1, 10) AS DATE) AS createdat,
        CAST(SUBSTR(CAST(ma.deletedat AS VARCHAR), 1, 10) AS DATE) AS deletedat
    FROM "AwsDataCatalog"."dlh_silver_dough_dev"."memberaccount" AS ma
    LEFT JOIN "AwsDataCatalog"."dlh_silver_dough_dev"."member" AS m
        ON ma.idmember = m.id
),

fact_transactions AS (

    -- SUB transactions
    SELECT
        CONCAT('SUB', CAST(t.id AS VARCHAR)) AS idtransaction,
        '1' AS idclient,
        split_part(t.transactioncomplete, '-', 1) AS idcompany,
        CONCAT('INT', CAST(s.idolbaccountnumber AS VARCHAR)) AS idaccount,
        CAST(SUBSTR(CAST(t.date AS VARCHAR), 1, 10) AS DATE) AS date,
        CAST(t.amount AS DOUBLE) AS amount,
        CASE WHEN CAST(t.amount AS DOUBLE) < 0 THEN 'expenditure' ELSE 'income' END AS incomeexpenditure,
        olbtransactioncategory.name AS default_category_name,
        CAST(olbtransactioninfo.idolbtransactioncategory AS VARCHAR) AS default_category_id,
        CONCAT('CMP:', CAST(t.idolbtransactioninfo AS VARCHAR)) AS uct_join_key
    FROM "AwsDataCatalog"."dlh_silver_olb_dev"."olbsubaccounttransaction" AS t
    LEFT JOIN "AwsDataCatalog"."dlh_silver_olb_dev"."olbsubaccount" AS s
        ON t.idsubaccount = s.id
    LEFT JOIN "AwsDataCatalog"."dlh_silver_olb_dev"."olbtransactioninfo" AS olbtransactioninfo
        ON t.idolbtransactioninfo = olbtransactioninfo.id
    LEFT JOIN "AwsDataCatalog"."dlh_silver_olb_dev"."olbtransactioncategory" AS olbtransactioncategory
        ON olbtransactioninfo.idolbtransactioncategory = olbtransactioncategory.id

    UNION ALL

    -- EXTERNAL transactions (Dough)
    SELECT
        CONCAT('EXT', CAST(t.id AS VARCHAR)) AS idtransaction,
        '1' AS idclient,
        CAST(company.externalid AS VARCHAR) AS idcompany,
        CONCAT('EXT', CAST(t.idaccount AS VARCHAR)) AS idaccount,
        CAST(SUBSTR(CAST(t.processdate AS VARCHAR), 1, 10) AS DATE) AS date,
        CAST(t.amount AS DOUBLE) AS amount,
        CASE WHEN CAST(t.amount AS DOUBLE) < 0 THEN 'expenditure' ELSE 'income' END AS incomeexpenditure,
        CAST(NULL AS VARCHAR) AS default_category_name,
        CAST(NULL AS VARCHAR) AS default_category_id,
        CONCAT('EXT:', CAST(t.id AS VARCHAR)) AS uct_join_key
    FROM "AwsDataCatalog"."dlh_silver_dough_dev"."externaltransaction" AS t
    LEFT JOIN "AwsDataCatalog"."dlh_silver_dough_dev"."account" AS acct
        ON t.idaccount = acct.id
    LEFT JOIN "AwsDataCatalog"."dlh_silver_dough_dev"."companyaccountsubtype" AS ast
        ON acct.idcompanyaccountsubtype = ast.id
    LEFT JOIN "AwsDataCatalog"."dlh_silver_dough_dev"."companytypeaccount" AS cta
        ON ast.idcompanytypeaccount = cta.id
    LEFT JOIN "AwsDataCatalog"."dlh_silver_dough_dev"."memberaccount" AS memberaccount
        ON t.idaccount = memberaccount.idaccount
    LEFT JOIN "AwsDataCatalog"."dlh_silver_dough_dev"."member" AS member
        ON memberaccount.idmember = member.id
    LEFT JOIN "AwsDataCatalog"."dlh_silver_dough_dev"."company" AS company
        ON member.idcompany = company.id
        AND company.idclient = 1
    WHERE LOWER(cta.name) != 'credit'
       OR cta.name IS NULL
),

expenditure_with_member AS (
    SELECT
        ft.*,
        bma.idmember
    FROM fact_transactions ft
    LEFT JOIN bridge_member_account bma
        ON ft.idaccount = bma.idaccount
        AND ft.idclient = bma.idclient
        AND ft.date >= bma.createdat
        AND (bma.deletedat IS NULL OR ft.date <= bma.deletedat)
    WHERE ft.incomeexpenditure = 'expenditure'
),

active_uct AS (
    SELECT
        CASE
            WHEN uct.idcompanytransaction IS NOT NULL
                THEN CONCAT('CMP:', CAST(uct.idcompanytransaction AS VARCHAR))
            WHEN uct.idexternaltransaction IS NOT NULL
                THEN CONCAT('EXT:', CAST(uct.idexternaltransaction AS VARCHAR))
        END AS uct_join_key,
        CAST(uct.amount AS DOUBLE) AS uct_amount,
        CAST(uct.idcategory AS VARCHAR) AS dough_category_id,
        CAST(uct.iddefaultcategory AS VARCHAR) AS dough_default_category_id,
        cat.name AS dough_category_name,
        dc.name AS dough_default_category_name
    FROM "AwsDataCatalog"."dlh_silver_dough_dev"."usercategorytransaction" uct
    LEFT JOIN "AwsDataCatalog"."dlh_silver_dough_dev"."category" cat
        ON uct.idcategory = cat.id
    LEFT JOIN "AwsDataCatalog"."dlh_silver_dough_dev"."defaultcategory" dc
        ON uct.iddefaultcategory = dc.id
    WHERE uct.deletedat IS NULL
),

categorized_expenditures AS (

    -- Dough categories
    SELECT
        ewm.idclient,
        ewm.idcompany,
        ewm.idmember,
        COALESCE(
            auct.dough_category_id,
            auct.dough_default_category_id
        ) AS category_id,
        COALESCE(
            auct.dough_category_name,
            auct.dough_default_category_name
        ) AS category_name,
        CASE
            WHEN auct.dough_category_name IS NOT NULL
                THEN 'Dough'
            ELSE 'defaultDough'
        END AS type_category,
        ewm.date,
        auct.uct_amount AS amount
    FROM expenditure_with_member ewm
    INNER JOIN active_uct auct
        ON auct.uct_join_key = ewm.uct_join_key
    WHERE COALESCE(
        auct.dough_category_name,
        auct.dough_default_category_name
    ) IS NOT NULL

    UNION ALL

    -- Fallback to OLB category
    SELECT
        ewm.idclient,
        ewm.idcompany,
        ewm.idmember,
        ewm.default_category_id AS category_id,
        ewm.default_category_name AS category_name,
        'defaultOLB' AS type_category,
        ewm.date,
        ewm.amount
    FROM expenditure_with_member ewm
    WHERE ewm.default_category_name IS NOT NULL
      AND NOT EXISTS (
            SELECT 1
            FROM active_uct auct
            WHERE auct.uct_join_key = ewm.uct_join_key
      )
)

SELECT
    idclient,
    idcompany,
    idmember,
    category_id,
    category_name,
    type_category,
    DATE_FORMAT(date, '%Y-%m') AS txn_month,
    ABS(SUM(amount)) AS total_amount
FROM categorized_expenditures
WHERE idmember IS NOT NULL
  AND category_name IS NOT NULL
GROUP BY
    idclient,
    idcompany,
    idmember,
    category_id,
    category_name,
    type_category,
    DATE_FORMAT(date, '%Y-%m')
ORDER BY
    idmember,
    txn_month,
    category_name,
    idcompany;