---
title: Codemap Schema
aliases: [Conventions, Rules, Cómo funciona el codemap]
tags: [overview, schema, meta]
type: overview
last_mapped_at: 2026-05-13T10:20:00Z
last_commit: fc0547f
---

# Codemap Schema

Convenciones del vault `docs/codemap/`. Leer este archivo antes de editar cualquier página del codemap a mano.

## Tres capas

1. **Fuentes** — el código fuente en `src/`, `scripts/`, `tests/`. Inmutables desde la perspectiva del codemap.
2. **El vault** — `docs/codemap/`. Creado y mantenido por `/blossom-codemap`. Podés editar páginas a mano — marcá tus edits para que el próximo update las preserve (ver "User edits" abajo).
3. **El schema** — este archivo. Cuando el equipo acuerda una convención nueva, aterriza acá.

## Estructura de carpetas

```
docs/codemap/
├── log.md                    → historial de runs, append-only
├── 00-overview/              → páginas transversales (este nivel)
│   ├── README.md             → punto de entrada del vault
│   ├── Index.md              → catálogo alfabético de páginas
│   ├── Schema.md             → este archivo
│   ├── Architecture.md       → capas de datos y flujo
│   ├── Tech-Stack.md         → dependencias y stack
│   ├── Module-Map.md         → tabla directorio → módulo
│   ├── Glossary.md           → términos de dominio
│   ├── Data-Pipeline.md      → flujo ETL completo
│   └── SDD-Workflow.md       → ciclo de desarrollo del repo
├── 01-core-model/            → src/smart_budget/
├── 02-scripts/               → scripts/
└── 03-tests/                 → tests/
```

## Reglas de frontmatter

Toda página DEBE tener YAML frontmatter con:

| Clave | Requerida | Propósito |
|---|---|---|
| `title` | sí | Nombre legible |
| `aliases` | sí (puede estar vacío) | Nombres alternativos para búsqueda |
| `tags` | sí | Kebab-case, sin espacios |
| `type` | sí | `overview`, `module`, `concept`, `api`, `guide` |
| `last_mapped_at` | sí | ISO 8601 UTC de última actualización |
| `last_commit` | sí | SHA corto del commit en el momento del mapeo |
| `audience` | solo guides | `end-user` para archivos en `docs/guides/` |

## Reglas de wiki-links

- Usar `[[Page-Name]]` para hermanos, `[[01-core-model/Public-API]]` entre carpetas.
- Case-sensitive. El slug es el nombre del archivo sin `.md`.
- Si una página menciona otro módulo o concepto, DEBE linkear a su página.
- **Bidireccional:** si A linkea a B, el `## Backlinks` de B debe listar A.

## Tags inline

Tags `#kebab-case` en algún lugar del body, además del frontmatter. Un tag por concepto principal.

## User edits

Si editás una página del codemap a mano, envolvé el contenido generado automáticamente:

```
<!-- codemap:auto-generated:start -->
(todo esto se reemplaza en el próximo update)
<!-- codemap:auto-generated:end -->

## Mis notas
(esto se preserva en el próximo update)
```

## Diagramas Mermaid

- `Architecture.md` DEBE tener un diagrama del sistema.
- Los READMEs de módulos DEBERÍAN tener un diagrama si el módulo no es trivial.
- Las páginas de conceptos transversales DEBERÍAN tener un diagrama de flujo.

## Tres operaciones

| Modo | Trigger | Qué hace |
|---|---|---|
| fresh | No existe `docs/codemap/` | Mapea todo desde cero |
| update | `--update` o auto-detección | Re-explora solo módulos con archivos cambiados desde `last_mapped_at` |
| lint | `--lint` | Health-check: links rotos, orphans, frontmatter stale |

## Backlinks

- [[README]]

#schema #meta #conventions
