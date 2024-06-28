import os
import signal
import sys
import threading

import django
import uvicorn
from django.core.management import call_command

from glitchtip.celery import app

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "glitchtip.settings")
django.setup()


def run_celery_worker():
    app.worker_main(argv=["worker", "--loglevel=info", "--pool=threads"])


def run_celery_beat():
    app.Beat().run()


def run_django_server():
    uvicorn.run(
        "glitchtip.asgi:application",
        workers=1,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )


def signal_handler(sig, frame):
    print("SIGTERM received, shutting down gracefully...")
    # Perform cleanup here
    sys.exit(0)


def main():
    call_command("migrate", no_input=True)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    worker_thread = threading.Thread(target=run_celery_worker)
    worker_thread.start()

    beat_thread = threading.Thread(target=run_celery_beat)
    beat_thread.start()

    django_thread = threading.Thread(target=run_django_server)
    django_thread.start()
    # run_django_server()

    django_thread.join()
    # worker_thread.join()
    # beat_thread.join()


main()
