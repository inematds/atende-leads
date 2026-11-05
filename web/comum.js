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
};
