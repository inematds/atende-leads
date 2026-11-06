"""Limites em memória (zeram ao reiniciar), por janela deslizante e chave.

- Senhas (seção 3): 5 falhas por minuto por IP → as próximas ERRADAS recebem 429 / 'Muitas tentativas, aguarde.'
  Uma credencial certa sempre passa (o bloqueio por IP não pode travar a equipe atrás do mesmo proxy).
- Chat web (seção 4): leads web novos por IP e no total, chamados abertos pelo web por IP.
"""
import threading
import time
from collections import deque

MAX_FALHAS = 5
JANELA = 60.0
MENSAGEM = 'Muitas tentativas, aguarde.'

_eventos = {}
_trava = threading.Lock()


def _limpar(fila, agora, janela):
    while fila and agora - fila[0] > janela:
        fila.popleft()


def excedeu(chave, maximo, janela):
    """True se a chave já tem `maximo` eventos dentro da janela (segundos)."""
    agora = time.monotonic()
    with _trava:
        fila = _eventos.get(chave)
        if not fila:
            return False
        _limpar(fila, agora, janela)
        return len(fila) >= maximo


def contar(chave, janela=JANELA):
    agora = time.monotonic()
    with _trava:
        fila = _eventos.setdefault(chave, deque())
        _limpar(fila, agora, janela)
        fila.append(agora)
        if len(_eventos) > 20000:  # não deixa crescer sem fim
            for k in [k for k, f in _eventos.items() if not f or agora - f[-1] > 3600]:
                _eventos.pop(k, None)


# ---- chat web (seção 4) ----
WEB_LEADS_IP = (5, 600.0)        # leads web novos por IP em 10 min
WEB_LEADS_TOTAL = (30, 60.0)     # leads web novos no total, por minuto
WEB_CHAMADOS_IP = (3, 3600.0)    # chamados abertos pelo chat web / página do lead, por IP, em 1 h
MSG_LEAD_WEB = 'Muitas conversas novas, aguarde alguns minutos.'
MSG_CHAMADO_WEB = 'Muitos pedidos de atendimento, aguarde.'


def checar_lead_web(ip):
    if excedeu(('web_lead', ip), *WEB_LEADS_IP) or excedeu(('web_total',), *WEB_LEADS_TOTAL):
        return False
    return True


def contar_lead_web(ip):
    contar(('web_lead', ip), WEB_LEADS_IP[1])
    contar(('web_total',), WEB_LEADS_TOTAL[1])


def chamado_web_permitido(ip):
    return not excedeu(('web_chamado', ip), *WEB_CHAMADOS_IP)


def contar_chamado_web(ip):
    contar(('web_chamado', ip), WEB_CHAMADOS_IP[1])


# ---- senhas (seção 3) ----
def bloqueado(chave):
    return excedeu(chave, MAX_FALHAS, JANELA)


def falhou(chave):
    contar(chave, JANELA)
