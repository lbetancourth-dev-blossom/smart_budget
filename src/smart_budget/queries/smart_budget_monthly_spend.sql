-- smart_budget_monthly_spend.sql
-- DEFINICIÓN DE FUENTE para la tabla Glue dlh_gold_dough_dev.smart_budget_transactions.
-- Este SQL define la transformación que materializa la tabla Glue.
-- El endpoint ahora consulta directamente dlh_gold_dough_dev.smart_budget_transactions via pyathena.
--
-- Fuente : dlh_gold_dough_dev.smart_budget_transactions (Athena/Glue)
-- Grain  : (idmember, idcategory, iddefaultcategory, period_yyyymm)
--
-- Reglas de filtrado aplicadas (equivalentes a filters.py):
--   1. deletedat IS NULL                      → excluir soft-deleted
--   2. incomeexpenditure = 'expenditure'      → solo gastos
--   3. categoryname NOT IN (exclusiones)      → categorías válidas (desde fmtc)
--   4. idtransaction NOT LIKE 'LOAN%'         → excluir pagos de préstamos
--   5. SUB%: status IS NULL OR NOT IN (PENDING, HOLD)
--   6. EXT%: UPPER(status) = 'POSTED'
--
-- Convención de signos confirmada en blossom-dough-consolidated-alpha:
--   OLB (SUB%)  / OTHER: expenditure = NEGATIVO (débito OLB = negativo).
--                        → ABS() normaliza a positivo antes de sumar.
--   EXT (EXT%)          : no hay filas EXT en esta DB (datos solo OLB/OTHER).
--                        Si en el futuro aparecen, ABS() es no-op sobre positivos.
--   income negativos    : ajustes/créditos internos — excluidos por el filtro
--                        incomeexpenditure = 'expenditure'.
--   GREATEST(0, ...)    : clamp de seguridad para el caso en que SUM sea negativo.
--
-- Resolución de idmember:
--   fact_transactions.idaccount → bridge_member_account.idaccount → idmember
--
-- Resolución de categoría:
--   fact_transactions.idtransaction → fact_member_transaction_category.idtransaction
--   → idcategory, iddefaultcategory, categoryname, categorygroupname
--
-- Parámetro opcional de ventana temporal:
--   Descomentar el WHERE de la CTE outer para limitar a los últimos N meses.
--   Ejemplo para 12 meses:
--     WHERE period_yyyymm >= TO_CHAR(NOW() - INTERVAL '12 months', 'YYYY-MM')

WITH base AS (
    SELECT
        ft.idclient,
        ft.idcompany,
        bma.idmember,
        ft.idaccount,
        -- Categoría resuelta desde fact_member_transaction_category por idtransaction
        fmtc.idcategory,
        fmtc.iddefaultcategory,
        fmtc.categoryname,
        fmtc.categorygroupname,
        TO_CHAR(ft.date, 'YYYY-MM')                       AS period_yyyymm,
        -- ABS() normaliza el signo: OLB/OTHER guardan gastos como NEGATIVOS (confirmado).
        -- SUM() acumula el gasto neto del mes.
        -- GREATEST(0, ...) clampea a 0 si el neto resultara negativo.
        GREATEST(0, SUM(ABS(ft.amount::NUMERIC)))         AS monthly_total
    FROM public.fact_transactions ft
    JOIN public.bridge_member_account bma
        ON ft.idaccount::TEXT = bma.idaccount::TEXT
    -- LEFT JOIN para no perder transacciones sin categoría asignada
    -- (categorías huérfanas: loguear warning en pipeline, no excluir silenciosamente)
    LEFT JOIN public.fact_member_transaction_category fmtc
        ON ft.idtransaction = fmtc.idtransaction
    WHERE
        -- Regla 1: excluir soft-deleted
        ft.deletedat IS NULL

        -- Regla 2: solo gastos (no ingresos ni transferencias internas)
        AND LOWER(ft.incomeexpenditure) = 'expenditure'

        -- Regla 3: categorías válidas (filtro sobre categoryname del join)
        AND fmtc.categoryname IS NOT NULL
        AND UPPER(fmtc.categoryname) NOT IN ('UNCATEGORIZED', 'INCOME', 'MONEY_SENT')

        -- Regla 4: excluir pagos de préstamos (obligación fija, no gasto discrecional)
        AND ft.idtransaction NOT LIKE 'LOAN%'

        -- Reglas 5 y 6: filtro de estado por origen de la transacción
        AND (
            -- OLB (SUB%): estado nulo o no PENDING / HOLD
            (
                ft.idtransaction LIKE 'SUB%'
                AND (ft.status IS NULL OR UPPER(ft.status) NOT IN ('PENDING', 'HOLD'))
            )
            OR
            -- Externas Dough vía Plaid / Finicity (EXT%): solo POSTED
            (
                ft.idtransaction LIKE 'EXT%'
                AND UPPER(ft.status) = 'POSTED'
            )
            OR
            -- Prefijos desconocidos: pasar sin filtro de estado (no data loss silencioso)
            (
                ft.idtransaction NOT LIKE 'SUB%'
                AND ft.idtransaction NOT LIKE 'EXT%'
                AND ft.idtransaction NOT LIKE 'LOAN%'
            )
        )
    GROUP BY
        ft.idclient,
        ft.idcompany,
        bma.idmember,
        ft.idaccount,
        fmtc.idcategory,
        fmtc.iddefaultcategory,
        fmtc.categoryname,
        fmtc.categorygroupname,
        period_yyyymm
)

SELECT
    idclient,
    idcompany,
    idmember,
    idaccount,
    idcategory,
    iddefaultcategory,
    categoryname,
    categorygroupname,
    period_yyyymm,
    monthly_total
FROM base
-- Descomentar para limitar ventana temporal (reemplazar N):
-- WHERE period_yyyymm >= TO_CHAR(NOW() - INTERVAL 'N months', 'YYYY-MM')
ORDER BY
    idmember,
    period_yyyymm,
    categoryname
