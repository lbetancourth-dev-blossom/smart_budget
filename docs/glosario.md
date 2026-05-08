# Glosario — Smart Budget · Dough · Blossom

**Propósito:** referencia única de términos, acrónimos y conceptos que aparecen en la documentación del proyecto. Este documento se alimenta de forma incremental: cada vez que aparezca un término nuevo en una conversación o en un documento, se añade aquí.

**Cómo mantenerlo:**

- Orden estrictamente **alfabético** (mayúsculas y minúsculas se ignoran para el orden).
- Cada entrada sigue el formato:
  - **Término** *(acrónimo / expansión si aplica)*
  - Definición concisa.
  - Dónde aparece o por qué importa al proyecto.
  - Términos relacionados (opcional).
- Para añadir términos nuevos, simplemente pedirle a Claude algo como: *"Agrega al glosario los siguientes términos: X, Y, Z"* o *"De la conversación de hoy, ¿qué términos nuevos deberían entrar al glosario?"*.

**Última actualización:** 2026-05-08

---

## A

### Acceptance Rate
Métrica de Fase 0. Porcentaje de sugerencias de Smart Budget que el usuario acepta sin modificar el monto.
*Definición operativa:* match exacto entre `original_suggested_amount` y `final_user_amount`. Sin tolerancia.

### Account Details
Sección del Online Banking (OLB) de Blossom que muestra todas las transacciones de una cuenta (ATM, tarjeta, pagos, transferencias). Su fuente es el core bancario.
*Relacionado:* Activity, OLB.

### ACH *(Automated Clearing House)*
Red electrónica de pagos en EE.UU. usada para transferencias entre bancos. En Dough aparece como código de transacción (`ACH Credit`, `ACH Debit`).

### Activity
Sección del OLB de Blossom que muestra transacciones creadas dentro de la banca en línea (programadas, recurrentes, ejecutadas). Su fuente es la base de datos del OLB.
*Relacionado:* Account Details.

### Airflow
Orquestador de workflows usado para correr el pipeline batch de Smart Budget (cálculo nocturno o mensual de sugerencias).

### Assets
Cuentas que representan activos del miembro (ahorros, inversiones, propiedades). En Dough es una de las dos clasificaciones top-level (la otra es Liabilities). Suma al lado positivo del Net Worth.

---

## B

### Blossom
Empresa que provee la plataforma de servicios digitales sobre la que vive Dough. Es el `client` raíz en el modelo de datos.

### BlossomAPI
Capa de servicio (GraphQL/REST) entre la base de datos operativa (Dough DB) y los frontends. Es el canal por el que el modelo DS-ML expone las sugerencias y captura las decisiones del usuario.

### Bronze *(capa medallion)*
Primera capa del data lake. Contiene los datos crudos provenientes del CDC de DMS, incluyendo metadata de extracción (`_dms_operation`, `_dms_timestamp`, `_ingested_at`, `_run_id`, `_load_type`). No es la capa que usa Smart Budget.
*Relacionado:* Silver, Gold, DMS, CDC.

### Budget (Manual)
Funcionalidad de Dough en la que el miembro define manualmente cuánto quiere gastar por categoría. Es el "botón de al lado" frente al cual Smart Budget se posiciona.

---

## C

### Cancelled *(estado de transacción)*
Transacción que fue cancelada (ej. una transacción programada que el usuario anuló). **Se descarta** del cálculo de Smart Budget.

### CDC *(Change Data Capture)*
Patrón que captura cambios (insert/update/delete) en una base de datos en tiempo real para replicarlos a otro sistema. En Blossom se implementa con AWS DMS y alimenta la capa bronze.

### CD *(Certificate of Deposit)*
Tipo de cuenta a plazo fijo. Uno de los 4 subtipos soportados por Finicity (junto con checking, savings, money market).

### CFPB *(Consumer Financial Protection Bureau)*
Regulador estadounidense de servicios financieros al consumidor. Emite las reglas UDAAP y Section 1033 que aplican a Dough.

