# Apps del backend (pendientes de desarrollo)

Carpetas reservadas para cada módulo, según el Gantt del proyecto:

- `usuarios/` — Registro, login, roles, perfil académico (Sprint 2)
- `tutor/` — Chat del tutor virtual con IA (Sprint 3)
- `documentos/` — Carga y análisis de apuntes/PDFs, RAG (Sprint 4)
- `evaluaciones/` — Quizzes y exámenes generados (Sprint 5)
- `progreso/` — Dashboard y detección de dificultades (Sprint 5)

Cada app se crea con `python manage.py startapp <nombre> apps/<nombre>`
(ajustando luego `apps.py` para que `name = "apps.<nombre>"`) y se registra
en `INSTALLED_APPS` dentro de `config/settings.py`.
