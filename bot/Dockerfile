FROM python:3.11-slim

WORKDIR /app

COPY bot/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Код бота
COPY bot/app /app/app

# Сами skill'ы (SKILL.md/rules.md/templates/scripts) - читаются ботом как
# справочный материал и как исполняемые скрипты (kp_number.py и т.п.)
COPY .claude/skills /app/skills

# /data - точка монтирования постоянного диска хостинга (buyers.xlsx,
# kp_state.json, вложения). Создаём как fallback, если volume не подключат -
# бот всё равно запустится, но данные пропадут при редеплое (см. README).
RUN mkdir -p /data

ENV DATA_DIR=/data
ENV SKILLS_DIR=/app/skills
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "app.main"]
