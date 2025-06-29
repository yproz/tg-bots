# Celery конфигурация для app_v2
import os
from celery.schedules import crontab

# Брокер и бэкенд
broker_url = 'redis://redis:6379/1'
result_backend = 'redis://redis:6379/1'

# Настройки задач
task_serializer = 'json'
accept_content = ['json']
result_serializer = 'json'
timezone = 'UTC'
enable_utc = True

# Настройки воркера
worker_prefetch_multiplier = 1
task_acks_late = True
worker_disable_rate_limits = True
worker_max_tasks_per_child = 1000

# Настройки результатов
result_expires = 3600  # 1 час
result_persistent = True

# Настройки логирования
worker_log_format = '[%(asctime)s: %(levelname)s/%(processName)s] %(message)s'
worker_task_log_format = '[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s'

# Beat schedule
beat_schedule = {
    'collect-prices-morning': {
        'task': 'tasks.app_v2.collect_all_accounts_v2',
        'schedule': crontab(hour=6, minute=0),  # 9:00 МСК
    },
    'collect-prices-evening': {
        'task': 'tasks.app_v2.collect_all_accounts_v2',
        'schedule': crontab(hour=14, minute=0),  # 17:00 МСК
    },
    'check-reports': {
        'task': 'tasks.app_v2.check_all_reports_v2',
        'schedule': 180.0,  # каждые 3 минуты
    },
} 