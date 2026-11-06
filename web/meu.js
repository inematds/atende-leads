// Página "meu atendimento": botões Quero falar agora / Apagar meus dados.
(function () {
  const falar = document.getElementById('falar'), apagar = document.getElementById('apagar');
  const aviso = document.getElementById('aviso');
  const token = falar.dataset.token;
  function msg(t, erro) { aviso.textContent = t; aviso.className = erro ? 'aviso erro' : 'aviso'; }
  async function post(rota, corpo) {
    const r = await fetch('/api/meu/' + token + rota, {method: 'POST', headers: {'Content-Type': 'application/json'},
                                                        body: JSON.stringify(corpo || {})});
    const d = await r.json();
    if (!r.ok) throw new Error(d.erro || 'Erro');
    return d;
  }
  falar.addEventListener('click', async () => {
    falar.disabled = true;
    try { const d = await post('/falar'); msg((d.respostas || [])[0] || 'Pedido enviado.'); setTimeout(() => location.reload(), 1500); }
    catch (e) { msg(e.message, true); } finally { falar.disabled = false; }
  });
  apagar.addEventListener('click', async () => {
    if (!confirm('Apagar seus dados? Isso não pode ser desfeito.')) return;
    try { await post('/apagar', {confirmar: true}); msg('Seus dados foram apagados.'); falar.hidden = true; apagar.hidden = true; }
    catch (e) { msg(e.message, true); }
  });
})();
