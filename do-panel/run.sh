#!/bin/bash
. /etc/environment
exec uvicorn app:app --host 127.0.0.1 --port 8787
