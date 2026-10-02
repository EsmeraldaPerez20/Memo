# FourMind (Memo)

Tutor virtual académico con IA. Backend en Django REST Framework, frontend en React,
base de datos PostgreSQL (Supabase), metodología Scrum (sprints de 2 semanas).

## Equipo y responsabilidades

| Integrante | Rol | Parte del repo |
|---|---|---|
| Anallely | Líder / Backend | `backend/` |
| Brenda | Tester / QA / Programación | `backend/` (apoyo) + pruebas |
| Lupita | Diseño / Programación | `frontend/` |
| Melanye | Análisis / Documentación | `docs/` |

## Estructura del repositorio

```
fourmind/
├── backend/     # Django REST Framework — API (Anallely)
├── frontend/    # React — interfaz de usuario (Lupita)
├── docs/        # Documentación del proyecto, actas, diagramas (Melanye)
└── README.md
```

Este es un **esqueleto inicial**: cada carpeta trae lo mínimo para arrancar.
El desarrollo a fondo de cada parte se hace en su propia rama (ver abajo).

## Cómo empezar

- **Backend**: entra a `backend/README.md`.
- **Frontend**: entra a `frontend/README.md`.

## Flujo de trabajo en Git

**Ramas:**
- `main` → siempre estable, lista para desplegar.
- `develop` → rama de integración, aquí se juntan los avances de todos.
- `feature/nombre-de-tu-tarea` → una rama por tarea (ej. `feature/backend-auth`, `feature/frontend-chat-ui`).

**Flujo típico:**

```bash
git checkout develop
git pull origin develop
git checkout -b feature/mi-tarea

# ... trabajas y haces commits ...
git add .
git commit -m "feat: agrega endpoint de registro de usuarios"
git push origin feature/mi-tarea
# Abres un Pull Request: feature/mi-tarea -> develop
```

**Convención de commits:** `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`

**Antes de hacer merge a `develop`**, alguien más del equipo revisa el Pull Request (idealmente Brenda, QA).
**Solo al cerrar un Sprint**, se hace merge de `develop` a `main`.

## Primeros pasos para subir este esqueleto a GitHub

```bash
cd fourmind
git init
git add .
git commit -m "chore: esqueleto inicial del repositorio"
git branch -M main

# Crea el repo vacío en GitHub primero (sin README), luego:
git remote add origin https://github.com/<tu-usuario-u-org>/fourmind.git
git push -u origin main

git checkout -b develop
git push -u origin develop
```

Después, en GitHub protege `main` y `develop` (Settings → Branches) para que solo se suba código vía Pull Request.
