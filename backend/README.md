# Memo (FourMind) — Backend

API REST con **Django REST Framework** para el tutor virtual académico con IA.
Base de datos: **PostgreSQL en Supabase** (+ pgvector). Despliegue: **Render**. Frontend: React.

Cubre los 8 módulos y las 39 tablas de `database/memo_schema.sql`: autenticación y roles, catálogo académico,
documentos y RAG, tutor con IA, evaluación adaptativa, diagnóstico (Knowledge Tracing), recomendaciones/planes/metas y administración.

> Las tablas las crea el SQL, no las migraciones de Django: los modelos son `managed = False`.
> `migrate` solo crea las 9 tablas internas de Django (`auth_*`, `django_*`, `token_blacklist_*`).

## 1. Instalación local

```bash
cd backend
python -m venv venv
venv\Scripts\activate            # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env           # Mac/Linux: cp .env.example .env   (y llena tus datos de Supabase)

python manage.py migrate
python manage.py proteger_tablas          # IMPORTANTE: activa RLS en las tablas que acaba de crear Django
python manage.py createsuperuser          # pide correo, nombre y contraseña; queda con rol administrador
python manage.py runserver
```

- Documentación interactiva de toda la API: **http://127.0.0.1:8000/api/docs/** (Swagger) — úsala para probar y para que el frontend vea los formatos.
- Comprobación rápida: `GET /api/salud/` → `{"estado": "ok"}`.
- Panel de Django (solo administradores): `/admin/`.

### Conexión a Supabase
En *Project Settings → Database → Connection string* elige **Session pooler** (la conexión directa usa IPv6 y muchas redes no la soportan).
El usuario tiene la forma `postgres.TU_REF` y el puerto es `5432`.

## 2. Cómo se usa desde React

```js
// 1) iniciar sesión
const r = await fetch(`${API}/api/auth/login/`, { method: "POST", headers: {"Content-Type": "application/json"},
  body: JSON.stringify({ correo, password }) });
const { access, refresh, usuario } = await r.json();     // usuario.rol y usuario.permisos sirven para mostrar/ocultar menús
// 2) llamar a la API con el token
fetch(`${API}/api/dashboard/`, { headers: { Authorization: `Bearer ${access}` } });
// 3) cuando el access expire (30 min): POST /api/auth/refresh/ {refresh} → nuevo access y nuevo refresh
```
Agrega la URL de tu frontend a `CORS_ALLOWED_ORIGINS`. Las listas vienen paginadas: `{count, next, previous, results}` (`?page=2&page_size=50`).

## 3. Endpoints principales

| Módulo | Endpoints |
|---|---|
| Autenticación | `POST auth/registro/` · `auth/login/` · `auth/refresh/` · `auth/logout/` · `auth/google/` · `auth/recuperar/` · `auth/restablecer/` — `GET/PATCH auth/yo/` · `auth/perfil/` · `auth/preferencias/` |
| Administración de usuarios | `usuarios/` · `roles/` (+ `PUT roles/{id}/permisos/`) · `permisos/` |
| Académico | `materias/` (+ `{id}/arbol/`) · `unidades/` · `temas/` · `mis-materias/` |
| Documentos | `documentos/` (+ `analizar`, `elementos`, `temas`, `enlace`, `descargar`) · `materiales/` (+ `aprobar`, `rechazar`) |
| Tutor | `conversaciones/` (+ `mensajes`, `preguntar`) · `mensajes/{id}/reportar/` · `reportes-ia/` |
| Evaluación | `banco-preguntas/` · `actividades/` (+ `generar`, `iniciar`) · `intentos/` (+ `responder`, `finalizar`, `resultado`) |
| Progreso | `progreso/` · `dificultades/` (+ `evidencias`) · `dashboard/` · `dashboard/exportar/?formato=excel\|pdf` · `docente/estudiantes/` |
| Planificación | `recomendaciones/` (+ `generar`) · `planes/` (+ `generar`, `items`, `revisar`) · `plan-items/` · `metas/` · `tareas/` |
| Administración | `notificaciones/` · `auditoria/` · `incidencias/` · `consumo-ia/` (+ `resumen`) · `configuracion/` |

Todo cuelga de `/api/`. Cada estudiante solo ve sus propios datos; lo demás depende de los **permisos del rol** (`roles_permisos`), no de los grupos de Django.