### Checking
Subtipo de cuenta corriente. Disponible en `defaultaccountsubtype` y `companyaccountsubtype`.

### Climb
Caso particular de Credit Union mencionado en la documentación. Tiene una versión de widget que solo permite filtrar hasta 1 año de data histórica.

### Coach *(Fase 3 de Smart Budget)*
Fase futura del roadmap. Permite señalar oportunidades sin prescribir (ej. "si mantienes este gasto, alcanzarás tu meta en 3 meses"). **Requiere revisión legal previa** por SEC/UDAAP.

### Confidence
Nivel de confianza de una sugerencia de Smart Budget en Fase 0. Tres niveles basados en cantidad de meses con data:
- `high` ≥ 6 meses
- `medium` 3–5 meses
- `low` 2 meses

### Contexto *(Fase 2 de Smart Budget)*
Fase futura. Incorpora estacionalidad, tendencia reciente y exclusión de outliers al cálculo de la sugerencia.

### Coverage
Métrica de Fase 0. Porcentaje de categorías del usuario que recibieron una sugerencia (mide suficiencia de data histórica).

### Credit Union *(CU)*
Cooperativa de crédito estadounidense — el cliente final que contrata Dough. En el modelo de datos es la entidad `company`. En EE.UU. sirven a 135 millones de miembros con $1.5T en activos (NCUA 2024).

---

## D

### Data Lake
Almacenamiento de datos crudos y semi-procesados (S3 en este caso). En Blossom se organiza con arquitectura medallion (bronze → silver → gold).

### Data Warehouse
Almacenamiento analítico de datos modelados (Redshift). Smart Budget lee de aquí para calcular las medianas mensuales.

### dbt *(data build tool)*
Herramienta de transformación de datos basada en SQL. Propuesta para implementar el pipeline de Smart Budget en silver/gold.

### DEP *(Deposit)*
Código de transacción para depósitos externos.

### Default Category
Categoría base global definida por Blossom (ej. "Auto & Transport", "Bills & Utilities"). Disponible en todas las CUs y no editable por el usuario. Vive en la tabla `defaultcategory`.
*Relacionado:* Custom Category, Enriched Grouped Category.

### DMS *(AWS Database Migration Service)*
Servicio de AWS que replica datos de bases operativas hacia el data lake mediante CDC. Los registros que llegan a bronze incluyen las columnas metadata (`_dms_operation`, etc.).

### Dough
Módulo de Personal Financial Management (PFM) de Blossom embebido en el OLB de las Credit Unions. Es read-only (no inicia movimientos de dinero, lo que limita su exposición regulatoria bajo Reg E).

### Dough DB
Base de datos operativa donde viven las transacciones, cuentas y configuraciones de Dough en tiempo real. Alimenta tanto el frontend (vía BlossomAPI) como el warehouse (vía streaming).

---

## E

### Edit Rate
Métrica de Fase 0. Porcentaje de sugerencias que el usuario modificó antes de confirmar. Señal de que la sugerencia llamó la atención del usuario aunque no la haya aceptado al pie de la letra.

### Enriched Grouped Category
Categorías devueltas por Ntropy/RICH. No se exponen directamente al usuario — se mapean a una `defaultcategory` mediante la tabla `companyntropycategory`.

### ETL *(Extract, Transform, Load)*
Pipeline que extrae datos de fuentes operativas, los transforma y los carga en un destino analítico.

### Expense
Tipo de categoría que representa gastos. **Es el único tipo que entra a Smart Budget** (Income y Other quedan fuera).

### External Transfers
Transacciones con una contraparte externa, normalmente entre instituciones. Se subdividen en:
- **External Incoming:** fondos que entran a una cuenta del miembro desde fuera (DEP, REF, INT, ACH credit).
- **External Outgoing:** fondos que salen hacia una entidad externa (POS, PMT, ACH debit, WDR).

