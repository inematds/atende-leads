"""Modo polling do Telegram (seção 16): para máquina sem domínio público/HTTPS.

Uma thread chama `deleteWebhook` (sem apagar os updates pendentes) e faz `getUpdates` com long polling.
Cada update vai ao MESMO tratamento do `POST /webhook/telegram` (sem o header de segredo: vem direto do
Telegram). O `offset` fica no SQLite (`meta.telegram_offset`), gravado na mesma transação do tratamento,
para não reprocessar depois de reiniciar. A chamada de rede acontece fora do lock. Erro de rede/HTTP →
espera 1, 2, 4… até 30 s e tenta de novo; 409 (webhook ativo) → `deleteWebhook` de novo.
"""
import threading

from .core import log
from . import telegram as tg

TETO = 30
CHAVE = 'telegram_offset'


class Leitor:
    def __init__(self, app, entregar):
        self.app, self.entregar = app, entregar
        self.parar = threading.Event()
        self.ocupado = threading.Lock()  # segurado só enquanto trata updates (nunca na chamada de rede)
        self.erros = 0
        self.thread = threading.Thread(target=self._rodar, name='telegram-polling', daemon=True)

    def iniciar(self):
        self.thread.start()
        return self

    def encerrar(self):
        self.parar.set()
        # Espera o update em tratamento terminar (o banco fecha logo depois); a chamada longa não segura nada.
        if self.ocupado.acquire(timeout=5):
            self.ocupado.release()
        self.thread.join(1)

    def _esperar_erro(self):
        espera = min(2 ** self.erros, TETO)
        self.erros += 1
        self.parar.wait(espera)

    def _offset(self):
        with self.app.lock:
            valor = self.app.meta(CHAVE)
        try:
            return int(valor) if valor is not None else None
        except ValueError:
            return None

    def apagar_webhook(self):
        st, r = tg.chamar_http('deleteWebhook', {'drop_pending_updates': False})
        ok = 200 <= st < 300 and r.get('ok') is not False
        if not ok:
            log(f'telegram polling: deleteWebhook falhou (status {st})')
        return ok

    def _rodar(self):
        apagar = True
        while not self.parar.is_set():
            try:
                if apagar:
                    if not self.apagar_webhook():
                        self._esperar_erro()
                        continue
                    apagar = False
                apagar = self.rodada()
            except Exception as e:
                log(f'telegram polling: {type(e).__name__}: {e}')
                self._esperar_erro()

    def rodada(self):
        """Um getUpdates. Devolve True se é preciso chamar deleteWebhook de novo."""
        timeout = tg.poll_timeout()
        corpo = {'timeout': timeout, 'allowed_updates': ['message', 'callback_query']}
        offset = self._offset()
        if offset is not None:
            corpo['offset'] = offset
        st, r = tg.chamar_http('getUpdates', corpo, timeout=timeout + 10)
        if self.parar.is_set():
            return False
        if st == 409 or r.get('error_code') == 409:
            log('telegram polling: 409 (webhook ativo), chamando deleteWebhook')
            self._esperar_erro()
            return True
        if not (200 <= st < 300) or r.get('ok') is False or not isinstance(r.get('result'), list):
            log(f'telegram polling: getUpdates falhou (status {st})')
            self._esperar_erro()
            return False
        self.erros = 0
        with self.ocupado:
            for u in r['result']:
                if self.parar.is_set():
                    return False
                if not isinstance(u, dict) or not isinstance(u.get('update_id'), int):
                    continue
                prox = u['update_id'] + 1
                if offset is not None and prox <= offset:
                    continue  # já tratado
                self.entregar(u, lambda p=prox: self.app.meta(CHAVE, str(p), gravar=True))
                if self._offset() != prox:  # tratamento e descarte falharam: não repete o update para sempre
                    with self.app.transacao():
                        self.app.meta(CHAVE, str(prox), gravar=True)
                offset = prox
        return False