## 4. Inteligencia artificial

Todo pasa por `servicios/ia.py`. Con `IA_PROVEEDOR=simulado` (por defecto) **todo el flujo funciona sin claves ni costo** (tutor, análisis,
generación de preguntas, calificación), pensado para desarrollar el frontend y probar.

| Para usar… | Instala | Variables |
|---|---|---|
| Claude | `pip install anthropic` | `IA_PROVEEDOR=anthropic`, `ANTHROPIC_API_KEY` |
| OpenAI | `pip install openai` | `IA_PROVEEDOR=openai`, `OPENAI_API_KEY` |
| Búsqueda semántica real en apuntes | `pip install openai` | `EMBEDDINGS_PROVEEDOR=openai`, `OPENAI_API_KEY` |

Cada llamada queda en `consumo_ia` (tokens, costo estimado, tiempo). Si el proveedor falla, la API responde `503` con un mensaje claro.
Si cambias el modelo de embeddings, la dimensión debe seguir siendo 1536 (o cambia `fragmentos.embedding` y `EMBEDDING_DIM`).

## 5. Archivos privados (Supabase Storage)

1. En Supabase → *Storage* crea un bucket **privado** llamado `documentos`.
2. Pon `SUPABASE_URL` y `SUPABASE_SERVICE_KEY` (la *service_role key*, **solo en el servidor**, nunca en el frontend) en el `.env`.

Sin esas variables guarda en `almacenamiento_local/` (solo para desarrollo: en Render el disco se borra en cada despliegue).

## 6. Tareas programadas (cron)

| Comando | Para qué | Frecuencia sugerida |
|---|---|---|
| `python manage.py enviar_recordatorios` | Avisa de tareas que vencen en las próximas 24 h (RF-54) | cada hora |
| `python manage.py purgar_conversaciones --horas 24` | Borra conversaciones que el estudiante no autorizó guardar (RF-10, RF-11) | diario |

En Render se programan con *Cron Jobs*.

## 7. Despliegue en Render

1. Conecta el repositorio → **Web Service** (Python), carpeta raíz `backend`.
2. Build command: `./build.sh` · Start command: `gunicorn config.wsgi`.
3. Pega las variables del `.env` en *Environment* (con `DEBUG=False`, `FORZAR_HTTPS=True` y `ALLOWED_HOSTS` con tu dominio de Render).
4. Health check path: `/api/salud/`.

## 8. Pruebas automáticas (61)

Prueban los flujos reales contra el schema SQL (registro, login, Google, RAG, aprobación de materiales, evaluación, diagnóstico, exportes…).
Necesitan un PostgreSQL **local con pgvector** (Supabase no permite crear bases de prueba):

```bash
createdb memo_template
psql -d memo_template -f database/memo_schema.sql
# en el .env:  TEST_DB_TEMPLATE=memo_template   (y DB_* apuntando a tu Postgres local)
python manage.py test
```

## 9. Seguridad: lo que conviene recordar

- Las contraseñas se guardan con hash; los tokens de recuperación solo como hash; la bitácora nunca guarda contraseñas.
- Supabase publica por API las tablas sin RLS: el SQL ya activó RLS en las 39 tablas y **`proteger_tablas` lo hace con las de Django** (ya está en `build.sh`).
- Django se conecta como dueño de las tablas, así que RLS no le estorba.
- Límites de peticiones activos en login/registro (`auth`) y en las acciones con IA (`ia`).

## 10. Lo que NO está probado o queda pendiente

- **Probado solo con el proveedor simulado:** Claude/OpenAI, Supabase Storage, la verificación real del token de Google y el envío SMTP (el código sigue la documentación de cada servicio, pero hay que probarlo con tus claves).
- **Imágenes (PNG/JPG):** se aceptan y guardan, pero analizarlas requiere OCR (`pytesseract` + `tesseract-ocr`); sin eso el análisis responde un error claro.
- **WhatsApp:** las notificaciones se registran con canal `whatsapp` y quedan pendientes; falta conectar un proveedor (Twilio / Meta Cloud API).
- **Análisis de documentos grandes:** corre dentro de la petición. Para producción con muchos usuarios conviene moverlo a una cola (Celery + Redis).
- **Decisiones del equipo:** que quien sube un material no sea quien lo aprueba, citar páginas web como fuentes (RF-53) y el modelo de embeddings definitivo.
