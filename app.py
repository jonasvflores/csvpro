import os
import csv
import re
from datetime import datetime
from dateutil.parser import parse
from flask import Flask, render_template, request, send_file, Response, jsonify
import requests

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def padronizar_nome_coluna(nome):
    return re.sub(r'\W+', '_', nome.lower()).strip('_')

def capitalizar_texto(texto):
    if re.match(r'^[a-zA-Z\s]+$', texto):
        return texto.title()
    return texto

def formatar_telefone(texto):
    numero = re.sub(r'\D', '', texto)
    if not numero or len(numero) < 10:
        return numero, False
    if len(numero) in [10, 11] and numero[2] in '6789':
        if len(numero) == 11:
            numero = numero[:2] + numero[3:]
    elif len(numero) == 10 and numero[2] not in '6789':
        pass
    else:
        return numero, False
    return f"+55{numero}", True

def formatar_data(texto, formato_saida):
    try:
        data = parse(texto)
        if formato_saida == "mm-dd-aaaa":
            return data.strftime('%m-%d-%Y')
        elif formato_saida == "dd-mm-aaaa":
            return data.strftime('%d-%m-%Y')
        else:
            return data.strftime('%Y-%m-%d')
    except ValueError:
        return texto

@app.route('/get_columns', methods=['POST'])
def get_columns():
    file = request.files.get('csv_file')
    if not file or not file.filename.endswith('.csv'):
        return jsonify({'error': 'Por favor, envie um arquivo CSV válido.'}), 400

    try:
        # Lê o arquivo CSV e extrai o cabeçalho
        file.seek(0)
        reader = csv.reader(file.read().decode('utf-8').splitlines(), delimiter=';')
        linhas = list(reader)
        if not linhas:
            return jsonify({'error': 'Arquivo CSV vazio.'}), 400
        cabecalho = linhas[0]
        return jsonify({'columns': cabecalho})
    except Exception as e:
        return jsonify({'error': f'Erro ao processar o arquivo: {str(e)}'}), 500

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file or not file.filename.endswith('.csv'):
            return render_template('index.html', error="Por favor, envie um arquivo CSV válido.")
        
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)

        capitalize = request.form.get('capitalize') == 'on'
        colunas_capitalize = request.form.getlist('colunas_capitalize')
        formatar_data = request.form.get('formatar_data') == 'on'
        formato_data = request.form.get('formato_data', 'dd-mm-aaaa')
        dividir_telefones = request.form.get('dividir_telefones') == 'on'

        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            linhas = list(reader)

        cabecalho = [padronizar_nome_coluna(col) for col in linhas[0]]
        dados = []
        idx_telefone = next((i for i, col in enumerate(cabecalho) if 'telefone' in col or 'celular' in col or 'contato' in col), -1)

        for linha in linhas[1:]:
            if dividir_telefones and idx_telefone != -1 and ' - ' in linha[idx_telefone]:
                telefones = linha[idx_telefone].split(' - ')
                for tel in telefones:
                    nova_linha = linha.copy()
                    nova_linha[idx_telefone] = tel.strip()
                    processar_linha(nova_linha, cabecalho, capitalize, colunas_capitalize, formatar_data, formato_data, dados)
            else:
                processar_linha(linha, cabecalho, capitalize, colunas_capitalize, formatar_data, formato_data, dados)

        cabecalho.extend(['phone_number', 'identifier'])
        for i, linha in enumerate(dados):
            tel = linha[idx_telefone]
            phone_number, _ = formatar_telefone(tel)
            identifier = phone_number.replace('+', '') + '@s.whatsapp.net'
            linha.extend([phone_number, identifier])

        output_file = os.path.join(UPLOAD_FOLDER, f"processed_{file.filename}")
        with open(output_file, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f, delimiter=';', quotechar='"', quoting=csv.QUOTE_ALL)
            writer.writerow(cabecalho)
            writer.writerows(dados)

        if request.form.get('send_to_chatwoot') == 'on':
            api_key = request.form.get('api_key')
            account_id = request.form.get('account_id')
            chatwoot_url = request.form.get('chatwoot_url', 'https://app.chatwoot.com')
            send_to_chatwoot(dados, cabecalho, api_key, account_id, chatwoot_url)

        return render_template('result.html', filename=output_file, cabecalho=cabecalho, dados=dados[:5], cabecalho_antes=linhas[0], dados_antes=linhas[1:6])
    
    return render_template('index.html')

def processar_linha(linha, cabecalho, capitalize, colunas_capitalize, formatar_data, formato_data, dados):
    linha_processada = [
        capitalizar_texto(cel) if capitalize and col in colunas_capitalize
        else (formatar_data(cel, formato_data) if formatar_data and 'data' in col else cel)
        for col, cel in zip(cabecalho, linha)
    ]
    dados.append(linha_processada)

def send_to_chatwoot(dados, cabecalho, api_key, account_id, chatwoot_url):
    headers = {'api_access_token': api_key, 'Content-Type': 'application/json'}
    url = f"{chatwoot_url}/api/v1/accounts/{account_id}/contacts"
    for linha in dados:
        contato = {cabecalho[i]: valor for i, valor in enumerate(linha)}
        response = requests.post(url, json=contato, headers=headers)
        if response.status_code != 200:
            print(f"Erro ao enviar contato: {response.text}")

@app.route('/download/<filename>')
def download(filename):
    return send_file(filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
