const {chromium} = require('/home/nmaldaner/projetos/agent-browser/node_modules/playwright');
const [BASE, SITE, TEMA] = process.argv.slice(2);
const SAIDA = '/home/nmaldaner/projetos/output/atende-leads-visual/178/';
const TOKEN = 'segredo-teste';
const ok = (c, m) => { if (!c) throw new Error('FALHOU: ' + m); console.log('  ok:', m); };
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({viewport: {width: 1366, height: 900}});
  await ctx.addInitScript(t => { try { localStorage.setItem('al_tema', t); } catch (e) {} }, TEMA);
  const pg = await ctx.newPage();
  const erros = []; pg.on('pageerror', e => erros.push(String(e)));
  const api = async (m, r, corpo) => { const res = await pg.request.fetch(BASE + r, {method: m, headers: {'X-Token': TOKEN, 'Content-Type': 'application/json'}, data: corpo ? JSON.stringify(corpo) : undefined}); return res.json(); };
  await pg.goto(BASE + '/gestor');
  await pg.fill('#token', TOKEN); await pg.click('#form-login button[type=submit]');
  await pg.waitForSelector('#painel:not([hidden])');
  ok(await pg.evaluate(() => document.documentElement.dataset.tema) === TEMA, 'tema ' + TEMA);

  // 1) link → propostas
  await pg.click('#t-base');
  await pg.fill('#fo-url', SITE + '/'); await pg.fill('#fo-max', '5'); await pg.click('#fo-ler');
  await pg.waitForSelector('.fonte-it .st-pronto', {timeout: 20000});
  const det = await pg.textContent('.fonte-it .det');
  ok(/3 páginas/.test(det) && /3 propostas/.test(det), 'fonte lida: ' + det.trim());
  if (TEMA === 'marinho') await pg.screenshot({path: SAIDA + 'marinho-importar-link.png', fullPage: false});
  await pg.click('.fonte-it [data-ir="aprendizado"]');
  await pg.waitForSelector('[data-prop]');
  ok(await pg.locator('.proposta .de-fonte a').count() === 3, 'cada proposta mostra a URL da fonte');
  ok(await pg.locator('.proposta .evid').count() === 3, 'cada proposta mostra a evidência');
  ok(await pg.locator('.selo.contradiz').count() === 2, 'marca "contradiz a base"');
  // 2) incorporar selecionadas (lote, prévia única)
  const ids = await pg.$$eval('[data-sel]', xs => xs.map(x => x.dataset.sel));
  for (const id of ids) await pg.check('[data-sel="' + id + '"]');
  ok((await pg.textContent('#a-lote-n')).includes('3 propostas'), 'contador do lote');
  await pg.click('#a-lote-btn');
  await pg.waitForSelector('#a-lote-previa:not([hidden]) li');
  ok(await pg.locator('#a-lote-previa li').count() === 3, 'prévia única com as 3');
  ok((await pg.textContent('#a-lote-previa')).includes('Cadastros → Produtos → Plano anual'), 'prévia diz o que vai alterar');
  if (TEMA === 'claro') await pg.screenshot({path: SAIDA + 'claro-aprendizado-fonte-lote.png', fullPage: true});
  await pg.click('#a-lote-ok');
  await pg.waitForFunction(() => /3 incorporada/.test(document.getElementById('aviso').textContent));
  const cfg = await api('GET', '/api/gestor/config');
  ok(cfg.produtos.find(p => p.id === 'plano-anual').preco === 'R$ 999', 'preço incorporado');
  ok(cfg.produtos.some(p => p.nome === 'Bolo de cenoura'), 'produto novo incorporado');
  ok(/CEP 80000-000/.test(cfg.info.endereco), 'endereço incorporado');

  // 3) chat da base
  await pg.click('#t-consolidada');
  await pg.fill('#bc-pergunta', 'qual o horário?'); await pg.press('#bc-pergunta', 'Enter');
  await pg.waitForSelector('#bc-conv .fontes-b');
  ok((await pg.textContent('#bc-conv')).includes('FAQ: qual o horario de atendimento'), 'resposta cita a seção');
  await pg.click('#bc-conv [data-conf-ir]');
  ok(await pg.locator('#bc-conflitos li.foco').count() === 1, '"ver conflito" leva ao conflito da lista');
  await pg.fill('#bc-pergunta', 'vocês entregam?'); await pg.press('#bc-pergunta', 'Enter');
  await pg.waitForSelector('[data-criar-prop]');
  await pg.click('[data-criar-prop]');
  ok(await pg.inputValue('#np-tipo') === 'info' && await pg.inputValue('#np-campo') === 'entrega', 'formulário pré-preenchido pela lacuna');
  await pg.fill('#np-resp', 'Entregamos em Curitiba em até 2 dias úteis.');
  if (TEMA === 'escuro') { await pg.evaluate(() => document.getElementById('bc-chat').scrollIntoView({block: 'start'})); await pg.waitForTimeout(300); await pg.screenshot({path: SAIDA + 'escuro-chat-da-base.png'}); }
  await pg.click('#np-criar');
  await pg.waitForFunction(() => /Proposta #\d+ criada/.test(document.getElementById('aviso').textContent));
  const ps = await api('GET', '/api/gestor/propostas?status=nova');
  ok(ps.some(p => p.origem === 'chat' && p.campo === 'entrega'), 'proposta do chat na fila do Aprendizado');

  // 4) Atualizar: config mudada por outra requisição aparece sem sair
  await pg.click('#t-cadastros');
  const c2 = await api('GET', '/api/gestor/config'); c2.nome = 'Loja Atualizada'; c2.token_gestor = '***';
  await api('PUT', '/api/gestor/config', c2);
  ok(await pg.inputValue('#c-nome') === 'Loja Teste', 'antes de atualizar: valor velho');
  await pg.click('#atualizar');
  await pg.waitForFunction(() => document.getElementById('c-nome').value === 'Loja Atualizada');
  ok(/Atualizado às \d\d:\d\d/.test(await pg.textContent('#atualizado')), '"Atualizado às HH:MM"');
  ok(await pg.inputValue('#c-urlpub') === 'https://loja.exemplo.test', 'Cadastros mostra o endereço público (id único)');
  await pg.fill('#c-nome', 'Rascunho não salvo');
  await pg.click('[data-painel="cadastros"] [data-atualizar]');
  await pg.waitForSelector('#confirma');
  ok((await pg.textContent('#confirma')).includes('Descartar alterações e atualizar?'), 'pergunta na página antes de descartar');
  await pg.click('#confirma [data-nao]');
  ok(await pg.inputValue('#c-nome') === 'Rascunho não salvo', 'cancelar mantém o que foi digitado');
  await pg.click('#c-estado'); await pg.keyboard.press('r');
  await pg.waitForSelector('#confirma');
  await pg.click('#confirma [data-sim]');
  await pg.waitForFunction(() => document.getElementById('c-nome').value === 'Loja Atualizada');
  ok(true, 'tecla R + descartar → valor do servidor');

  // 5) equipe
  const eq = await ctx.newPage(); eq.on('pageerror', e => erros.push(String(e)));
  await eq.goto(BASE + '/equipe'); await eq.fill('#codigo', 'ana-1234-teste'); await eq.click('#form-login button[type=submit]');
  await eq.waitForSelector('#atualizar-w:not([hidden])');
  await api('POST', '/api/gestor/equipe/ana/status', {status: 'livre'});
  ok(await eq.getAttribute('[data-status="livre"]', 'aria-pressed') === 'false', 'equipe: antes, fora');
  await eq.click('#atualizar');
  await eq.waitForFunction(() => /Atualizado às/.test(document.getElementById('atualizado').textContent));
  ok(await eq.getAttribute('[data-status="livre"]', 'aria-pressed') === 'true', 'equipe: Atualizar relê o status');
  ok(!erros.length, 'sem erro de JavaScript ' + erros.join(' | '));
  await b.close();
})().catch(async e => { console.error(e.message || e); process.exit(1); });
