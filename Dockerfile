FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY atende VERSION ./
COPY src/ ./src/
COPY web/ ./web/
COPY exemplos/ ./exemplos/
# Roda sem root: usuário "atende" com uid/gid 1000. A pasta montada em /dados (./dados no host) precisa ser
# desse uid: sudo chown -R 1000:1000 dados  (o instalar-vps.sh já faz).
RUN chmod +x atende && groupadd -g 1000 atende && useradd -u 1000 -g 1000 -M -d /app -s /usr/sbin/nologin atende \
    && mkdir -p /dados && chown 1000:1000 /dados
USER 1000:1000
VOLUME ["/dados"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import json,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8080/api/saude', timeout=3); assert json.load(r)['ok'] is True"
CMD ["./atende", "serve", "--host", "0.0.0.0", "--porta", "8080", "--dados", "/dados"]
