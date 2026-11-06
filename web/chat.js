// Chat web do lead. Identidade = sessão (localStorage), não o telefone: a 1ª mensagem cria o lead web e
// devolve `sessao`; as seguintes mandam a sessão. Respostas da equipe chegam por GET /api/web/<sessao>.
(function () {
  if (new URLSearchParams(location.search).get('widget') === '1') document.body.classList.add('widget');
  const $ = id => document.getElementById(id);
  const guarda = window.localStorage;
  let tel = guarda.getItem('al_tel'), nome = guarda.getItem('al_nome') || '', sessao = guarda.getItem('al_sessao');
  let vistos = 0, relogio = null;

  function bolha(texto, classe, rotulo) {
    const d = document.createElement('div');
    d.className = 'bolha ' + (classe || '');
    d.innerHTML = (rotulo ? '<small>' + AL.esc(rotulo) + '</small>' : '') + AL.esc(texto);
    $('log').appendChild(d);
    $('log').scrollTop = $('log').scrollHeight;
  }

  function esquecer() {
    sessao = null; ['al_sessao', 'al_tel', 'al_nome'].forEach(k => guarda.removeItem(k));
  }

  async function enviar(texto) {
    bolha(texto, 'minha');
    const corpo = sessao ? {sessao, texto, canal: 'web'} : {telefone: tel, texto, nome: nome || undefined, canal: 'web'};
    try {
      const r = await AL.api('POST', '/api/mensagens', corpo);
      if (r.sessao) { sessao = r.sessao; guarda.setItem('al_sessao', sessao); }
      r.respostas.forEach(t => bolha(t));
      vistos = -1; // reconta no próximo ciclo
    } catch (e) {
      if (e.status === 404 && sessao) { esquecer(); bolha('Sua conversa expirou. Recarregue a página para começar de novo.', 'erro'); }
      else bolha('Não consegui enviar: ' + e.message, 'erro');
    }
  }

  async function puxar() {
    if (!sessao) return;
    try {
      const m = await AL.api('GET', '/api/web/' + encodeURIComponent(sessao));
      const humanos = (m.mensagens || []).filter(x => x.de === 'humano');
      if (vistos === -1) vistos = humanos.length;
      humanos.slice(vistos).forEach(x => bolha(x.texto, 'humano', m.colaborador || 'Equipe'));
      vistos = humanos.length;
    } catch (e) { /* silencioso */ }
  }

  function abrirChat() {
    $('entrada').hidden = true; $('chat').hidden = false; $('texto').focus();
    vistos = -1; puxar();
    if (!relogio) relogio = setInterval(puxar, 5000);
  }

  $('form-entrada').addEventListener('submit', ev => {
    ev.preventDefault();
    const d = $('telefone').value.replace(/\D/g, '');
    if (d.length < 10 || d.length > 13) { $('erro-entrada').textContent = 'Confira o número com DDD.'; return; }
    tel = d; nome = $('nome').value.trim(); sessao = null;
    guarda.setItem('al_tel', tel); guarda.setItem('al_nome', nome); guarda.removeItem('al_sessao');
    abrirChat();
    enviar('Olá');
  });
  $('form-msg').addEventListener('submit', ev => {
    ev.preventDefault();
    const t = $('texto').value.trim();
    if (!t) return;
    $('texto').value = '';
    enviar(t);
  });
  AL.api('GET', '/api/saude').then(() => {}).catch(() => {});
  if (sessao) abrirChat();
})();
