# Site público: Vercel + Render + gateway local

Nenhum deploy, criação de conta, commit ou push foi executado automaticamente.
Os arquivos estão preparados para você revisar e publicar.

## O que roda onde

| Parte | Execução | Função |
|---|---|---|
| Gateway | PC, `python app_radio.py` | Reutiliza serial/parser/estado e envia snapshot HTTPS aproximadamente a cada segundo |
| Backend | Render, Flask/Socket.IO + Gunicorn | Um processo, estado atual em RAM, autenticação da escrita e expiração |
| Frontend | Vercel, HTML estático | Mesmo visual do Flask, recebe estado por Socket.IO; fallback HTTP e offline |

Não há Supabase, banco, disco de dados, login, cadastro ou histórico online.
O histórico limitado já existente no aplicativo local foi preservado para não
alterar suas funcionalidades/testes, mas **não é enviado nem armazenado online**.
O backend não lê micro:bit, USB ou linhas seriais; recebe um snapshot normalizado.

## 1. Publicar a alteração no seu GitHub

Revise `git status` e `git diff`, faça o commit e o push quando decidir publicar.
Render/Vercel usarão o código da branch selecionada em
`https://github.com/dabulkase-ux/estacao-radio`.
Não inclua arquivos `.env` ou tokens no commit. `.env.example` contém somente
nomes/valores ilustrativos. Copiado para `.env`, é carregado pelos launchers Windows;
o comando direto `python app_radio.py` continua usando o ambiente do terminal.

## 2. Criar o segredo do gateway

No seu computador:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Guarde o resultado: será o mesmo valor de `GATEWAY_TOKEN` no Render e
`MICROSERIAL_GATEWAY_TOKEN` no PC. Ele **nunca** deve ir para a Vercel, JavaScript,
URL ou repositório. Se vazar, gere outro e substitua nos dois lugares.

## 3. Criar o backend no Render

1. No Render, escolha **New → Blueprint** e conecte o repositório e a branch com
   estas alterações. O arquivo `render.yaml` configura um Web Service Python Free.
2. Preencha as variáveis solicitadas:
   - `GATEWAY_TOKEN`: segredo do passo anterior.
   - `FRONTEND_ORIGINS`: origem prevista do frontend, por exemplo
     `https://estacao-radio.vercel.app`. Corrija no passo 5 se a URL efetiva for outra.
3. Confirme a criação/deploy. Nenhum banco é necessário.
4. Copie a URL HTTPS do serviço, por exemplo `https://estacao-radio-backend-xxxx.onrender.com`.
5. Abra `<URL>/health` e `<URL>/api/data`. Deve aparecer `connected: false` e
   `stations: {}` antes da primeira publicação do gateway.

Se preferir **New → Web Service** sem Blueprint, configure:

```text
Runtime: Python
Root Directory: raiz do repositório (deixar vazio)
Build: pip install -r requirements-backend.txt
Start: gunicorn --worker-class gthread --workers 1 --threads 40 --bind 0.0.0.0:$PORT online_wsgi:app
Health check: /health
```

Use **uma instância e um worker**, sem `--preload`. O estado e os clientes Socket.IO
ficam no mesmo processo; múltiplos workers/instâncias criariam estados distintos.
Gunicorn é usado no Linux do Render; para teste no Windows existe
`python backend_online.py` na porta local 5001.

## 4. Criar o frontend na Vercel

1. Escolha **Add New → Project** e importe o mesmo repositório/branch.
2. Root Directory: raiz do repositório. Framework Preset: **Other**.
3. Em Environment Variables, adicione **somente**:
   `RADIO_BACKEND_URL=https://URL-DO-BACKEND.onrender.com`.
   Use a origem sem `/api`, caminhos, credenciais ou token.
4. O `vercel.json` já define:
   - Build: `node tools/build_frontend.js`.
   - Output Directory: `dist`.
   - Instalação: nenhum pacote npm necessário.
5. Faça o deploy e copie a URL pública efetivamente atribuída.

O build reutiliza `templates/index.html` e injeta apenas a URL pública e o modo
somente leitura. O resultado é `dist/index.html`; não há função Python na Vercel.
Se mudar `RADIO_BACKEND_URL`, faça **Redeploy**, pois ela é incorporada no build.
`estacao-radio.vercel.app` é um exemplo, sujeito à disponibilidade do nome.
Se a Vercel ativar proteção de acesso no projeto, permita acesso público à
produção para abrir em celulares/navegadores sem login; previews podem ter outra política.

