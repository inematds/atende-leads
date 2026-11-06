// Funções comuns das páginas (sem dependências externas).
window.AL = {
  esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  },
  async api(metodo, rota, corpo, headers) {
    const r = await fetch(rota, {method: metodo, headers: Object.assign({'Content-Type': 'application/json'}, headers || {}),
      body: corpo === undefined ? undefined : JSON.stringify(corpo)});
    const tipo = r.headers.get('Content-Type') || '';
    const dados = tipo.includes('json') ? await r.json() : await r.text();
    if (!r.ok) { const e = new Error((dados && dados.erro) || ('Erro ' + r.status)); e.status = r.status; throw e; }
    return dados;
  },
  fone(d) {
    d = String(d || '');
    if (!/^\d{12,13}$/.test(d)) return d;
    return '+' + d.slice(0, 2) + ' (' + d.slice(2, 4) + ') ' + d.slice(4, -4) + '-' + d.slice(-4);
  },
  hora(iso) { return iso ? iso.slice(8, 10) + '/' + iso.slice(5, 7) + ' ' + iso.slice(11, 16) : ''; },
  tag(t) { return '<span class="tag ' + AL.esc(t) + '">' + AL.esc(t) + '</span>'; },
  STATUS: {em_atendimento: 'em atendimento', retornar: 'retornar', negociando: 'negociando', novo: 'novo',
    ganho: 'ganho', perdido: 'perdido', invalido: 'inválido'},
  selo(st) { return '<span class="selo st-' + AL.esc(st) + '">' + AL.esc(AL.STATUS[st] || st) + '</span>'; },
  dur(min) { min = Math.max(0, Math.round(min || 0)); return min < 60 ? min + ' min' : Math.floor(min / 60) + ' h ' + (min % 60) + ' min'; },
  ha(min) {
    if (min == null) return '';
    if (min < 60) return 'há ' + min + ' min';
    if (min < 1440) return 'há ' + Math.floor(min / 60) + ' h';
    const d = Math.floor(min / 1440); return 'há ' + d + (d === 1 ? ' dia' : ' dias');
  },
  ddmm(dia) { return dia ? dia.slice(8, 10) + '/' + dia.slice(5, 7) : ''; },
  // tempo de conversa · há quanto tempo · contato em outro dia (seção 12)
  tempos(l) {
    const p = [];
    if (l.minutos_conversa) p.push('💬 ' + AL.dur(l.minutos_conversa) + ' de conversa');
    if (l.minutos_desde_contato != null) p.push(AL.ha(l.minutos_desde_contato));
    if (l.dia_anterior) p.push('também falou em ' + AL.ddmm(l.dia_anterior) + ' · ' + l.dias_contato + ' dias de contato');
    return AL.esc(p.join(' · '));
  },
};
