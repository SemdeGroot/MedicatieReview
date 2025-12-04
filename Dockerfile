# Gebruik de AWS Lambda Python image
FROM public.ecr.aws/lambda/python:3.11

# Installeer dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --no-cache-dir -r requirements.txt

# Kopieer de applicatie code
COPY app/ ${LAMBDA_TASK_ROOT}/app/
COPY core/ ${LAMBDA_TASK_ROOT}/core/

# Kopieer de data (database en json files)
# Let op: Zorg dat je 'scripts/build_db.py' hebt gedraaid zodat lookup.db bestaat!
COPY data/ ${LAMBDA_TASK_ROOT}/data/

# Start commando voor Mangum
CMD [ "app.main.handler" ]