## 5. Ajustar a origem permitida no Render

Defina `FRONTEND_ORIGINS` com a URL efetiva da Vercel **sem barra final ou caminho**,
por exemplo `https://estacao-radio.vercel.app`. Salve e aplique o redeploy do backend.
Para mais de um endereço, separe origens exatas por vírgula (domínio próprio,
preview que queira testar etc.). Não use `*`.

A leitura é pública. CORS restringe o uso por navegadores, mas a proteção da escrita
é o token Bearer verificado no servidor, não CORS.

## 6. Executar o gateway no PC

**Uso diário no Windows:** conecte a Central e dê dois cliques em `iniciar.bat`.
Na primeira vez, tenha Python 3.10+ no PATH, copie `.env.example` para `.env` e
preencha o token privado igual ao `GATEWAY_TOKEN` do Render. O launcher prepara
`.venv` e as dependências automaticamente, sem imprimir o segredo. `.env NÃO
deve ser commitado`. O arquivo tem prioridade sobre variáveis do terminal quando
usado pelo launcher; o modo manual abaixo continua disponível sem mudanças.

Endereços atuais informados pelo responsável pelo projeto:

- Frontend: https://estacao-radio-gules.vercel.app/
- Backend: https://estacao-radio-backend.onrender.com

`iniciar-local.bat` mantém também a interface local; ambos usam o mesmo setup.
Se uma instalação de dependências falhar, corrija internet/permissões e execute
novamente: versões faltantes serão verificadas outra vez. Não é preciso colocar
nenhum token no script ou definir `$env:` para usar os launchers.

Instalação inicial (PowerShell):

```powershell
git clone https://github.com/dabulkase-ux/estacao-radio.git
cd estacao-radio
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Em cada terminal no qual for executar (ou configure as variáveis no ambiente do usuário):

```powershell
$env:MICROSERIAL_BACKEND_URL = "https://SEU-BACKEND.onrender.com"
$env:MICROSERIAL_GATEWAY_TOKEN = "COLE-O-MESMO-SEGREDO-DO-RENDER"
.\.venv\Scripts\python.exe app_radio.py
```

Para não hospedar nem mesmo a interface local:

```powershell
.\.venv\Scripts\python.exe app_radio.py --gateway-only
```

Conecte a Central por USB e ligue as Estações. A descoberta da Central, assinatura
`CENTRAL_ONLINE|1`, parser e tratamento NPART/CMD continuam os existentes.
Se necessário, defina `MICROSERIAL_PORT=COM5` como antes.

O gateway transmite somente estado atual, sem backlog. Falhas de internet não
bloqueiam a leitura serial; novas tentativas usam esperas de 2, 4, 8 e até 10 s.
Após o backend voltar, o snapshot seguinte reconstrói seu estado.

## 7. Demonstrar

1. Abra a URL Vercel no PC ou celular de outra rede, sem executar Python: Central offline.
2. Ligue Central/Estação e execute o gateway: Central online, Conexão USB Serial,
   QUARTO online e som atual, substituindo o valor anterior.
3. Pare a Estação: offline após o timeout de sinal, 5 s por padrão.
4. Feche o Python/desligue o PC: Central e estações offline após cerca de 10 s
   mais o ciclo de atualização (até ~1 s); o site permanece acessível.
5. Execute novamente: o mesmo site recebe o estado sem recarregar.

A página pública é **somente leitura**. O botão de PING foi preservado na
interface local em `http://127.0.0.1:5000`; não criamos comandos públicos de rádio.
Quando o backend não responde, a página marca os cards offline, preserva os
últimos valores como última leitura e reconecta automaticamente. Esses valores
no navegador não significam que a Estação continua online.

## Estado e API mínima

- `POST /api/gateway/state`: exige `Authorization: Bearer <segredo>`; JSON de até 64 KiB,
  no máximo 64 Estações. Token ausente/incorreto: 401; payload inválido: 400/413.
- `GET /api/data`: leitura pública, sem cache, somente estado atual.
- Socket.IO `radio_data`: estado inicial, atualizações e expiração automática.
- `GET /health`: disponibilidade do processo, independente de gateway/Central.

