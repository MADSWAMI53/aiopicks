FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite+aiosqlite:///data/aiopicks.db

WORKDIR /app

RUN mkdir -p /data

COPY pyproject.toml README.md ./
COPY app ./app
COPY .env.sample ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

ARG PORT=3000
ENV PORT=${PORT}

EXPOSE ${PORT}
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]