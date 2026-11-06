// Funções comuns das páginas (sem dependências externas): API, formatação, ícones de traço e temas.
(function () {
  // Ícones de traço (desenho próprio no estilo Lucide), um <symbol> por ícone; uso: AL.ic('phone').
  const P = {
    phone: '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.8 19.8 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>',
    msg: '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    flame: '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
    spark: '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>',
    send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    back: '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    cal: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    live: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    chart: '<path d="M3 3v18h18"/><path d="M18 17V9M13 17V5M8 17v-3"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    book: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    bulb: '<path d="M9 18h6M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.6 4.6 0 0 1 8.91 14"/>',
    sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-4"/>',
    inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    arrow: '<path d="M5 12h14M12 5l7 7-7 7"/>',
    pass: '<path d="M15 10l5 5-5 5"/><path d="M4 4v7a4 4 0 0 0 4 4h12"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    waves: '<path d="M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/><path d="M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/><path d="M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>',
    eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    eyeoff: '<path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.4 10.4 0 0 1 12 5c6.5 0 10 7 10 7a13.2 13.2 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.5 13.5 0 0 0 2 12s3.5 7 10 7a9.7 9.7 0 0 0 5.39-1.61"/><path d="M2 2l20 20"/>',
    refresh: '<path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 21v-5h5"/><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5M21 12H9"/>',
    trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
    swap: '<path d="M16 3l4 4-4 4"/><path d="M20 7H4"/><path d="M8 21l-4-4 4-4"/><path d="M4 17h16"/>',
    play: '<path d="m6 3 14 9-14 9Z"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/>',
    reopen: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
  };
  const sprite = '<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false">' +
    Object.keys(P).map(k => '<symbol id="i-' + k + '" viewBox="0 0 24 24">' + P[k] + '</symbol>').join('') + '</svg>';
  const por = () => document.body.insertAdjacentHTML('afterbegin', sprite);
  if (document.body) por(); else document.addEventListener('DOMContentLoaded', por);

  const TEMAS = ['claro', 'escuro', 'marinho'];
  const ROTULO_TEMA = {claro: 'Tema claro', escuro: 'Tema escuro', marinho: 'Tema marinho'};
  const ICONE_TEMA = {claro: 'sun', escuro: 'moon', marinho: 'waves'};
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

  window.AL = {
    esc,
    ic(nome, extra) { return '<svg class="i' + (extra ? ' ' + extra : '') + '" aria-hidden="true" focusable="false"><use href="#i-' + nome + '"/></svg>'; },
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
      return (d.startsWith('55') ? '' : '+' + d.slice(0, 2) + ' ') + '(' + d.slice(2, 4) + ') ' + d.slice(4, -4) + '-' + d.slice(-4);
    },
    hora(iso) { return iso ? iso.slice(8, 10) + '/' + iso.slice(5, 7) + ' ' + iso.slice(11, 16) : ''; },
    hm(iso) { return iso ? iso.slice(11, 16) : ''; },
    iniciais(nome) {
      const p = String(nome || '').trim().split(/\s+/).filter(Boolean);
      return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase();
    },
    STATUS: {em_atendimento: 'em atendimento', retornar: 'retornar', negociando: 'negociando', novo: 'novo',
      ganho: 'ganho', perdido: 'perdido', invalido: 'inválido'},
    COLAB: {livre: 'livre', ocupado: 'ocupado', fora: 'fora', atendendo: 'atendendo'},
    CHAMADO: {aguardando: 'aguardando', alerta: 'em alerta', atendendo: 'em atendimento', fechado: 'fechado'},
    MOTIVO: {pediu_humano: 'pediu humano', venda: 'chance de venda', precisa: 'precisa de atenção'},
    RESULTADO: {vendeu: 'vendeu', retornar: 'retornar', negociando: 'negociando', sem_interesse: 'sem interesse',
      invalido: 'inválido', apagado: 'apagado', devolvido: 'devolvido ao assistente'},
    selo(st) { return '<span class="selo st-' + esc(st) + '">' + esc(AL.STATUS[st] || st) + '</span>'; },
    nota(n) {
      if (!n) return '';
      return '<span class="selo n-' + esc(n) + '">' + (n === 'quente' ? AL.ic('flame') : '') + esc(n) + '</span>';
    },
    ponto(st) { return '<span class="dot d-' + esc(st) + '" aria-hidden="true"></span>'; },
    // minutos → "45 s", "2 min 40 s", "12 min", "12 h 21 min"
    dur(min) {
      min = Math.max(0, Number(min) || 0);
      if (min < 1) { const s = Math.round(min * 60); return s ? s + ' s' : '0 min'; }
      if (min < 10 && min % 1) { const s = Math.round((min % 1) * 60); return Math.floor(min) + ' min' + (s ? ' ' + s + ' s' : ''); }
      const m = Math.floor(min);
      if (m < 60) return m + ' min';
      const h = Math.floor(m / 60), r = m % 60;
      return h + ' h' + (r ? ' ' + r + ' min' : '');
    },
    ha(min) {
      if (min == null) return '';
      if (min < 1) return 'agora';
      if (min < 60) return 'há ' + min + ' min';
      if (min < 1440) return 'há ' + Math.floor(min / 60) + ' h';
      const d = Math.floor(min / 1440); return 'há ' + d + (d === 1 ? ' dia' : ' dias');
    },
    ddmm(dia) { return dia ? dia.slice(8, 10) + '/' + dia.slice(5, 7) : ''; },
    brl(v) { return (Number(v) || 0).toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'}); },
    // tempo de conversa · há quanto tempo · contato em outro dia (seção 12)
    tempos(l) {
      const p = [];
      if (l.minutos_conversa) p.push(AL.dur(l.minutos_conversa) + ' de conversa');
      if (l.minutos_desde_contato != null) p.push(AL.ha(l.minutos_desde_contato));
      if (l.dia_anterior) p.push('também falou em ' + AL.ddmm(l.dia_anterior) + ' · ' + l.dias_contato + ' dias de contato');
      return esc(p.join(' · '));
    },
    // Bolha de mensagem vista pela equipe/gestor: lead (cliente), ia (assistente), eu/equipe (humano).
    bolhaEquipe(m, nomeLead, meuId, nomes) {
      const quem = m.de === 'lead' ? (nomeLead || 'Lead') : m.de === 'humano' ? 'Equipe' : m.de === 'agente' ? 'Assistente (IA)' : 'Sistema';
      const cls = m.de === 'lead' ? 'lead' : m.de === 'humano' ? 'eu' : 'ia';
      const ic = m.de === 'agente' ? AL.ic('spark') : '';
      return '<div class="b ' + cls + '"><small>' + ic + esc(quem) + '</small>' + esc(m.texto) + '<time>' + esc(AL.hora(m.em)) + '</time></div>';
    },

    // ---------- temas ----------
    TEMAS,
    aplicarTema(t) {
      if (!TEMAS.includes(t)) t = 'claro';
      document.documentElement.dataset.tema = t;
      document.querySelectorAll('[data-tema-btn]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.temaBtn === t)));
      return t;
    },
    // Seletor de tema (equipe e gestor): salvo por aparelho; sem escolha salva, vale o tema do negócio.
    seletorTema(alvo) {
      const el = typeof alvo === 'string' ? document.getElementById(alvo) : alvo;
      if (!el) return;
      el.innerHTML = TEMAS.map(t => '<button type="button" data-tema-btn="' + t + '" aria-pressed="false" aria-label="' + ROTULO_TEMA[t] +
        '" title="' + ROTULO_TEMA[t] + '">' + AL.ic(ICONE_TEMA[t]) + '</button>').join('');
      el.addEventListener('click', ev => {
        const b = ev.target.closest('[data-tema-btn]'); if (!b) return;
        try { localStorage.setItem('al_tema', b.dataset.temaBtn); } catch (e) { /* sem storage */ }
        AL.aplicarTema(b.dataset.temaBtn);
      });
      let salvo = null;
      try { salvo = localStorage.getItem('al_tema'); } catch (e) { /* sem storage */ }
      AL.aplicarTema(salvo || document.documentElement.dataset.tema || 'claro');
      if (!salvo) AL.api('GET', '/api/aparencia').then(a => {
        try { localStorage.setItem('al_tema_negocio', a.tema); } catch (e) { /* sem storage */ }
        let agora = null; try { agora = localStorage.getItem('al_tema'); } catch (e) { /* */ }
        if (!agora) AL.aplicarTema(a.tema);
      }).catch(() => {});
    },
  };
})();