---

## F

### Failed *(estado de transacción)*
Transacción que falló en su ejecución. **Se descarta** del cálculo de Smart Budget.

### Fase 0 *(El Reflejo)*
MVP de Smart Budget. Sugiere un monto por categoría usando la **mediana** del gasto histórico mensual del miembro. Si hay menos de 2 meses de historia → no sugiere.

### Fase 1 *(La Intención)*
Fase futura. El usuario declara una meta (mantener, reducir X% en categoría, ahorrar $Y) y la sugerencia se ajusta según esa intención.

### Fase 2 *(El Contexto)*
Fase futura. Ver "Contexto".

### Fase 3 *(El Coach)*
Fase futura. Ver "Coach".

### Feature Flag
Mecanismo de activación granular. En Dough hay tres principales:
- **Master Toggle (Dough):** ON/OFF del módulo completo.
- **RICH:** ON/OFF del enrichment de Ntropy.
- **Mobile widget:** ON/OFF del widget en mobile.

### FEE
Código de transacción para comisiones del sistema (cobros administrativos).

### Finicity
Solución enterprise de Mastercard para datos financieros. Soporta 4 tipos de cuenta: checking, savings, money market, CD. Es uno de los dos providers externos de Dough (el otro es Plaid). Hoy es el provider activo.

---

## G

### Gating
Regla que decide si se emite o no una sugerencia. En Smart Budget Fase 0: **si el miembro tiene menos de 2 meses con gasto en una categoría, no se sugiere** — el campo aparece vacío con mensaje explicativo.

### Gold *(capa medallion)*
Tercera y última capa del data lake. Pensada para datos curados, agregados y marts dimensionales. **Hoy está vacía** en `data/dough/gold/`. Es donde Smart Budget debería materializar sus salidas.
*Relacionado:* Bronze, Silver.

---

## I

### Income
Tipo de categoría que representa ingresos. **No entra a Smart Budget.**

### Intención *(Fase 1 de Smart Budget)*
Ver "Fase 1".

### Internal *(transacción)*
Movimiento de valor entre dos cuentas del mismo miembro (ej. checking → savings). **Se excluye del cálculo de Smart Budget** porque no representa consumo real.

---

## J

### Joint Accounts
Cuentas de titularidad compartida (común en cuentas business o familiares). Plantean preguntas abiertas para Smart Budget sobre granularidad del cálculo (member, account o grupo).

---

## L

### Liabilities
Cuentas que representan pasivos del miembro (préstamos, tarjetas de crédito, líneas de crédito). Una de las dos clasificaciones top-level. Resta al Net Worth.

### Loop de Retroalimentación
Feature transversal de Smart Budget. Captura `original_suggested_amount`, `final_user_amount`, timestamps y dirección del ajuste cada vez que un usuario interactúa con una sugerencia. Habilita que el modelo "aprenda" de las decisiones del usuario en fases futuras. **Crítico capturarlo desde Fase 0** — el costo de no tener este historial desde el inicio es alto.

---

## M

### Magic
Sistema de configuración de roles a nivel CU mencionado en la documentación de permisos. Define qué segmento de miembros tiene acceso a Dough.

### Manual Budget
Ver "Budget (Manual)".

### Master Toggle
Feature Flag principal de Dough. Si está OFF, el widget desaparece de la UI del usuario.

### Mediana
Estadístico que calcula el valor central de una distribución. **Es el método del modelo en Fase 0**: para cada `member × category`, se toma la mediana del gasto mensual de los últimos N meses.

### Medallion Architecture
Patrón de organización de un data lake en tres capas: **bronze** (raw), **silver** (limpia) y **gold** (curada/agregada).

### Member
Miembro de una Credit Union. Es el usuario final de Dough. En el modelo de datos: tabla `member`, FK `idcompany`. **Es la unidad mínima de cálculo de Smart Budget.**

