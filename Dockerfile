FROM python:3.8-alpine
ADD requirements.txt /
RUN apk add openssh-client git alpine-sdk; \
    pip install -r requirements.txt;
