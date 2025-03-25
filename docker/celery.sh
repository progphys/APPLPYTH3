#!/bin/bash
cd src
if [[ "${1}" == "celery" ]]; then
   celery -A tasks.tasks:celery_app worker --loglevel=info
 fi