### Member-to-Member
Movimiento de dinero entre dos miembros de la misma CU (P2P). **Se excluye del cálculo de Smart Budget**.

### Money Market
Subtipo de cuenta de mayor liquidez con tasas variables. Uno de los 4 tipos soportados por Finicity.

### Multi-tenancy
Aislamiento de datos entre clientes. En Dough es estricto: jerarquía `client → company (CU) → member → account → transaction`. **Toda query de Smart Budget debe filtrar por estos IDs**; nunca cruzar miembros o CUs.

---

## N

### Net Worth
Patrimonio neto del miembro. Fórmula: `Σ Assets − Σ Liabilities`. Es la métrica principal del módulo Overview de Dough.

### Ntropy
Proveedor de enriquecimiento de transacciones (categorías, comercios, logos). Su servicio se activa con el feature flag RICH. Devuelve categorías libres que Dough mapea a `defaultcategory` mediante `companyntropycategory`.

---

## O

### Off-book cards
Transacciones de tarjetas que no se alojan en el Core de Blossom (vienen de terceros).

### OLB *(Online Banking)*
Banca en línea de las Credit Unions. Es el contenedor donde vive Dough como widget.

### On-book cards
Transacciones de tarjetas que sí están en el Core de Blossom.

### Other *(tipo de categoría)*
Tipo de categoría que no es Expense ni Income (transferencias, ajustes). **No entra a Smart Budget.**

---

## P

### Pending *(estado de transacción)*
Transacción pendiente de ejecutar. Su monto o fecha pueden cambiar todavía. **Se excluye del cálculo de Smart Budget.**

### PFM *(Personal Financial Management)*
Categoría de productos digitales que ayudan a las personas a gestionar sus finanzas (ver gastos, presupuestos, metas). Dough es un PFM.

### Plaid
Proveedor líder de agregación financiera en EE.UU. (+12.000 instituciones soportadas). Uno de los dos providers externos de Dough (junto con Finicity). Hoy aparece como **inactivo** en la tabla `provider`.

### PMT *(Payment)*
Código de transacción para pagos a terceros (servicios, préstamos externos).

### POS *(Point of Sale)*
Código de transacción para compras en comercio.

### Posted *(estado de transacción)*
Transacción ya posteada en el core bancario. Su monto y fecha son finales. **Es el único estado que entra al cálculo de Smart Budget.**

### Provider
Agregador externo de datos financieros. En Dough hay dos: Finicity y Plaid (tabla `provider`).

---

## R

### Redshift
Data warehouse de AWS usado por Blossom para almacenamiento analítico (3-24 meses configurables por CU). Fuente del input de Smart Budget.

### Reflejo *(Fase 0 de Smart Budget)*
Ver "Fase 0".

### REF *(Refund)*
Código de transacción para reembolsos. En Smart Budget se interpreta como gasto negativo del mes; si la suma neta del mes queda negativa, se hace clamp a 0.

### Reg E
Regulación estadounidense que cubre transferencias electrónicas de fondos. Dado que Dough es read-only (no inicia movimientos), su exposición a Reg E es limitada.

### RICH
Feature flag y servicio de enriquecimiento de transacciones (limpia comercios, asigna logos, normaliza categorías). Internamente delega en Ntropy. **Si está OFF, no hay categorías enriquecidas** — Dough muestra el formato OLB estándar.

### Robo-Adviser
Categoría regulatoria de la SEC. Son herramientas automatizadas que recomiendan productos o asignaciones de inversión. **Smart Budget NO puede ser un robo-adviser** — solo refleja, no prescribe.

---

## S

### S3
Almacenamiento de objetos de AWS. Usado como data lake para las capas bronze/silver/gold.

### SEC *(Securities and Exchange Commission)*
Regulador estadounidense de inversiones. Define qué cuenta como asesoría de inversión (Investment Advisers Act of 1940) y qué herramientas deben registrarse como Robo-Adviser.

