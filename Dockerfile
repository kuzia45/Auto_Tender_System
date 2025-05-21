# Используем легкий образ Python
FROM python:3.10-slim

EXPOSE 8000

# Установка dos2unix для обработки Windows-файлов
RUN apt update && apt install -y dos2unix

# Создаем директории
RUN mkdir -p /app_b/backend /app_f /evaluation_info && chmod 777 /app_b/backend /app_f /evaluation_info

# Копируем фронтенд
COPY frontend/ /app_f

# Копируем evaluation_info
COPY evaluation_info/ /evaluation_info

# Переходим к бэкенду
WORKDIR /app_b/backend

# Копируем зависимости
COPY backend/requirements.txt /app_b/backend/

# Обновляем pip
RUN pip install --upgrade pip

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь бэкенд
COPY backend/ /app_b/backend

# Указываем путь поиска модулей
ENV PYTHONPATH=/app_b/backend

# Копируем и готовим стартовый скрипт
COPY start.sh /start.sh
RUN dos2unix /start.sh && chmod +x /start.sh

# Запуск
# Запуск
CMD ["/start.sh"]