Exemplo do corpo enviado pelo gateway (o token fica somente no header):

```json
{
  "connected": true,
  "transport": "serial",
  "stations": {
    "QUARTO": {"name": "Quarto", "sound": 51, "connected": true, "interval": 0.5, "age": 0.2}
  }
}
```

`age` é a idade em segundos da última leitura válida, não o horário do computador.
O backend usa relógio monotônico para expirar estações/gateway. Reenviar dados
velhos não renova a presença. A regra de Estação foi preservada: **qualquer sinal
válido** (heartbeat, som, identificação etc.) conta; não exigimos exclusivamente H.
O timeout `MICROSERIAL_STATION_TIMEOUT` deve coincidir entre PC e Render se alterado.

Um gateway autorizado por vez é o uso previsto. Dois gateways usando o mesmo
segredo alternariam/substituiriam o estado. Não há armazenamento permanente:
após reiniciar o backend, ele pode voltar vazio até receber o próximo snapshot.
Som/nome/ID são preservados enquanto o processo vive, inclusive nos cards offline.
`transport: "bluetooth"` é aceito no contrato para um futuro gateway; nenhum BLE
foi implementado. Tokens não são expostos aos espectadores.

## Hospedagem e limites

A Vercel permanece somente com arquivos estáticos. A documentação atual admite
WebSockets em Functions, mas limita a conexão à duração da função e não garante
que conexões futuras cheguem à mesma instância. Por isso um único backend persistente
no Render é mais adequado para este estado compartilhado em RAM, sem Redis/banco.
[Referência oficial Vercel](https://vercel.com/kb/guide/do-vercel-serverless-functions-support-websocket-connections).

O Render aceita WebSockets em Web Services. Não impõe um prazo fixo à conexão,
mas deploys/reinícios/interrupções a encerram; o cliente reconecta.
[Referência WebSockets](https://render.com/docs/websocket).

No Free, após **15 minutos sem tráfego de entrada**, o serviço dorme; a próxima
requisição/conexão o desperta, normalmente em cerca de **um minuto**. Há **750 horas
gratuitas por workspace/mês**, compartilhadas entre serviços, além de quotas de
banda/build; esgotá-las pode suspender serviços. Reinícios também são possíveis.
O site estático continua abrindo e mostra offline durante a indisponibilidade do
backend. Se precisar backend sempre pronto, use uma instância paga e confira as
condições atuais. Nenhum plano gratuito representa uma garantia de disponibilidade.
[Limites oficiais Free](https://render.com/docs/free) (consultados em 25/09/2026).

O processo com 40 threads é para uma demonstração pequena, não milhares de
espectadores. A página ainda usa o CDN Socket.IO já existente, com fallback HTTP
se essa biblioteca não carregar. Não há alterações na rede física nem no firmware.

## Testes executados e o que falta

```powershell
python -m unittest discover -s tests -v
node tests/frontend_test.js
node tests/frontend_online_test.js
node --disable-warning=ExperimentalWarning tests/rede_sim.js
```

22 testes Python aprovados (11 existentes + 11 online), 16 cenários do protocolo
existente e testes JavaScript do frontend local e público aprovados.
As dependências do gateway foram conferidas com `pip install --dry-run -r requirements.txt`.
Na retomada, o dry-run de `requirements-backend.txt` também passou no Windows
(Gunicorn é instalado somente no Linux). `pip check` encontrou pendências de
`personal-jarvis` no Python global, sem relação com este projeto; não foi feita
instalação limpa em `.venv`. Use o ambiente virtual indicado acima.
Build estático, sintaxe Python/JavaScript e `git diff --check` passaram. O frontend
também foi testado com resposta HTTP lenta e sem `AbortSignal.timeout`.
O envio do gateway e Socket.IO por HTTP long-polling foram testados com servidor
**real no loopback**. Expiração/reinício/reconexão também têm testes determinísticos;
o JavaScript do frontend foi executado com DOM simulado e backend indisponível.

Não foi feito deploy no Render/Vercel, teste de WebSocket público através desses
provedores, ensaio visual em navegador/celular nem novo teste físico de micro:bit.
Após publicar, execute a demonstração do passo 7 e confirme CORS, TLS, atualização,
desligamento/reconexão e comportamento do cold start. O Gunicorn Linux do Render
não foi executado neste ambiente Windows.
