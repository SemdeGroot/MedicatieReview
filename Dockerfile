# syntax=docker/dockerfile:1.7

# AWS Lambda Python base image
FROM public.ecr.aws/lambda/python:3.11

# Standaard werkdirectory voor Lambda containers
WORKDIR /var/task

# 1) requirements eerst, voor layer caching
COPY requirements.txt .

# 2) pip install met BuildKit cache (zoals bij je EC2 image)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

# 3) daarna de rest van je code (hele repo)
COPY . .

# Lambda entrypoint: handler = Mangum(app) in app/main.py
CMD ["app.main.handler"]
