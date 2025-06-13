FROM python:3.11-slim

# Установка зависимостей для сборки (если нужно)
RUN apt-get update && apt-get install -y build-essential

# Установка рабочей директории
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Установка зависимостей
RUN pip3 install --upgrade pip \
 && pip3 install -r requirements.txt

# Копируем проект
COPY . .

# Запуск приложения (замени на свою команду)
CMD ["python", "main.py"]
