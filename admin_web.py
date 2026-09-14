import os
import json
import sqlite3
import re
import time
from flask import Flask, request, jsonify, render_template_string, Response, send_from_directory
from werkzeug.utils import secure_filename
from google import genai
from google.genai import types
from dotenv import load_dotenv
from PIL import Image

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("ERRO CRÍTICO: Chave GEMINI_API_KEY não encontrada no .env")

client = genai.Client(api_key=GEMINI_API_KEY)
app = Flask(__name__)

DIRETORIO_ALVO = 'fotos_estoque'
os.makedirs(DIRETORIO_ALVO, exist_ok=True)
app.config['UPLOAD_FOLDER'] = DIRETORIO_ALVO

def inicializar_banco():
    conn = sqlite3.connect('catalogo_loja.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL, marca TEXT NOT NULL, preco REAL NOT NULL,
            cor_principal TEXT, estilo TEXT, palavras_chave TEXT,
            caminho_imagem TEXT UNIQUE NOT NULL, data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    try:
        cursor.execute("ALTER TABLE produtos ADD COLUMN grade TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass 
    conn.commit()
    return conn

def analisar_calcado(caminho_imagem, preco_sugerido):
    prompt_extracao = f"""Atue como classificador especialista. Preço base: R$ {preco_sugerido:.2f}.
REGRA: Ignore logotipos. A marca SEMPRE será "Genérica". Foque só no visual.
Retorne EXCLUSIVAMENTE JSON:
{{
    "nome": "Nomenclatura (máx 4 palavras)",
    "marca": "Genérica",
    "preco": {preco_sugerido},
    "cor_principal": "Cor predominante",
    "estilo": "Categoria principal (ex: Bota, Tênis, Sandália)",
    "palavras_chave": "Lista de 8 a 12 características visíveis separadas por vírgula"
}}"""
    try:
        imagem = Image.open(caminho_imagem)
        resposta = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=[imagem, prompt_extracao],
            config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json")
        )
        json_limpo = resposta.text.replace('```json', '').replace('```', '').strip()
        dados = json.loads(json_limpo)
        dados["caminho_imagem"] = caminho_imagem
        return dados
    except Exception as e:
        print(f"\n❌ ERRO DA IA AO LER '{caminho_imagem}': {e}")
        return None

HTML_PAGE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cadastro de Produtos</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        input[type=number]::-webkit-inner-spin-button, input[type=number]::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
        input[type=number] { -moz-appearance: textfield; }
        .scrollbar-hide::-webkit-scrollbar { display: none; }
    </style>
</head>
<body class="bg-slate-50 font-sans min-h-screen text-slate-800">

    <nav class="bg-slate-900 text-white shadow-md p-4 flex justify-between items-center">
        <div class="flex items-center space-x-3">
            <i class="fa-solid fa-microchip text-indigo-400 text-xl"></i>
            <h1 class="text-xl font-bold tracking-wide">Cadastro de Produtos com IA</h1>
        </div>
    </nav>

    <div class="max-w-[1400px] mx-auto p-6 grid grid-cols-1 lg:grid-cols-4 gap-6">
        
        <div class="lg:col-span-1 space-y-6">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <h2 class="text-lg font-bold mb-4 flex items-center"><i class="fa-solid fa-upload mr-2 text-indigo-500"></i> Lote de Imagens</h2>
                <div id="dropZone" class="border-2 border-dashed border-slate-300 rounded-xl p-6 text-center cursor-pointer hover:border-indigo-400 relative group bg-slate-50 transition">
                    <input type="file" id="fileInput" multiple accept=".png, .jpg, .jpeg, .webp" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10">
                    <i class="fa-solid fa-image text-3xl text-slate-400 mb-2 group-hover:text-indigo-500 transition"></i>
                    <p class="text-sm font-medium text-slate-600">Arraste fotos do estoque</p>
                </div>
                <button id="btnProcessar" class="w-full mt-4 bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2.5 px-4 rounded-xl transition shadow-md hidden">Processar na IA</button>
            </div>
            
            <div id="previewCard" class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden hidden">
                <div class="bg-slate-100 p-3 border-b flex justify-between items-center">
                    <span class="text-xs font-bold text-slate-500 uppercase tracking-wider">Monitoramento</span>
                    <span id="previewStatus" class="text-xs font-bold px-2 py-1 rounded bg-indigo-100 text-indigo-700">Aguardando...</span>
                </div>
                <div class="p-4 flex flex-col items-center">
                    <img id="liveImage" src="" class="w-full h-48 object-cover rounded-lg shadow-inner mb-4 border border-slate-200">
                    <p id="liveFileName" class="text-xs font-mono text-slate-500 mb-2 break-all text-center"></p>
                    <div id="liveLabels" class="w-full text-sm flex flex-wrap gap-1 justify-center mt-2"></div>
                </div>
            </div>
        </div>

        <div class="lg:col-span-3 bg-white rounded-2xl shadow-sm border border-slate-200 flex flex-col h-[80vh]">
            
            <div class="flex border-b border-slate-200">
                <button onclick="switchTab('pendentes')" id="tab-btn-pendentes" class="flex-1 py-3 text-sm font-bold text-indigo-600 border-b-2 border-indigo-600 transition flex justify-center items-center gap-2">
                    Fila de Curadoria <span id="count-pendentes" class="bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full text-xs">0</span>
                </button>
                <button onclick="switchTab('salvos')" id="tab-btn-salvos" class="flex-1 py-3 text-sm font-semibold text-slate-400 hover:text-slate-600 border-b-2 border-transparent transition flex justify-center items-center gap-2">
                    Estoque Ativo <span id="count-salvos" class="bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full text-xs">0</span>
                </button>
            </div>

            <div id="catalogoGrid" class="flex-1 overflow-y-auto p-6 grid grid-cols-1 md:grid-cols-2 gap-4 items-start content-start bg-slate-50">
                <!-- Render via JS -->
            </div>
        </div>
    </div>

    <script>
        let allProducts = [];
        let currentTab = 'pendentes';
        let editingId = null; 

        const fileInput = document.getElementById('fileInput');
        const btnProcessar = document.getElementById('btnProcessar');
        const previewCard = document.getElementById('previewCard');
        const standardSizes = [33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44];

        document.addEventListener('DOMContentLoaded', carregarCatalogo);

        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                btnProcessar.classList.remove('hidden');
                btnProcessar.textContent = `Processar ${fileInput.files.length} Imagens`;
            }
        });

        btnProcessar.addEventListener('click', async () => {
            const files = fileInput.files;
            if (files.length === 0) return;
            btnProcessar.disabled = true;
            btnProcessar.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Preparando...';
            previewCard.classList.remove('hidden');
            switchTab('pendentes'); 

            const formData = new FormData();
            for (let i = 0; i < files.length; i++) formData.append('fotos', files[i]);

            try {
                const response = await fetch('/upload', { method: 'POST', body: formData });
                const result = await response.json();
                if (result.sucesso) iniciarStream(result.arquivos.join(','));
            } catch (err) { alert("Erro de rede."); }
        });

        function iniciarStream(filenames) {
            const ev = new EventSource(`/process_stream?files=${encodeURIComponent(filenames)}`);
            ev.onmessage = function(event) {
                const data = JSON.parse(event.data);
                
                if (data.image_url) {
                    document.getElementById('liveImage').src = data.image_url;
                    document.getElementById('liveFileName').textContent = data.filename;
                }
                
                const st = document.getElementById('previewStatus');
                const ll = document.getElementById('liveLabels');
                
                if (data.status === 'processing') {
                    st.className = "text-xs font-bold px-2 py-1 rounded bg-blue-100 text-blue-700";
                    st.innerHTML = '<i class="fa-solid fa-eye fa-fade mr-1"></i> Analisando...';
                    ll.innerHTML = '<span class="text-slate-400 italic text-xs">Aguardando IA...</span>';
                } else if (data.status === 'duplicate') {
                    st.className = "text-xs font-bold px-2 py-1 rounded bg-amber-100 text-amber-700";
                    st.innerHTML = '<i class="fa-solid fa-copy mr-1"></i> Duplicada';
                    ll.innerHTML = '<span class="text-amber-600 text-xs font-semibold">Foto ignorada (já existe).</span>';
                } else if (data.status === 'error') {
                    st.className = "text-xs font-bold px-2 py-1 rounded bg-red-100 text-red-700";
                    st.innerHTML = '<i class="fa-solid fa-triangle-exclamation mr-1"></i> Falha';
                    ll.innerHTML = `<span class="text-red-600 text-xs font-semibold">${data.message}</span>`;
                } else if (data.status === 'success') {
                    st.className = "text-xs font-bold px-2 py-1 rounded bg-emerald-100 text-emerald-700";
                    st.innerHTML = '<i class="fa-solid fa-check mr-1"></i> Sucesso';
                    
                    if(data.keywords) {
                        const tags = data.keywords.split(',').map(t => t.trim());
                        ll.innerHTML = tags.map(t => `<span class="bg-slate-200 text-slate-700 px-2 py-1 rounded text-[10px] font-bold shadow-sm">${t}</span>`).join('');
                    }

                    if(data.produto && !allProducts.some(p => p.id === data.produto.id)) {
                        allProducts.unshift(data.produto); 
                        
                        if (currentTab === 'pendentes') {
                            const grid = document.getElementById('catalogoGrid');
                            
                            if(grid.innerHTML.includes("Tudo zerado!")) {
                                grid.innerHTML = `<div class="col-span-full flex justify-end mb-2">
                                    <button onclick="salvarTodosProntos()" id="btn-save-all" class="bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold py-2 px-4 rounded-xl transition shadow flex items-center">
                                        <i class="fa-solid fa-layer-group mr-2"></i> Salvar Lote Preenchido
                                    </button>
                                </div>`;
                            }
                            
                            grid.insertAdjacentHTML('beforeend', renderFullCard(data.produto));
                            rebuildTagsUI(data.produto.id, data.produto.palavras_chave);
                            
                            document.getElementById('count-pendentes').innerText = allProducts.filter(p => !p.grade).length;
                        }
                    }
                } else if (data.status === 'done') {
                    ev.close();
                    st.className = "text-xs font-bold px-2 py-1 rounded bg-indigo-100 text-indigo-700";
                    st.innerHTML = '<i class="fa-solid fa-flag-checkered mr-1"></i> Concluído';
                    
                    btnProcessar.disabled = false;
                    btnProcessar.textContent = "Finalizado (Processar Mais)";
                    fileInput.value = ''; 
                }
            };
        }

        window.switchTab = (tab) => {
            currentTab = tab;
            editingId = null; 
            
            document.getElementById('tab-btn-pendentes').className = tab === 'pendentes' 
                ? 'flex-1 py-3 text-sm font-bold text-indigo-600 border-b-2 border-indigo-600 transition flex justify-center items-center gap-2'
                : 'flex-1 py-3 text-sm font-semibold text-slate-400 hover:text-slate-600 border-b-2 border-transparent transition flex justify-center items-center gap-2';
            
            document.getElementById('tab-btn-salvos').className = tab === 'salvos' 
                ? 'flex-1 py-3 text-sm font-bold text-indigo-600 border-b-2 border-indigo-600 transition flex justify-center items-center gap-2'
                : 'flex-1 py-3 text-sm font-semibold text-slate-400 hover:text-slate-600 border-b-2 border-transparent transition flex justify-center items-center gap-2';
            
            renderApp();
        };

        async function carregarCatalogo() {
            try {
                const response = await fetch('/api/produtos');
                allProducts = await response.json();
                renderApp();
            } catch (err) { alert("Falha ao carregar banco."); }
        }

        function renderApp() {
            const pendentes = allProducts.filter(p => !p.grade || p.grade.trim() === '');
            const salvos = allProducts.filter(p => p.grade && p.grade.trim() !== '');

            document.getElementById('count-pendentes').innerText = pendentes.length;
            document.getElementById('count-salvos').innerText = salvos.length;

            const grid = document.getElementById('catalogoGrid');

            if (currentTab === 'pendentes') {
                if (pendentes.length === 0) {
                    grid.innerHTML = '<div class="col-span-full py-20 text-center text-slate-400 font-medium">Tudo zerado! Nenhuma foto pendente na fila.</div>';
                } else {
                    let html = `<div class="col-span-full flex justify-end mb-2">
                                    <button onclick="salvarTodosProntos()" id="btn-save-all" class="bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold py-2 px-4 rounded-xl transition shadow flex items-center">
                                        <i class="fa-solid fa-layer-group mr-2"></i> Salvar Lote Preenchido
                                    </button>
                                </div>`;
                    html += pendentes.map(p => renderFullCard(p)).join('');
                    grid.innerHTML = html;
                    pendentes.forEach(p => rebuildTagsUI(p.id, p.palavras_chave)); 
                }
            } else {
                if (salvos.length === 0) {
                    grid.innerHTML = '<div class="col-span-full py-20 text-center text-slate-400 font-medium">O estoque ativo está vazio.</div>';
                } else {
                    grid.innerHTML = salvos.map(p => editingId === p.id ? renderFullCard(p) : renderCompactCard(p)).join('');
                    if(editingId !== null) {
                        const p = salvos.find(x => x.id === editingId);
                        rebuildTagsUI(p.id, p.palavras_chave);
                    }
                }
            }
        }

        function renderCompactCard(p) {
            return `
            <div id="card-${p.id}" class="bg-white rounded-xl p-3 border border-slate-200 flex items-center justify-between shadow-sm hover:shadow transition">
                <div class="flex items-center gap-3 w-[65%]">
                    <img src="/${p.caminho_imagem}" class="w-12 h-12 object-cover rounded-lg border border-slate-200">
                    <div class="flex-1 min-w-0">
                        <h3 class="font-bold text-slate-800 text-sm truncate">${p.nome}</h3>
                        <div class="flex gap-2 items-center mt-0.5">
                            <span class="text-[10px] font-mono text-emerald-600 font-bold bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-100">R$ ${parseFloat(p.preco).toFixed(2)}</span>
                            <span class="text-[10px] font-mono text-indigo-500 font-bold truncate">${p.grade}</span>
                        </div>
                    </div>
                </div>
                <div class="flex gap-2">
                    <button onclick="ativarEdicao(${p.id})" class="text-slate-500 hover:text-indigo-600 bg-slate-100 hover:bg-indigo-50 px-3 py-1.5 rounded-lg text-xs font-bold transition">
                        <i class="fa-solid fa-pen"></i> Editar
                    </button>
                    <button onclick="deletarProduto(${p.id})" title="Apagar Calçado" class="text-red-400 hover:text-red-600 bg-red-50 hover:bg-red-100 px-3 py-1.5 rounded-lg text-xs transition">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </div>`;
        }

        window.ativarEdicao = (id) => { editingId = id; renderApp(); };
        window.cancelarEdicao = () => { editingId = null; renderApp(); };

        function renderFullCard(p) {
            const btnCancel = currentTab === 'salvos' ? `<button onclick="cancelarEdicao()" class="w-1/4 bg-slate-200 hover:bg-slate-300 text-slate-700 text-xs font-bold py-2 rounded-lg transition">Cancelar</button>` : '';
            
            return `
            <div id="card-${p.id}" class="bg-white rounded-xl p-4 border border-slate-200 shadow-lg relative flex flex-col transition-all duration-300">
                <div class="flex gap-3 mb-4">
                    <img src="/${p.caminho_imagem}" class="w-24 h-24 object-cover rounded-lg border border-slate-200 shadow-sm">
                    <div class="flex-1 min-w-0 flex flex-col justify-between">
                        <div>
                            <h3 class="font-bold text-slate-800 text-sm leading-tight mb-1" title="${p.nome}">${p.nome}</h3>
                            <p class="text-xs text-indigo-600 font-semibold">${p.estilo}</p>
                        </div>
                        <div class="mt-2">
                            <label class="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1 block">Preço de Venda (R$)</label>
                            <input type="number" step="0.01" id="preco-input-${p.id}" value="${parseFloat(p.preco).toFixed(2)}" class="w-24 text-xs p-1.5 rounded border border-slate-300 focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-slate-50 font-mono text-slate-700">
                        </div>
                    </div>
                </div>
                
                <label class="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Palavras-chave Semânticas</label>
                <div class="border border-slate-200 rounded-lg p-2 bg-slate-50 flex flex-wrap gap-1.5 items-center min-h-[40px] mb-4" id="tags-visual-${p.id}"></div>
                <input type="hidden" id="tags-hidden-${p.id}" value="${p.palavras_chave}">
                
                <div class="flex justify-between items-center mb-1">
                    <label class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Mapeamento de Grade</label>
                    <div class="flex gap-1">
                        <button onclick="aplicarGradePadrao(${p.id}, 'masc')" class="text-[9px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-bold hover:bg-blue-200 transition">Masc 1</button>
                        <button onclick="aplicarGradePadrao(${p.id}, 'fem')" class="text-[9px] bg-pink-100 text-pink-700 px-1.5 py-0.5 rounded font-bold hover:bg-pink-200 transition">Fem 1</button>
                    </div>
                </div>
                ${gerarGridTamanhos(p.id, p.grade)}
                
                <div class="flex gap-2 mt-auto">
                    <button onclick="deletarProduto(${p.id})" title="Excluir Definitivamente" class="px-3.5 bg-red-50 hover:bg-red-100 text-red-500 text-xs py-2 rounded-lg transition border border-red-200">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                    ${btnCancel}
                    <button onclick="salvarCuradoria(${p.id})" id="btn-save-${p.id}" class="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold py-2 rounded-lg transition shadow">
                        <i class="fa-solid fa-check mr-1"></i> Salvar Calçado
                    </button>
                </div>
            </div>`;
        }

        window.rebuildTagsUI = (id, initialTags = null) => {
            const hidden = document.getElementById(`tags-hidden-${id}`);
            if(initialTags !== null && !hidden.value) hidden.value = initialTags;
            
            const tags = hidden.value.split(',').map(t=>t.trim()).filter(t=>t);
            const container = document.getElementById(`tags-visual-${id}`);
            
            let html = tags.map(t => `<span class="bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded text-[10px] flex items-center font-semibold group cursor-default shadow-sm border border-indigo-200">
                ${t} <i class="fa-solid fa-times ml-1.5 opacity-50 group-hover:opacity-100 group-hover:text-red-500 cursor-pointer" onclick="removeTag(${id}, '${t}')"></i>
            </span>`).join('');
            
            html += `<input type="text" placeholder="Adicionar + Enter..." class="text-[10px] border-none bg-transparent outline-none ring-0 flex-1 min-w-[100px] text-slate-600 p-0" onkeydown="handleTagInput(event, ${id})">`;
            container.innerHTML = html;
        };

        window.handleTagInput = (e, id) => {
            if(e.key === 'Enter' || e.key === ',') {
                e.preventDefault();
                const v = e.target.value.trim().replace(/,/g, '');
                if(v) {
                    const hidden = document.getElementById(`tags-hidden-${id}`);
                    let tags = hidden.value.split(',').map(t=>t.trim()).filter(t=>t);
                    if(!tags.includes(v)) tags.push(v);
                    hidden.value = tags.join(', ');
                    rebuildTagsUI(id);
                }
            }
        };

        window.removeTag = (id, tag) => {
            const hidden = document.getElementById(`tags-hidden-${id}`);
            let tags = hidden.value.split(',').map(t=>t.trim()).filter(t=>t);
            tags = tags.filter(t => t !== tag);
            hidden.value = tags.join(', ');
            rebuildTagsUI(id);
        };

        function gerarGridTamanhos(id, gradeStr) {
            let gradesMap = {};
            if(gradeStr) {
                gradeStr.split(',').forEach(p => {
                    let [s, q] = p.split(':');
                    if(s && q) gradesMap[s.trim()] = parseInt(q.trim());
                });
            }
            let html = '<div class="grid grid-cols-6 gap-1.5 mb-4">';
            standardSizes.forEach(sz => {
                const qty = gradesMap[sz] || 0;
                const bgClass = qty > 0 ? 'bg-indigo-50 border-indigo-300' : 'bg-slate-50 border-slate-200';
                html += `
                <div id="grade-box-${id}-${sz}" class="flex flex-col items-center border ${bgClass} rounded overflow-hidden transition-colors">
                    <span class="w-full text-center text-[9px] font-bold bg-slate-200 text-slate-600 py-0.5 border-b border-slate-200">${sz}</span>
                    <input type="number" id="grade-input-${id}-${sz}" value="${qty}" min="0" onchange="atualizarCorCaixaGrade(${id}, ${sz})" class="w-full text-center text-xs p-1 outline-none font-mono text-slate-700 bg-transparent">
                </div>`;
            });
            return html + '</div>';
        }

        window.atualizarCorCaixaGrade = (id, sz) => {
            const val = parseInt(document.getElementById(`grade-input-${id}-${sz}`).value) || 0;
            const box = document.getElementById(`grade-box-${id}-${sz}`);
            if(val > 0) { box.classList.replace('bg-slate-50', 'bg-indigo-50'); box.classList.replace('border-slate-200', 'border-indigo-300'); }
            else { box.classList.replace('bg-indigo-50', 'bg-slate-50'); box.classList.replace('border-indigo-300', 'border-slate-200'); }
        };

        window.aplicarGradePadrao = (id, tipo) => {
            standardSizes.forEach(s => { document.getElementById(`grade-input-${id}-${s}`).value = 0; atualizarCorCaixaGrade(id, s); });
            const config = tipo === 'masc' ? {38:1, 39:2, 40:3, 41:3, 42:2, 43:1} : {34:1, 35:2, 36:3, 37:3, 38:2, 39:1};
            for (const [size, qty] of Object.entries(config)) {
                document.getElementById(`grade-input-${id}-${size}`).value = qty;
                atualizarCorCaixaGrade(id, size);
            }
        };

        window.deletarProduto = async (id) => {
            if(!confirm("Certeza que deseja excluir este calçado? A imagem será apagada do servidor.")) return;
            
            try {
                const response = await fetch(`/api/produtos/${id}`, { method: 'DELETE' });
                if(response.ok) {
                    allProducts = allProducts.filter(p => p.id !== id);
                    
                    const card = document.getElementById(`card-${id}`);
                    if(card) {
                        card.style.opacity = '0';
                        setTimeout(() => {
                            card.remove();
                            document.getElementById('count-pendentes').innerText = allProducts.filter(p => !p.grade).length;
                            document.getElementById('count-salvos').innerText = allProducts.filter(p => p.grade).length;
                            
                            if (allProducts.filter(p => !p.grade).length === 0 && currentTab === 'pendentes') renderApp();
                            if (allProducts.filter(p => p.grade).length === 0 && currentTab === 'salvos') renderApp();
                        }, 300);
                    }
                }
            } catch (err) { alert("Erro ao excluir."); }
        };

        window.salvarCuradoria = async (id, emLote = false) => {
            const btn = document.getElementById(`btn-save-${id}`);
            if(!emLote) {
                btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
                btn.disabled = true;
            }

            const tagsStr = document.getElementById(`tags-hidden-${id}`).value;
            const precoVal = parseFloat(document.getElementById(`preco-input-${id}`).value) || 0.0;
            
            let arrGrades = [];
            standardSizes.forEach(s => {
                const val = parseInt(document.getElementById(`grade-input-${id}-${s}`).value) || 0;
                if(val > 0) arrGrades.push(`${s}:${val}`);
            });
            const gradeStr = arrGrades.join(', ');

            if (gradeStr === '') {
                if(!emLote) {
                    alert("⚠️ ALERTA: Você precisa adicionar pelo menos 1 item na grade de tamanhos antes de salvar!");
                    btn.innerHTML = '<i class="fa-solid fa-check mr-1"></i> Salvar Calçado';
                    btn.disabled = false;
                }
                return false;
            }

            try {
                const response = await fetch(`/api/produtos/${id}`, {
                    method: 'PUT', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ palavras_chave: tagsStr, grade: gradeStr, preco: precoVal })
                });
                
                if(response.ok) {
                    const idx = allProducts.findIndex(p => p.id === id);
                    allProducts[idx].palavras_chave = tagsStr;
                    allProducts[idx].grade = gradeStr;
                    allProducts[idx].preco = precoVal;
                    
                    if (currentTab === 'pendentes') {
                        const card = document.getElementById(`card-${id}`);
                        card.style.opacity = '0';
                        setTimeout(() => card.remove(), 300);
                        
                        document.getElementById('count-pendentes').innerText = allProducts.filter(p => !p.grade).length;
                        document.getElementById('count-salvos').innerText = allProducts.filter(p => p.grade).length;
                    } else {
                        editingId = null;
                        renderApp(); 
                    }
                    return true;
                }
            } catch (err) { 
                if(!emLote) alert("Erro de conexão ao salvar."); 
                if(!emLote) { btn.innerHTML = "Erro"; btn.disabled = false; }
                return false;
            }
        };

        window.salvarTodosProntos = async () => {
            const btnAll = document.getElementById('btn-save-all');
            btnAll.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i> Processando Lote...';
            btnAll.disabled = true;

            const pendentes = allProducts.filter(p => !p.grade || p.grade.trim() === '');
            let countSucesso = 0;
            
            for(let p of pendentes) {
                let temGrade = false;
                standardSizes.forEach(s => {
                    const input = document.getElementById(`grade-input-${p.id}-${s}`);
                    if (input && parseInt(input.value) > 0) temGrade = true;
                });
                
                if(temGrade) {
                    const sucesso = await salvarCuradoria(p.id, true);
                    if(sucesso) countSucesso++;
                }
            }

            if(countSucesso > 0) {
                if (document.querySelectorAll('[id^="card-"]').length === 0) {
                    renderApp();
                } else {
                    btnAll.innerHTML = '<i class="fa-solid fa-layer-group mr-2"></i> Salvar Lote Preenchido';
                    btnAll.disabled = false;
                }
            } else {
                alert("Nenhum calçado na tela possui grade preenchida para ser salvo!");
                btnAll.innerHTML = '<i class="fa-solid fa-layer-group mr-2"></i> Salvar Lote Preenchido';
                btnAll.disabled = false;
            }
        };
    </script>
