FROM python:3.8-alpine
ADD requirements.txt /
RUN adduser -D vscode
RUN apk add openssh-client git alpine-sdk libffi-dev docker-cli; \
    pip install -r requirements.txt;
