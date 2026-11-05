"""Horário de atendimento (seção 10): janelas [ini, fim) por dia da semana."""
from datetime import datetime, timedelta

from .core import DIAS


def janelas(c, dia):
    """Lista de (ini, fim) datetime do dia (date)."""
    out = []
    for par in (c.cfg.get('horarios') or {}).get(DIAS[dia.weekday()], []) or []:
        try:
            ini = datetime.combine(dia, datetime.strptime(par[0], '%H:%M').time())
            fim = datetime.combine(dia, datetime.strptime(par[1], '%H:%M').time())
        except (ValueError, TypeError, IndexError):
            continue
        if fim > ini:
            out.append((ini, fim))
    return sorted(out)


def janela_atual(c, agora):
    for ini, fim in janelas(c, agora.date()):
        if ini <= agora < fim:
            return ini, fim
    return None


def no_horario(c, agora):
    return janela_atual(c, agora) is not None


def proximo_inicio(c, agora):
    for d in range(0, 15):
        dia = (agora + timedelta(days=d)).date()
        for ini, _ in janelas(c, dia):
            if ini > agora:
                return ini
    return None


def fim_do_dia(c, dia):
    js = janelas(c, dia)
    return js[-1][1] if js else None