### Section 1033 *(CFPB)*
Regla del CFPB sobre derechos de datos financieros del consumidor. Establece estándares de portabilidad y prohíbe el uso secundario de datos sin consentimiento explícito. Aplica a datos de Plaid/Finicity.

### SIG *(System Generated Transactions)*
Transacciones creadas por el sistema sin contraparte comercial externa: comisiones mensuales, intereses, ajustes, penalizaciones, write-offs. **Se excluyen del cálculo de Smart Budget** (por ser ruido administrativo, no consumo del miembro).

### Silver *(capa medallion)*
Segunda capa del data lake. Contiene los datos limpios sin metadata de extracción, listos para análisis. **Es la capa que Smart Budget debe consumir.**
*Relacionado:* Bronze, Gold.

### Smart Budget
Módulo de presupuesto inteligente de Dough. Sugiere montos por categoría basándose en el histórico real del miembro, eliminando el "punto de partida en blanco" del Manual Budget.

### Snapshot Freeze
Regla que impide modificar retroactivamente un valor mostrado al usuario. Una vez emitida una sugerencia, no se modifica — si el modelo recalcula, se inserta una fila nueva con timestamp distinto. Originalmente definida para Net Worth, aplica también a Smart Budget.

### Splits *(Transaction Split)*
División lógica de una transacción en varias partes con categorías distintas, sin afectar el core bancario. **Es la unidad real de agregación para Smart Budget** (no la transacción).

---

## T

### T&C *(Terms & Conditions)*
Términos y condiciones del producto. Cada CU configura los suyos propios para Dough, con disclaimer de "no asesoría financiera". El miembro debe aceptarlos antes de ver el dashboard. Sin aceptación válida, **no se sirve sugerencia de Smart Budget**.

### Team Member
Empleado dentro de una cuenta business. El Team Owner controla qué secciones y categorías puede ver el Team Member.

### Team Owner
Dueño de una cuenta business. Configura qué información financiera ven sus Team Members. Las cuentas externas que agrega son privadas por defecto.

### Time-to-budget
Métrica de Fase 0. Tiempo promedio para completar el setup de un budget. Comparativa Smart Budget vs Manual Budget. Umbral para Fase 1: Smart al menos 80% más rápido que Manual.

### Transaction
Evento financiero que impacta assets/liabilities y es visible para el usuario. Puede estar enriquecida (RICH) o cruda. Tiene estado (Pending/Posted/Failed/Cancelled). Es la entrada base del cálculo de Smart Budget — pero la unidad real de agregación es el `transactionSplit`.

### Transaction Split
Ver "Splits".

---

## U

### UDAAP *(Unfair, Deceptive, or Abusive Acts or Practices)*
Doctrina del CFPB que prohíbe prácticas injustas, engañosas o abusivas con consumidores. **Obliga a que el lenguaje de Smart Budget sea neutral y descriptivo, nunca prescriptivo** ("Basado en tus últimos 3 meses" ✅ vs "Deberías gastar menos en X" ❌).

### Uncategorized
Categoría especial que agrupa transacciones de tipo Expense que no fueron categorizadas. **No es modificable** y **no recibe sugerencia** en Smart Budget.

---

## W

### WDR *(Withdrawal)*
Código de transacción para retiros hacia cuenta externa.

### Wire
Rail de transferencia bancaria de alto valor y procesamiento inmediato.

---

## X

### XFR *(Transfer)*
Código de transacción para transferencias (entrantes o salientes según contexto).

---

## Plantilla para añadir nuevos términos

```markdown
### Término *(acrónimo si aplica)*
Definición concisa en una o dos oraciones.
Dónde aparece o por qué importa al proyecto.
*Relacionado:* Término relacionado 1, Término relacionado 2.
```

> **Nota para Claude:** cuando se añadan nuevos términos al glosario, mantener el orden alfabético, respetar el formato de las entradas existentes y actualizar la fecha de "Última actualización" al inicio del documento.
