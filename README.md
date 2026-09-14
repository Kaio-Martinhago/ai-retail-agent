# 🤖 Sistema Inteligente de Estoque & Atendimento IA

Um ecossistema completo para gestão de catálogos e atendimento automatizado, utilizando Modelos de Linguagem de Grande Escala (LLMs) e Visão Computacional multimodal.

## 📌 Visão Geral do Projeto

Este projeto resolve o problema da automação no comércio varejista (focado em calçados). O sistema atua em duas frentes:
1. **Pipeline de Ingestão (Visão Computacional):** Uma interface web onde o lojista faz upload de fotos brutas. A IA multimodal extrai automaticamente características semânticas (cor, estilo, materiais) dispensando o cadastro manual demorado.
2. **Agente Conversacional (Vendas):** Um bot no Telegram com memória de contexto (Sliding Window). Ele cruza as solicitações do cliente em linguagem natural com o banco de dados local, oferecendo produtos, checando disponibilidade de numeração na grade e enviando fotos dinamicamente.

## ⚙️ Arquitetura e Tecnologias

*   **Linguagem Core:** Python 3.10+
*   **Inteligência Artificial:** Google Gemini 3.5 Flash Lite (API) para classificação visual *Zero-Shot* e geração de texto conversacional.
*   **Banco de Dados:** SQLite3 relacional integrado.
*   **Integração Bot:** `pyTelegramBotAPI` (Telebot).
*   **Processamento de Imagem:** `Pillow` (PIL) com correção nativa de metadados EXIF.

---

## 🚀 Como Configurar e Executar

Para rodar este projeto na sua máquina local, siga o passo a passo rigorosamente. Como o banco de dados é persistente (SQLite), você pode rodar a alimentação do estoque primeiro e depois executar o bot de atendimento.

### 1. Clonar e Instalar Dependências
Faça o clone deste repositório e, na pasta raiz do projeto, instale as bibliotecas necessárias:
```bash
pip install flask pyTelegramBotAPI google-genai pillow python-dotenv
```

### 2. Configurar as Chaves de Acesso (Variáveis de Ambiente)
Crie um arquivo chamado `.env` na raiz do projeto. Você precisará de duas chaves:
1. **GEMINI_API_KEY:** Gerada no [Google AI Studio](https://aistudio.google.com/).
2. **TELEGRAM_TOKEN:** Gerado no Telegram conversando com o `@BotFather` (envie `/newbot`, escolha o nome e copie o token HTTP API).

O seu arquivo `.env` deve ficar exatamente assim:
```env
GEMINI_API_KEY=cole_sua_chave_do_google_aqui
TELEGRAM_TOKEN=cole_seu_token_do_telegram_aqui
```

### 3. Iniciando o Motor de Ingestão (Painel Web)
Abra seu terminal, navegue até a pasta do projeto e inicie o painel web:
```bash
python admin_web.py
```
* Acesse `http://127.0.0.1:5000` no seu navegador.
* Arraste fotos de calçados para a área de upload. A IA fará a análise.
* Preencha a grade de numeração e o preço. Clique em "Salvar Calçado" para efetivar o item no Estoque Ativo.
* Após terminar de cadastrar o estoque, você pode encerrar o servidor no terminal (`Ctrl + C`).

### 4. Iniciando o Agente de Atendimento (Bot Telegram)
Com o estoque cadastrado, inicie o agente do Telegram no seu terminal:
```bash
python main.py
```
* O terminal exibirá `🤖 Agente Operacional: Escutando o Telegram...`
* Abra o seu Telegram, busque pelo *username* do bot que você criou no BotFather e mande um `/start`.
* Após isso, tudo estará pronto para você testar o bot livremente.
