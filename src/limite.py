"""Limite de tentativas falhas (seção 3): 5 por minuto por chave → 429 / 'Muitas tentativas, aguarde.'

Em memória (zera ao reiniciar). Enquanto bloqueado, recusa até a senha certa.
"""
import threading
import time
from collections import deque

MAX_FALHAS = 5
JANELA = 60.0
MENSAGEM = 'Muitas tentativas, aguarde.'

_falhas = {}
_trava = threading.Lock()


def _limpar(fila, agora):
    while fila and agora - fila[0] > JANELA:
        fila.popleft()


def bloqueado(chave):
    agora = time.monotonic()
    with _trava:
        fila = _falhas.get(chave)
        if not fila:
            return False
        _limpar(fila, agora)
        return len(fila) >= MAX_FALHAS


def falhou(chave):
    agora = time.monotonic()
    with _trava:
        fila = _falhas.setdefault(chave, deque())
        _limpar(fila, agora)
        fila.append(agora)
        if len(_falhas) > 10000:  # não deixa crescer sem fim
            for k in [k for k, f in _falhas.items() if not f or agora - f[-1] > JANELA]:
                _falhas.pop(k, None)
