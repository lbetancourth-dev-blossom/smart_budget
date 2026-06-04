-- smart_budget_monthly_spend.sql
-- Extrae el gasto mensual agregado por miembro y categoría desde fact_transactions.
--
-- Fuente : blossom-dough-consolidated-alpha · schema public
-- Grain  : (idmember, defaultcategory, period_yyyymm)
-- Output : base para smart_budget_synthetic_idmember.csv y para el pipeline batch
--
-- Reglas de filtrado aplicadas (equivalentes a filters.py):
--   1. deletedat IS NULL                      → excluir soft-deleted
--   2. incomeexpenditure = 'expenditure'      → solo gastos
--   3. defaultcategory NOT IN (exclusiones)   → categorías válidas
--   4. idtransaction NOT LIKE 'LOAN%'         → excluir pagos de préstamos
--   5. SUB%: status IS NULL OR NOT IN (PENDING, HOLD)
--   6. EXT%: UPPER(status) = 'POSTED'
--
-- Resolución de idmember:
--   fact_transactions.idaccount → bridge_member_account.idaccount → idmember
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
        -- idcategory como proxy del nombre de categoría (sin catálogo en Fase 0)
        ft.defaultcategory                       AS idcategory,
        ft.defaultcategory,
        TO_CHAR(ft.date, 'YYYY-MM')              AS period_yyyymm,
        -- Suma neta clampeada a 0: reembolsos no generan montos negativos
        GREATEST(0, SUM(ft.amount::NUMERIC))     AS monthly_total
    FROM public.fact_transactions ft
    JOIN public.bridge_member_account bma
        ON ft.idaccount::TEXT = bma.idaccount::TEXT
    WHERE
        -- Regla 1: excluir soft-deleted
        ft.deletedat IS NULL

        -- Regla 2: solo gastos (no ingresos ni transferencias internas)
        AND LOWER(ft.incomeexpenditure) = 'expenditure'

        -- Regla 3: categorías válidas
        AND ft.defaultcategory IS NOT NULL
        AND UPPER(ft.defaultcategory) NOT IN ('UNCATEGORIZED', 'INCOME', 'MONEY_SENT')

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
        ft.defaultcategory,
        period_yyyymm
)

SELECT
    idclient,
    idcompany,
    idmember,
    idaccount,
    idcategory,
    defaultcategory,
    period_yyyymm,
    monthly_total
FROM base
-- Descomentar para limitar ventana temporal (reemplazar N):
-- WHERE period_yyyymm >= TO_CHAR(NOW() - INTERVAL 'N months', 'YYYY-MM')
ORDER BY
    idmember,
    period_yyyymm,
    defaultcategory
