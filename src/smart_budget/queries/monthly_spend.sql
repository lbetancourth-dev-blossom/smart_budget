-- Smart Budget Fase 0 — Agregación mensual de gasto
-- Fuente: manualtransaction + manualaccount
-- Output: (id_member, category_id, year_month, monthly_amount)
--
-- PARÁMETROS (sustituir antes de ejecutar):
--   :id_client    → VARCHAR  — filtra por cliente
--   :id_company   → VARCHAR  — filtra por CU
--   :start_date   → DATE     — primer mes de la ventana (YYYY-MM-01)
--   :end_date     → DATE     — primer día del mes en curso (excluido)
--   :n_months     → INT      — ventana de meses (default 6, rango 3-24)

WITH expense_categories AS (
    -- Categorías válidas: tipo Expense, visibles, no eliminadas
    SELECT id AS category_id
    FROM   defaultcategory
    WHERE  idcategorygroup = 1           -- solo Expense
      AND  shouldshow      = TRUE
      AND  deletedat       IS NULL
      AND  name            != 'Uncategorized'
),

active_accounts AS (
    SELECT id AS idmanualaccount,
           idmember
    FROM   manualaccount
    WHERE  deletedat IS NULL
      AND  idmember  IS NOT NULL
),

filtered_transactions AS (
    -- manualtransaction: no tiene status/type, se filtra por categoría y fecha
    SELECT
        mt.id                                                AS tx_id,
        aa.idmember,
        mt.idcategory                                        AS category_id,
        DATE_TRUNC('month', mt.processdate::DATE)::DATE      AS month_start,
        GREATEST(mt.amount, 0)                               AS amount  -- clamp reembolsos a 0
    FROM   manualtransaction mt
    JOIN   active_accounts  aa  ON mt.idmanualaccount = aa.idmanualaccount
    JOIN   expense_categories ec ON mt.idcategory      = ec.category_id
    WHERE  mt.deletedat   IS NULL
      AND  mt.amount      >  0
      AND  mt.processdate >= :start_date
      AND  mt.processdate <  :end_date
),

monthly_spend AS (
    -- Suma de gasto por member × categoría × mes calendario
    SELECT
        idmember,
        category_id,
        TO_CHAR(month_start, 'YYYY-MM')  AS year_month,
        SUM(amount)                      AS monthly_amount
    FROM   filtered_transactions
    GROUP  BY idmember, category_id, month_start
)

SELECT
    idmember,
    category_id,
    year_month,
    ROUND(monthly_amount::NUMERIC, 2) AS monthly_amount
FROM   monthly_spend
ORDER  BY idmember, category_id, year_month;
