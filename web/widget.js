// Bolha de chat para qualquer site: <script src="https://SEU-DOMINIO/widget.js" async></script>
// Tema e cor de destaque vêm de Cadastros → Aparência (GET /api/aparencia), embutidos pelo servidor.
(function () {
  if (window.__atendeLeads) return; window.__atendeLeads = true;
  var URL_PUBLICA = __URL_PUBLICA__;
  var AP = __APARENCIA__;
  var base = (URL_PUBLICA || '').replace(/\/$/, '');
  var FUNDO = {claro: '#ffffff', escuro: '#0c0c10', marinho: '#0b1524'}[AP.tema] || '#ffffff';
  var cor = AP.cor_destaque || '#FACC15', tinta = AP.cor_destaque_texto || '#1a1206';
  var SVG = 'xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" ' +
    'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
  var ABRIR = '<svg ' + SVG + '><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/></svg>';
  var FECHAR = '<svg ' + SVG + '><path d="M18 6 6 18M6 6l12 12"/></svg>';
  var bolha = document.createElement('button');
  bolha.type = 'button';
  bolha.setAttribute('aria-label', 'Abrir chat');
  bolha.setAttribute('aria-expanded', 'false');
  bolha.innerHTML = ABRIR;
  bolha.style.cssText = 'position:fixed;right:18px;bottom:18px;width:58px;height:58px;border-radius:50%;border:0;display:grid;' +
    'place-items:center;background:' + cor + ';color:' + tinta + ';cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.30);z-index:2147483646';
  var caixa = document.createElement('div');
  caixa.style.cssText = 'position:fixed;right:18px;bottom:88px;width:min(380px,calc(100vw - 24px));height:min(600px,calc(100vh - 110px));' +
    'border-radius:14px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.35);display:none;z-index:2147483647;background:' + FUNDO;
  var iframe = document.createElement('iframe');
  iframe.title = 'Chat de atendimento' + (AP.nome_exibido ? ' · ' + AP.nome_exibido : '');
  iframe.style.cssText = 'width:100%;height:100%;border:0';
  caixa.appendChild(iframe);
  bolha.addEventListener('click', function () {
    if (!iframe.src) iframe.src = base + '/?widget=1';
    var aberto = caixa.style.display === 'block';
    caixa.style.display = aberto ? 'none' : 'block';
    bolha.innerHTML = aberto ? ABRIR : FECHAR;
    bolha.setAttribute('aria-label', aberto ? 'Abrir chat' : 'Fechar chat');
    bolha.setAttribute('aria-expanded', aberto ? 'false' : 'true');
  });
  function montar() { document.body.appendChild(caixa); document.body.appendChild(bolha); }
  if (document.body) montar(); else document.addEventListener('DOMContentLoaded', montar);
})();
