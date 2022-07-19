#!/bin/bash

# Apply database migrations
echo "----Apply database migrations"
python3 manage.py migrate

echo "----Creating fake db"
rm media/*
python3 manage.py resetdb

# Start server
echo "----Starting server"
python3 manage.py runserver 0.0.0.0:8000
