#!/usr/bin/env bash
# Script de construccion para Render.
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input          # solo crea las tablas internas de Django; las 39 tablas de Memo ya existen (memo_schema.sql)
python manage.py proteger_tablas             # activa RLS en las tablas nuevas de Django (Supabase las expone por API publica si no)
