// Bolha de chat para qualquer site: <script src="https://SEU-DOMINIO/widget.js" async></script>
(function () {
  if (window.__atendeLeads) return; window.__atendeLeads = true;
  var URL_PUBLICA = __URL_PUBLICA__;
  var base = (URL_PUBLICA || '').replace(/\/$/, '');
  var bolha = document.createElement('button');
  bolha.type = 'button';
  bolha.setAttribute('aria-label', 'Abrir chat');
  bolha.textContent = '💬';
  bolha.style.cssText = 'position:fixed;right:18px;bottom:18px;width:58px;height:58px;border-radius:50%;border:0;' +
    'background:#FACC15;color:#1a1206;font-size:26px;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.35);z-index:2147483646';
  var caixa = document.createElement('div');
  caixa.style.cssText = 'position:fixed;right:18px;bottom:88px;width:min(380px,calc(100vw - 24px));height:min(600px,calc(100vh - 110px));' +
    'border-radius:14px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.45);display:none;z-index:2147483647;background:#0c0c10';
  var iframe = document.createElement('iframe');
  iframe.title = 'Chat de atendimento';
  iframe.style.cssText = 'width:100%;height:100%;border:0';
  caixa.appendChild(iframe);
  bolha.addEventListener('click', function () {
    if (!iframe.src) iframe.src = base + '/?widget=1';
    var aberto = caixa.style.display === 'block';
    caixa.style.display = aberto ? 'none' : 'block';
    bolha.textContent = aberto ? '💬' : '×';
    bolha.setAttribute('aria-label', aberto ? 'Abrir chat' : 'Fechar chat');
  });
  function montar() { document.body.appendChild(caixa); document.body.appendChild(bolha); }
  if (document.body) montar(); else document.addEventListener('DOMContentLoaded', montar);
})();
