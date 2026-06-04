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
        -- idcategory resuelto desde el catálogo: defaultcategory.name → defaultcategory.id
        -- NULL si la categoría no existe en el catálogo (ej: categorías legacy sin mapeo)
        dc.id                                             AS idcategory,
        ft.defaultcategory,
        TO_CHAR(ft.date, 'YYYY-MM')                       AS period_yyyymm,
        -- ABS() normaliza el signo: OLB/OTHER guardan gastos como NEGATIVOS (confirmado).
        -- SUM() acumula el gasto neto del mes.
        -- GREATEST(0, ...) clampea a 0 si el neto resultara negativo.
        GREATEST(0, SUM(ABS(ft.amount::NUMERIC)))         AS monthly_total
    FROM public.fact_transactions ft
    JOIN public.bridge_member_account bma
        ON ft.idaccount::TEXT = bma.idaccount::TEXT
    -- LEFT JOIN para no perder transacciones cuya categoría no esté en el catálogo
    -- (categorías huérfanas: loguear warning en pipeline, no excluir silenciosamente)
    LEFT JOIN public.defaultcategory dc
        ON UPPER(dc.name) = UPPER(ft.defaultcategory)
        AND dc.deletedat IS NULL
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
        dc.id,
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
