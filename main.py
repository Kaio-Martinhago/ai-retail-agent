import os
import re
import json
import sqlite3
import socket
import logging
import telebot
from google import genai
from google.genai import types
from dotenv import load_dotenv
from io import BytesIO
from PIL import Image, ImageOps

socket.setdefaulttimeout(15)
load_dotenv()

# Silencia os avisos (warnings) internos do Google e requisições no terminal
logging.getLogger("google").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not GEMINI_API_KEY or not TELEGRAM_TOKEN:
    raise ValueError("ERRO CRÍTICO: Chaves de API não encontradas no .env!")

client = genai.Client(api_key=GEMINI_API_KEY)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

def obter_estoque_atualizado():
    try:
        conn = sqlite3.connect('catalogo_loja.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT nome, marca, preco, cor_principal, estilo, palavras_chave, caminho_imagem, grade 
            FROM produtos
        ''')
        linhas = cursor.fetchall()
        conn.close()
        
        catalogo = []
        for linha in linhas:
            catalogo.append({
                "nome": linha[0], "marca": linha[1], "preco": linha[2],
                "cor_principal": linha[3], "estilo": linha[4], 
                "palavras_chave": linha[5], "caminho_imagem": linha[6],
                "grade": linha[7] if len(linha) > 7 else ""
            })
        return catalogo
    except sqlite3.OperationalError:
        print("⚠️ Aviso: Banco 'catalogo_loja.db' não encontrado.")
        return []

memoria_conversas = {}
LIMITE_HISTORICO = 10 

def obter_resposta_ia(chat_id, mensagem_cliente, nome_cliente):
    estoque_agora = obter_estoque_atualizado()
    
    prompt_sistema = f"""Você é um vendedor humano de calçados no WhatsApp.
O nome do cliente é {nome_cliente}. Trate-o pelo nome com simpatia.
Estoque atual: {json.dumps(estoque_agora, ensure_ascii=False)}

DIRETRIZES DE COMUNICAÇÃO (OBRIGATÓRIO):
1. FALE COMO HUMANO: NUNCA leia as chaves do sistema. Transforme os dados em UMA ÚNICA frase natural.
2. ZERO FORMATAÇÃO: PROIBIDO usar listas, asteriscos ou travessões.
3. ENVIO DE FOTO OBRIGATÓRIO: NUNCA pergunte "posso mandar a foto?". Você DEVE SEMPRE colocar a tag [FOTO: caminho_do_arquivo] logo após descrever o produto.
4. GESTÃO DE NUMERAÇÃO (CRÍTICO): 
   - A chave 'grade' indica os tamanhos disponíveis e a quantidade (ex: "38:1" significa tamanho 38, 1 unidade). 
   - Se o cliente informar o tamanho que calça (ex: "calço 39"), mostre APENAS produtos que tenham o tamanho 39 na grade. 
   - Se não tiver o tamanho, peça desculpas informando que esgotou aquela numeração e sugira perguntar sobre outro modelo.
   - Se o cliente não falou o tamanho ainda, mostre as opções de modelos e pergunte: "Qual tamanho você calça para eu verificar a disponibilidade?"

MÚLTIPLAS OPÇÕES E TEMPLATE EXATO:
Se for oferecer mais de uma opção, separe os produtos ESTRITAMENTE por três traços (---):

Olha que linda essa Sandália com salto bloco, super elegante! [FOTO: caminho_imagem_1]
---
Também tenho essa Mississipi off-white mais casual pro dia a dia. [FOTO: caminho_imagem_2]
---
Qual dessas você mais gostou? E me diz seu tamanho para eu ver se sobrou na grade!

REGRA DO PREÇO:
- Se o preço for 0.0, NÃO FALE O PREÇO.
- Se tiver preço, integre na frase: "Temos essa sandália por R$ 159,90! [FOTO: caminho_imagem]"

REGRA DO SILÊNCIO:
Se o cliente disser "ok", "entendi", "valeu", responda EXATAMENTE E APENAS: [SILENCIO]
"""

    if chat_id not in memoria_conversas:
        memoria_conversas[chat_id] = []

    memoria_conversas[chat_id].append(
        types.Content(role="user", parts=[types.Part.from_text(text=mensagem_cliente)])
    )

    if len(memoria_conversas[chat_id]) > LIMITE_HISTORICO:
        memoria_conversas[chat_id] = memoria_conversas[chat_id][-LIMITE_HISTORICO:]

    try:
        resposta = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=memoria_conversas[chat_id],
            config=types.GenerateContentConfig(
                system_instruction=prompt_sistema,
                temperature=0.2
            )
        )
        
        resposta_texto = resposta.text
        memoria_conversas[chat_id].append(
            types.Content(role="model", parts=[types.Part.from_text(text=resposta_texto)])
        )
        return resposta_texto

    except Exception as e:
        print(f"[ERRO GEMINI] - {e}")
        memoria_conversas[chat_id].pop() 
        return "Desculpe, a internet aqui da loja deu uma oscilada rápida. Pode repetir, por favor?"

@bot.message_handler(commands=['start'])
def saudacao_inicial(message):
    chat_id = message.chat.id
    nome_cliente = message.from_user.first_name
    bot.send_chat_action(chat_id, 'typing')
    memoria_conversas.pop(chat_id, None)
        
    texto = f"Olá, {nome_cliente}! Seja bem-vindo(a). O que você está procurando hoje? 👟"
    bot.send_message(chat_id, texto)

@bot.message_handler(func=lambda message: message.text is not None)
def responder_cliente(message):
    chat_id = message.chat.id
    texto_usuario = message.text.strip()
    nome_cliente = message.from_user.first_name

    if not texto_usuario:
        return

    print(f"[{nome_cliente}]: {texto_usuario}")
    
    # Aciona o "Digitando..." para o cliente não achar que o bot travou
    bot.send_chat_action(chat_id, 'typing')

    resposta_ia = obter_resposta_ia(chat_id, texto_usuario, nome_cliente)

    if "[SILENCIO]" in resposta_ia:
        return

    blocos_mensagem = resposta_ia.split('---')

    for bloco in blocos_mensagem:
        bloco = bloco.strip()
        if not bloco: continue

        padrao_foto = r'(?i)(?:\[|<)?FOTO:\s*(.*?)(?:\]|>|\n|$)'
        match = re.search(padrao_foto, bloco)

        if match:
            caminho_imagem = match.group(1).strip()
            texto_limpo = re.sub(padrao_foto, '', bloco).strip()
            texto_limpo = re.sub(r'(?i)(nome|marca|cor_principal|estilo|palavras_chave|preco|grade):\s*.*', '', texto_limpo).strip()
            
            try:
                if caminho_imagem.startswith('http'):
                    bot.send_photo(chat_id, caminho_imagem, caption=texto_limpo, timeout=60)
                else:
                    if not os.path.exists(caminho_imagem):
                        raise FileNotFoundError(f"Caminho não encontrado: {caminho_imagem}")

                    with Image.open(caminho_imagem) as img:
                        img = ImageOps.exif_transpose(img)
                        img.thumbnail((800, 800))
                        buffer = BytesIO()
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        img.save(buffer, format="JPEG", quality=50, optimize=True)
                        buffer.seek(0)
                    
                    bot.send_photo(chat_id, buffer, caption=texto_limpo, timeout=60)
            except Exception as e:
                bot.send_message(chat_id, texto_limpo + "\n\n*(Ops, a foto sumiu do nosso estoque!)*", parse_mode="Markdown")
        else:
            bloco_limpo = re.sub(r'(?i)(nome|marca|cor_principal|estilo|palavras_chave|preco|grade):\s*.*', '', bloco).strip()
            if bloco_limpo:
                bot.send_message(chat_id, bloco_limpo)

print("🤖 Agente Operacional: Escutando o Telegram...")
bot.infinity_polling(skip_pending=True, timeout=10, long_polling_timeout=5)