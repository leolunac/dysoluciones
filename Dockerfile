FROM python:3.12

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . /app/

RUN mkdir -p /app/staticfiles

EXPOSE 8000

CMD ["gunicorn", "sistema7x24.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]