</body>
</html>
"""

@app.route('/')
def index(): return render_template_string(HTML_PAGE)

@app.route(f'/{DIRETORIO_ALVO}/<path:filename>')
def serve_image(filename): return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/upload', methods=['POST'])
def upload_files():
    if 'fotos' not in request.files: return jsonify({"sucesso": False})
    nomes = []
    for f in request.files.getlist('fotos'):
        if f.filename != '':
            n = secure_filename(f.filename)
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], n))
            nomes.append(n)
    return jsonify({"sucesso": True, "arquivos": nomes})

@app.route('/process_stream')
def process_stream():
    arquivos = request.args.get('files', '').split(',')
    def generate():
        conn = inicializar_banco()
        cursor = conn.cursor()
        for arq in arquivos:
            if not arq: continue
            cam = os.path.join(app.config['UPLOAD_FOLDER'], arq)
            
            cursor.execute('SELECT 1 FROM produtos WHERE caminho_imagem = ?', (cam,))
            if cursor.fetchone():
                yield f"data: {json.dumps({'status': 'duplicate', 'filename': arq, 'image_url': f'/{cam}'})}\n\n"
                continue
            
            yield f"data: {json.dumps({'status': 'processing', 'filename': arq, 'image_url': f'/{cam}'})}\n\n"
            
            match = re.search(r'(\d+[.,]\d{1,2})', arq)
            preco = float(match.group(1).replace(',','.')) if match else 0.0
            
            dados = analisar_calcado(cam, preco)
            
            if dados:
                try:
                    cursor.execute('''INSERT INTO produtos (nome, marca, preco, cor_principal, estilo, palavras_chave, caminho_imagem)
                                      VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                                   (dados['nome'], dados['marca'], dados['preco'], dados['cor_principal'], dados['estilo'], dados['palavras_chave'], dados['caminho_imagem']))
                    conn.commit()
                    
                    cursor.execute('SELECT id FROM produtos WHERE caminho_imagem = ?', (cam,))
                    novo_id = cursor.fetchone()[0]
                    novo_produto = {
                        "id": novo_id, "nome": dados['nome'], "estilo": dados['estilo'],
                        "palavras_chave": dados['palavras_chave'], "caminho_imagem": cam, "grade": "",
                        "preco": dados['preco']
                    }
                    
                    yield f"data: {json.dumps({'status': 'success', 'keywords': dados['palavras_chave'], 'produto': novo_produto})}\n\n"
                except sqlite3.IntegrityError:
                    yield f"data: {json.dumps({'status': 'duplicate'})}\n\n"
            else:
                yield f"data: {json.dumps({'status': 'error', 'filename': arq, 'message': 'Verifique o erro no terminal do Python.'})}\n\n"
            
            time.sleep(5)
            
        conn.close()
        yield f"data: {json.dumps({'status': 'done'})}\n\n"
    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/produtos', methods=['GET'])
def get_produtos():
    conn = inicializar_banco()
    cursor = conn.cursor()
    cursor.execute('SELECT id, nome, estilo, palavras_chave, caminho_imagem, grade, preco FROM produtos ORDER BY id DESC')
    res = [{"id": l[0], "nome": l[1], "estilo": l[2], "palavras_chave": l[3], "caminho_imagem": l[4], "grade": l[5] if l[5] else "", "preco": l[6]} for l in cursor.fetchall()]
    conn.close()
    return jsonify(res)

@app.route('/api/produtos/<int:produto_id>', methods=['PUT'])
def update_produto(produto_id):
    dados = request.json
    conn = inicializar_banco()
    conn.cursor().execute('UPDATE produtos SET palavras_chave = ?, grade = ?, preco = ? WHERE id = ?', 
                          (dados.get('palavras_chave'), dados.get('grade',''), float(dados.get('preco', 0.0)), produto_id))
    conn.commit()
    conn.close()
    return jsonify({"sucesso": True})

@app.route('/api/produtos/<int:produto_id>', methods=['DELETE'])
def delete_produto(produto_id):
    conn = inicializar_banco()
    cursor = conn.cursor()
    cursor.execute('SELECT caminho_imagem FROM produtos WHERE id = ?', (produto_id,))
    row = cursor.fetchone()
    if row:
        try:
            if os.path.exists(row[0]): os.remove(row[0])
        except Exception as e:
            print(f"Aviso: Não foi possível deletar a imagem física: {e}")
            
    cursor.execute('DELETE FROM produtos WHERE id = ?', (produto_id,))
    conn.commit()
    conn.close()
    return jsonify({"sucesso": True})

if __name__ == '__main__':
    print("🌐 Servidor Operacional. Acesse: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)