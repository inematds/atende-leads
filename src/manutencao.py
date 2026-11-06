"""Manutenção do `negocio.json` (seção 1): `./atende manutencao limpar-bastidores --dados DIR [--aplicar]`.

Remove de `info.*` e do FAQ as frases com marca de bastidor (recado interno que entrou na base pela incorporação
de propostas da 1.6.7 ou antes: "o vendedor informou", "a base diz", "confirmar com a equipe"...). Sem `--aplicar`
só mostra o que sairia. Com `--aplicar`: exige o servidor parado (mesma trava do `restaurar`), grava backup
`negocio.json.<AAAAMMDD-HHMMSS>.bak` e regrava com permissão 600. Não usa LLM.
"""
import json
import os
import re
import shutil
import time
from pathlib import Path

from . import backup
from .base import CAMPOS, tem_bastidor

FRASE = re.compile(r'(?<=[.!?])\s+|\n+')


def _limpar_texto(texto):
    """(texto limpo, [frases removidas]): divide em linhas/frases e tira as que têm marca de bastidor."""
    removidas, linhas = [], []
    for linha in (texto or '').split('\n'):
        frases = [f for f in FRASE.split(linha) if f.strip()]
        boas = []
        for f in frases:
            (removidas if tem_bastidor(f) else boas).append(f.strip())
        if boas:
            linhas.append(' '.join(boas))
    return '\n'.join(linhas).strip(), removidas


def planejar(cfg):
    """Devolve (cfg_novo, relatório [(onde, frase)])."""
    novo = json.loads(json.dumps(cfg))
    rel = []
    info = novo.get('info') if isinstance(novo.get('info'), dict) else {}
    for k in CAMPOS:
        v = info.get(k)
        if isinstance(v, str) and tem_bastidor(v):
            limpo, fora = _limpar_texto(v)
            rel += [(f'info.{k}', f) for f in fora]
            info[k] = limpo
    faq = []
    for f in novo.get('faq') or []:
        resp = f.get('resposta') if isinstance(f, dict) else None
        if isinstance(resp, str) and tem_bastidor(resp):
            limpo, fora = _limpar_texto(resp)
            rel += [(f"faq {f.get('id')}", x) for x in fora]
            if not limpo:
                rel.append((f"faq {f.get('id')}", '(item inteiro removido: só tinha recado interno)'))
                continue
            f['resposta'] = limpo
        faq.append(f)
    if 'faq' in novo:
        novo['faq'] = faq
    return novo, rel


def limpar_bastidores(dados, aplicar=False, saida=print):
    arq = Path(dados) / 'negocio.json'
    if not arq.exists():
        raise SystemExit(f'{arq} não existe')
    cfg = json.loads(arq.read_text(encoding='utf-8'))
    novo, rel = planejar(cfg)
    if not rel:
        saida('Nada a remover: nenhuma frase com marca de bastidor em info nem no FAQ.')
        return 0
    saida(f'{len(rel)} trecho(s) com marca de bastidor:')
    for onde, frase in rel:
        saida(f'  - {onde}: {frase}')
    if not aplicar:
        saida('Simulação: nada foi gravado. Rode de novo com --aplicar (servidor parado) para remover.')
        return len(rel)
    if backup.servidor_rodando(dados):
        raise SystemExit('O servidor está rodando com esta pasta: pare-o antes de --aplicar (ele regravaria o '
                         'negocio.json antigo).')
    bak = arq.with_name(f"negocio.json.{time.strftime('%Y%m%d-%H%M%S')}.bak")
    shutil.copy2(arq, bak)
    os.chmod(bak, 0o600)
    tmp = arq.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(novo, ensure_ascii=False, indent=2), encoding='utf-8')
    os.chmod(tmp, 0o600)
    os.replace(tmp, arq)
    saida(f'Aplicado. Backup em {bak}')
    return len(rel)
