import streamlit as st
import pandas as pd
import numpy as np
import gspread
from google.oauth2.service_account import Credentials
from io import BytesIO

# ================== CONFIGURAÇÃO ==================
st.set_page_config(page_title="Pesquisa Mart Minas", layout="wide", page_icon="icon.png")

# CSS para layout e centralização
st.markdown("""
    <style>
    [data-testid="stSidebarCollapsedControl"] > span,
    [data-testid="stSidebarCollapsedControl"] span:not(.material-symbols-outlined) {
        display: none !important;
    }
    [data-testid="stSidebarCollapsedControl"]::before {
        content: "keyboard_double_arrow_right" !important;
        font-family: "Material Symbols Outlined", "Material Icons", sans-serif !important;
        font-size: 28px !important;
        line-height: 1 !important;
        vertical-align: middle !important;
    }
    .block-container {
        max-width: 98% !important;
        padding-top: 1.5rem !important;
        margin: auto !important;
    }
    .titulo-centralizado {
        text-align: center;
        font-size: clamp(24px, 5vw, 40px);
        font-weight: 700;
        margin-top: 10px;
        margin-bottom: 15px;
        width: 100%;
        display: block;
    }
    [data-testid="stDataTableBodyCell"] > div, [data-testid="stTable"] td, [data-testid="stTable"] th {
        text-align: center !important;
        justify-content: center !important;
    }
            
    [data-testid="stSidebar"] {
        width: 300px !important; /* Ajuste este valor (ex: 400px, 500px) como preferir */
    }
    </style>
""", unsafe_allow_html=True)

# Estados de sessão
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "perfil" not in st.session_state:
    st.session_state.perfil = None
if "loja_sel" not in st.session_state:
    st.session_state.loja_sel = None
if "concorrente_sel" not in st.session_state:
    st.session_state.concorrente_sel = None
if "prod_idx" not in st.session_state:
    st.session_state.prod_idx = 0

# ================== CONFIGURAÇÕES COMERCIAL ==================
DEFAULT_CONFIG = {
    "range_min": 0.5,
    "range_max": 1.5,
    "considerar_obs": False,
    "considerar_menor_preco": True,
}

for key, value in DEFAULT_CONFIG.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ================== FUNÇÕES CORE ==================
@st.cache_resource
def authenticate_gspread():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_info = dict(st.secrets["gcp_service_account"])
    return Credentials.from_service_account_info(creds_info, scopes=scopes)

def listar_planilhas_no_drive(_client):
    lista_arquivos = _client.list_spreadsheet_files()
    return {f["name"]: f["id"] for f in lista_arquivos}

@st.cache_data(ttl=30)
def fetch_data(spreadsheet_id):
    client = gspread.authorize(authenticate_gspread())
    sheet = client.open_by_key(spreadsheet_id).get_worksheet(0)
    data = sheet.get_values("A:G")
    df = pd.DataFrame(data[1:], columns=data[0])
    return df.iloc[:, :7]

def salvar_dados(spreadsheet_id, indice_original, preco, observacao):
    try:
        client = gspread.authorize(authenticate_gspread())
        sheet = client.open_by_key(spreadsheet_id).get_worksheet(0)
        preco_limpo = str(preco).replace(",", ".").strip()
        linha_sheets = int(indice_original + 2)
        sheet.update(f"D{linha_sheets}:E{linha_sheets}", [[preco_limpo, observacao]])
        st.toast("Dados salvos!", icon="✅")
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

def preparar_dados_validos(df):
    df_calc = df.copy()
    c_preco, c_ref = df.columns[3], df.columns[6]
    df_calc[c_preco] = pd.to_numeric(df_calc[c_preco].astype(str).str.replace(',', '.'), errors='coerce')
    df_calc[c_ref] = pd.to_numeric(df_calc[c_ref].astype(str).str.replace(',', '.'), errors='coerce')
    return df_calc[(df_calc[c_preco] > 0) & (df_calc[c_ref] > 0)].copy()

# ================== FILTROS DINÂMICOS COMERCIAL ==================
def aplicar_filtros_configuracoes(df):
    df_calc = df.copy()
    # Identifica as colunas D (Concorrente) e G (Mart Minas)
    c_preco_conc = df.columns[3] 
    c_preco_mart = df.columns[6]
    c_obs = df.columns[4]
    c_produto = df.columns[2]
    
    # Conversão numérica rigorosa
    df_calc[c_preco_conc] = pd.to_numeric(df_calc[c_preco_conc].astype(str).str.replace(',', '.'), errors='coerce')
    df_calc[c_preco_mart] = pd.to_numeric(df_calc[c_preco_mart].astype(str).str.replace(',', '.'), errors='coerce')

    # Remove valores inválidos para evitar divisão por zero
    df_calc = df_calc[(df_calc[c_preco_conc] > 0) & (df_calc[c_preco_mart] > 0)]

    # REGRA: Mart Minas (G) / Concorrente (D)
    ratio = df_calc[c_preco_mart] / df_calc[c_preco_conc]
    
    # USA AS VARIÁVEIS DO SESSION_STATE DIRETAMENTE
    mask_range = (ratio >= st.session_state.range_min) & (ratio <= st.session_state.range_max)
    df_filtrado = df_calc[mask_range].copy()

    if not st.session_state.considerar_obs:
        df_filtrado = df_filtrado[
            (df_filtrado[c_obs].astype(str).str.strip() == "") |
            (df_filtrado[c_produto].astype(str).str.endswith("(MENOR PREÇO)"))
        ]

    if not st.session_state.considerar_menor_preco:
        df_filtrado = df_filtrado[
            ~df_filtrado[c_produto].astype(str).str.endswith("(MENOR PREÇO)")
        ]

    return df_filtrado

# ================== FUNÇÃO EXPORTAR ==================

def to_excel_consolidated(dict_dfs):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for sheet_name, df_orig in dict_dfs.items():
            if df_orig.empty:
                continue

            # --- LIMPEZA DE ERROS (#NÚM!, NaN, Inf) ---
            # Converte infinitos em NaN e depois preenche todos os NaNs com string vazia
            df_limpo = df_orig.replace([np.inf, -np.inf], np.nan)
            
            sheet_name_safe = sheet_name[:31].replace('/', '_').replace('\\', '_').replace('*', '').strip()

            workbook = writer.book
            # Configura para que células de erro ou vazias não gerem #NÚM! no Excel
            workbook.nan_inf_to_errors = True  
            ws = workbook.add_worksheet(sheet_name_safe)

            # Formatações
            header_fmt = workbook.add_format({'bold': True, 'text_wrap': True, 'valign': 'vcenter', 'align': 'center', 'fg_color': '#2E7D32', 'font_color': 'white', 'border': 1})
            subheader_fmt = workbook.add_format({'bold': True, 'text_wrap': True, 'valign': 'vcenter', 'align': 'center', 'fg_color': '#4CAF50', 'font_color': 'white', 'border': 1})
            money_fmt = workbook.add_format({'num_format': 'R$ #,##0.00', 'align': 'center', 'border': 1})
            perc_fmt  = workbook.add_format({'num_format': '0.0%', 'align': 'center', 'border': 1})
            center_fmt = workbook.add_format({'align': 'center', 'border': 1})

            is_multi_header = isinstance(df_limpo.columns, pd.MultiIndex)
            is_product_sheet = "Produtos_" in sheet_name
            
            n_idx_cols = 2 if is_product_sheet else (1 if is_multi_header else 0)
            col_start = n_idx_cols
            n_levels = df_limpo.columns.nlevels if is_multi_header else 1

            if is_multi_header:
                # 1. Mesclagem de Cabeçalhos
                for level in range(n_levels - 1):
                    current_group, merge_start = None, None
                    fmt_atual = header_fmt if level == 0 else subheader_fmt
                    for col_idx in range(len(df_limpo.columns)):
                        real_col = col_idx + col_start
                        val = str(df_limpo.columns.get_level_values(level)[col_idx]).strip()
                        if val != current_group:
                            if current_group is not None and (real_col - 1) > merge_start:
                                ws.merge_range(level, merge_start, level, real_col - 1, current_group, fmt_atual)
                            elif current_group is not None:
                                ws.write(level, merge_start, current_group, fmt_atual)
                            current_group, merge_start = val, real_col
                    if current_group is not None:
                        if (len(df_limpo.columns) + col_start - 1) > merge_start:
                            ws.merge_range(level, merge_start, level, len(df_limpo.columns) + col_start - 1, current_group, fmt_atual)
                        else:
                            ws.write(level, merge_start, current_group, fmt_atual)

                for col_idx in range(len(df_limpo.columns)):
                    val = df_limpo.columns.get_level_values(n_levels-1)[col_idx]
                    ws.write(n_levels-1, col_idx + col_start, str(val), subheader_fmt)
                
                if is_product_sheet:
                    ws.merge_range(0, 0, n_levels-1, 0, "Comprador", header_fmt)
                    ws.merge_range(0, 1, n_levels-1, 1, "Produto", header_fmt)
                elif is_multi_header:
                    title = "Comprador" if "Matriz_" in sheet_name else "Item"
                    ws.merge_range(0, 0, n_levels-1, 0, title, header_fmt)

                start_data_row = n_levels
            else:
                for col_idx, col_name in enumerate(df_limpo.columns):
                    ws.write(0, col_idx, str(col_name), header_fmt)
                start_data_row = 1

            # 4. Escrita dos Dados com tratamento de nulos
            for r in range(len(df_limpo)):
                # Escrever Índices
                if is_product_sheet:
                    ws.write(r + start_data_row, 0, df_limpo.index[r][0], center_fmt)
                    ws.write(r + start_data_row, 1, df_limpo.index[r][1], center_fmt)
                elif is_multi_header:
                    val = df_limpo.index[r][0] if isinstance(df_limpo.index[r], tuple) else df_limpo.index[r]
                    ws.write(r + start_data_row, 0, val, center_fmt)

                # Escrever Valores
                for c in range(len(df_limpo.columns)):
                    value = df_limpo.iloc[r, c]
                    
                    # Se o valor for nulo ou erro, escreve vazio e pula formatação
                    if pd.isna(value):
                        ws.write(r + start_data_row, c + col_start, "", center_fmt)
                        continue

                    col_name = str(df_limpo.columns.get_level_values(n_levels-1)[c]).upper() if is_multi_header else str(df_limpo.columns[c]).upper()
                    
                    fmt = center_fmt
                    if any(x in col_name for x in ['%', 'COMP']):
                        fmt = perc_fmt
                        if isinstance(value, (int, float)) and value > 2: value /= 100
                    elif any(k in col_name for k in ['SOMA', 'MÉDIA', 'MART MINAS', 'CONCORRENTE']):
                        fmt = money_fmt
                    
                    ws.write(r + start_data_row, c + col_start, value, fmt)

            ws.set_column(0, 1, 30)
            for c in range(col_start, len(df_limpo.columns) + col_start):
                ws.set_column(c, c, 18)
            ws.freeze_panes(start_data_row, col_start)

    output.seek(0)
    return output.getvalue()

# ================== LÓGICA DE FORMATAÇÃO MOEDA ==================
def formatar_moeda(valor):
    if pd.isna(valor) or not isinstance(valor, (int, float)):
        return valor
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ================== LÓGICA DE VISÕES ==================

def calcular_metricas_simples(df, agrupador):
    df_v = df.copy()

    c_p, c_r = df.columns[3], df.columns[6]

    df_v[c_p] = pd.to_numeric(df_v[c_p], errors="coerce")
    df_v[c_r] = pd.to_numeric(df_v[c_r], errors="coerce")

    if df_v.empty: return pd.DataFrame()
    c_p, c_r = df.columns[3], df.columns[6]
    res = df_v.groupby(agrupador).apply(lambda x: pd.Series({
        'Encontrados': int(len(x)),
        'Menor': int((x[c_p] < x[c_r]).sum()),
        'Maior': int((x[c_p] > x[c_r]).sum())
    })).reset_index()
    t_enc, t_men, t_mai = res['Encontrados'].sum(), res['Menor'].sum(), res['Maior'].sum()
    res = pd.concat([res, pd.DataFrame({agrupador:['TOTAL'], 'Encontrados':[t_enc], 'Menor':[t_men], 'Maior':[t_mai]})], ignore_index=True)
    res['% Menor'] = res.apply(lambda r: f"{(r['Menor']/r['Encontrados']*100):.1f}%" if r['Encontrados'] > 0 else "0.0%", axis=1)
    res['% Maior'] = res.apply(lambda r: f"{(r['Maior']/r['Encontrados']*100):.1f}%" if r['Encontrados'] > 0 else "0.0%", axis=1)
    return res[[agrupador, 'Encontrados', 'Menor', '% Menor', 'Maior', '% Maior']]

def calcular_soma_competitividade_simples(df, agrupador, format_money=False):
    df_v = df.copy()

    c_p, c_r = df.columns[3], df.columns[6]

    df_v[c_p] = pd.to_numeric(df_v[c_p], errors="coerce")
    df_v[c_r] = pd.to_numeric(df_v[c_r], errors="coerce")

    if df_v.empty: return pd.DataFrame()
    c_p, c_r = df.columns[3], df.columns[6]
    res = df_v.groupby(agrupador).apply(lambda x: pd.Series({
        'Soma Mart Minas': x[c_r].sum(),
        'Soma Concorrente': x[c_p].sum()
    })).reset_index()
    t_mart, t_conc = res['Soma Mart Minas'].sum(), res['Soma Concorrente'].sum()
    res = pd.concat([res, pd.DataFrame({agrupador:['TOTAL'], 'Soma Mart Minas':[t_mart], 'Soma Concorrente':[t_conc]})], ignore_index=True)
    res['Comp. %'] = res.apply(lambda r: (r['Soma Mart Minas']/r['Soma Concorrente']*100) if r['Soma Concorrente'] > 0 else 0, axis=1)
    
    if format_money:
        res['Soma Mart Minas'] = res['Soma Mart Minas'].apply(formatar_moeda)
        res['Soma Concorrente'] = res['Soma Concorrente'].apply(formatar_moeda)
        res['Comp. %'] = res['Comp. %'].apply(lambda x: f"{x:.1f}%")
    return res

def visao_matriz_loja_concorrente(df, tipo="contagem"):
    df_v = df.copy()

    cols = df.columns
    c_p, c_r = cols[3], cols[6]

    df_v[c_p] = pd.to_numeric(df_v[c_p], errors="coerce")
    df_v[c_r] = pd.to_numeric(df_v[c_r], errors="coerce")

    if df_v.empty: return pd.DataFrame()
    cols = df.columns
    compradores = sorted(df_v[cols[1]].unique())
    lojas_concorrentes = df_v[[cols[0], cols[5]]].drop_duplicates().sort_values([cols[0], cols[5]])
    
    headers = []
    for _, row in lojas_concorrentes.iterrows():
        lj, conc = row[cols[0]], row[cols[5]]
        if tipo == "contagem":
            headers.extend([(lj, conc, 'Encontrados'), (lj, conc, 'Menor'), (lj, conc, '% Menor'), (lj, conc, 'Maior'), (lj, conc, '% Maior')])
        else:
            headers.extend([(lj, conc, 'Soma Mart Minas'), (lj, conc, 'Soma Concorrente'), (lj, conc, 'Comp. %')])
    
    m_index = pd.MultiIndex.from_tuples(headers)
    df_final = pd.DataFrame(index=compradores, columns=m_index)
    
    for compr in compradores:
        for _, row in lojas_concorrentes.iterrows():
            lj, conc = row[cols[0]], row[cols[5]]
            filt = df_v[(df_v[cols[1]] == compr) & (df_v[cols[0]] == lj) & (df_v[cols[5]] == conc)]
            if not filt.empty:
                if tipo == "contagem":
                    e, m, ma = len(filt), (filt[cols[3]] < filt[cols[6]]).sum(), (filt[cols[3]] > filt[cols[6]]).sum()
                    df_final.loc[compr, (lj, conc, 'Encontrados')] = e
                    df_final.loc[compr, (lj, conc, 'Menor')] = m
                    df_final.loc[compr, (lj, conc, '% Menor')] = (m/e*100)
                    df_final.loc[compr, (lj, conc, 'Maior')] = ma
                    df_final.loc[compr, (lj, conc, '% Maior')] = (ma/e*100)
                else:
                    s_m, s_c = filt[cols[6]].sum(), filt[cols[3]].sum()
                    df_final.loc[compr, (lj, conc, 'Soma Mart Minas')] = s_m
                    df_final.loc[compr, (lj, conc, 'Soma Concorrente')] = s_c
                    df_final.loc[compr, (lj, conc, 'Comp. %')] = (s_m/s_c*100) if s_c > 0 else 0
            else:
                for met in df_final.columns.get_level_values(2).unique(): df_final.loc[compr, (lj, conc, met)] = 0

    totals = {}
    for col in df_final.columns:
        if 'Comp. %' in col[2] or '%' in col[2]:
            t_ref = 'Encontrados' if tipo == "contagem" else 'Soma Concorrente'
            t_val = "Menor" if "Menor" in col[2] else ("Maior" if "Maior" in col[2] else "Soma Mart Minas")
            s_r = df_final[(col[0], col[1], t_ref)].sum()
            s_v = df_final[(col[0], col[1], t_val)].sum()
            totals[col] = (s_v / s_r * 100) if s_r > 0 else 0
        else:
            totals[col] = df_final[col].sum()
    
    df_final.loc['TOTAL'] = totals
    return df_final

def gerar_tabelas_produtos_cruzada(df):
    if df.empty:
        return pd.DataFrame().style

    # Definição das colunas baseadas na estrutura do seu código
    c_loja, c_comprador, c_produto, c_preco_conc, c_concorrente, c_preco_mart = \
        cols[0], cols[1], cols[2], cols[3], cols[5], cols[6]

    # 1. Limpeza e Garantia de tipos
    df = df.copy()
    for col in [c_preco_conc, c_preco_mart]:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce')

    # 2. Agregação para remover duplicatas antes do pivot
    # Isso evita o erro de "non-unique index"
    df_base = (
        df.groupby([c_comprador, c_produto, c_concorrente, c_loja], as_index=False)
        .agg({c_preco_conc: 'mean', c_preco_mart: 'max'})
        .dropna(subset=[c_preco_conc])
    )

    idx_cols = [c_comprador, c_produto]

    # 3. Construção das partes (Médias e Lojas)
    df_medias = df_base.pivot_table(index=idx_cols, columns=c_concorrente, values=c_preco_conc, aggfunc='mean')
    
    df_lojas = df_base.assign(Loja_Label=df_base[c_concorrente] + " / " + df_base[c_loja]) \
                      .pivot_table(index=idx_cols, columns='Loja_Label', values=c_preco_conc, aggfunc='mean')

    df_mart = df_base.groupby(idx_cols)[c_preco_mart].max().to_frame("Mart Minas")

    # 4. Cálculo da Competitividade (Menor preço > 0 entre todos os concorrentes)
    todos_conc = pd.concat([df_medias, df_lojas], axis=1)
    menor_valor_conc = todos_conc.replace(0, np.nan).min(axis=1)
    
    df_mart["Comp. %"] = (df_mart["Mart Minas"] / menor_valor_conc)

    # NOVO: Remove da visualização o que estiver fora do range configurado
    mask_visual = (df_mart["Comp. %"] >= st.session_state.range_min) & \
                (df_mart["Comp. %"] <= st.session_state.range_max)
    
    df_final = pd.concat([df_mart, df_medias, df_lojas], axis=1)
    df_final = df_final[mask_visual] # Aplica o corte na tabela final

    # 6. Formatação Segura
    def formatar_valores(val, is_perc=False):
        if pd.isna(val) or val == 0: return ""
        if is_perc: return f"{val:.1%}"
        return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # Criando o dicionário de formatação mapeado
    format_map = {}
    for col in df_final.columns:
        if col == "Comp. %":
            format_map[col] = lambda x: formatar_valores(x, is_perc=True)
        else:
            format_map[col] = lambda x: formatar_valores(x)

    return df_final.style.format(format_map)

# ================== APP ==================
try:
    client = gspread.authorize(authenticate_gspread())
    planilhas_drive = listar_planilhas_no_drive(client)
    NOME_PADRAO = "Pesquisa de Preços"

    if st.session_state.autenticado and st.session_state.perfil == "comercial":
        # Criamos uma lista filtrada excluindo o nome indesejado
        opcoes_arquivos = [nome for nome in planilhas_drive.keys() if nome != "Pesquisa de Preços"]
        
        # Usamos a lista filtrada no selectbox
        nome_sel = st.sidebar.selectbox("Arquivo:", options=opcoes_arquivos, key="filtro_planilha")
        id_atual = planilhas_drive[nome_sel]
    else:
        # Mantém a lógica padrão para outros casos
        id_atual = planilhas_drive.get(NOME_PADRAO, list(planilhas_drive.values())[0])
    df_raw = fetch_data(id_atual)
    cols = df_raw.columns

    if st.session_state.autenticado and st.session_state.perfil == "comercial":
        comprador_sel = st.sidebar.selectbox("Filtrar Comprador:", ["TODOS"] + sorted(df_raw[cols[1]].unique().tolist()))
        df_completo = df_raw[df_raw[cols[1]] == comprador_sel].copy() if comprador_sel != "TODOS" else df_raw.copy()
    else:
        df_completo = df_raw.copy()

    # Login
    if not st.session_state.autenticado:            
            st.image("banner.png", use_container_width=True)
            st.markdown('<div class="titulo-centralizado">Portal de Pesquisa</div>', unsafe_allow_html=True)
            t1, t2 = st.tabs(["Acesso Lojas 🏪", "Acesso Comercial 📊"])
            
            with t1: # Lógica vinda do app.py
                with st.container(border=True):
                    loja = st.selectbox("Loja:", sorted(df_raw[cols[0]].unique()))
                    concorrentes_disp = sorted(df_raw[df_raw[cols[0]] == loja][cols[5]].unique())
                    concorrente = st.selectbox("Concorrente:", concorrentes_disp)
                    if st.button("Entrar 🚀", use_container_width=True, type="primary"):
                        st.session_state.update({"perfil": "loja", "autenticado": True, 
                                            "loja_sel": loja, "concorrente_sel": concorrente})
                        st.rerun()

            with t2:
                senha = st.text_input("Senha Comercial:", type="password")
                if st.button("Acessar Painel 📈", use_container_width=True):
                    if senha == "comercialmm2026":
                        st.session_state.update({"perfil": "comercial", "autenticado": True})
                        st.rerun()
            st.stop()

    if st.session_state.perfil == "comercial":
        st.markdown(f'<div class="titulo-centralizado">{nome_sel if "nome_sel" in locals() else NOME_PADRAO}</div>', unsafe_allow_html=True)
        
        # BARRA LATERAL
        st.sidebar.divider()
        
        # ================= APLICA CONFIGURAÇÕES ATIVAS =================
        df_filtrado = aplicar_filtros_configuracoes(df_completo)

        # ================= MONTA DICIONÁRIO DE EXPORTAÇÃO =================
        dict_all = {"Base Completa Drive": df_filtrado}

        labels = ["Comprador", "Concorrente", "Loja"]

        for i, grp in enumerate([cols[1], cols[5], cols[0]]):
            dict_all[f"Contagem_{labels[i]}"] = calcular_metricas_simples(df_filtrado, grp)
            dict_all[f"Soma_{labels[i]}"] = calcular_soma_competitividade_simples(df_filtrado, grp, format_money=False)

        excel_data = to_excel_consolidated(dict_all)
        st.sidebar.download_button(
            label="📥 Exportar Relatório Completo",
            data=excel_data,
            file_name=f"Relatorio_Consolidado.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

        tabs = st.tabs(["Comprador", "Concorrente", "Loja", "Completo", "Preços Por Produto", "⚙️ Configurações"])
        
        # FORMATADOR INTELIGENTE DE COLUNAS
        def aplicar_estilo_dinamico(styler):
            # Obtém os nomes das colunas (incluindo MultiIndex se houver)
            colunas = styler.data.columns
            format_dict = {}
            
            for col in colunas:
                # Se for MultiIndex, pega o último nível da tupla
                nome_col = col[2] if isinstance(col, tuple) and len(col) > 2 else (col[1] if isinstance(col, tuple) else col)
                
                if "Comp. %" in str(nome_col) or "%" in str(nome_col):
                    format_dict[col] = "{:.1f}%"
                elif any(word in str(nome_col) for word in ["Soma", "Média", "Mart Minas", "Concorrente"]):
                    format_dict[col] = formatar_moeda
                else:
                    # Se for contagem pura (Encontrados, Menor, Maior)
                    format_dict[col] = lambda x: "" if pd.isna(x) else f"{int(x)}" if isinstance(x, (int, float)) else x
            
            return styler.format(format_dict)

        # Abas Comprador, Concorrente, Loja
        for i, grp in enumerate([cols[1], cols[5], cols[0]]):
            with tabs[i]:
                st.subheader("Mart Minas Menor Preço")
                df_met = calcular_metricas_simples(df_filtrado, grp)
                st.dataframe(df_met, use_container_width=True, hide_index=True)
                
                st.divider()
                st.subheader("Cestas R$")
                df_sm = calcular_soma_competitividade_simples(df_filtrado, grp, format_money=False)
                st.dataframe(aplicar_estilo_dinamico(df_sm.style), use_container_width=True, hide_index=True)

        with tabs[3]: # Aba Completo
            st.subheader("Mart Minas Menor Preço")
            df_lc_c = visao_matriz_loja_concorrente(df_filtrado, "contagem")
            st.dataframe(aplicar_estilo_dinamico(df_lc_c.style), use_container_width=True)
            
            st.divider()
            st.subheader("Cestas R$")
            df_lc_s = visao_matriz_loja_concorrente(df_filtrado, "soma")
            st.dataframe(aplicar_estilo_dinamico(df_lc_s.style), use_container_width=True)

        with tabs[4]:
            st.subheader("Preços por Produto (Concorrentes × Mart Minas)")
            df_styled = gerar_tabelas_produtos_cruzada(df_filtrado)
            st.dataframe(
                df_styled,
                use_container_width=True,
                hide_index=False,           # mostra comprador e produto no índice
            )

        with tabs[5]:  # Aba Configurações

            # Inicializa temporários se não existirem
            if "tmp_range_min" not in st.session_state:
                st.session_state.tmp_range_min = st.session_state.range_min

            if "tmp_range_max" not in st.session_state:
                st.session_state.tmp_range_max = st.session_state.range_max

            if "tmp_considerar_obs" not in st.session_state:
                st.session_state.tmp_considerar_obs = st.session_state.considerar_obs

            if "tmp_considerar_menor_preco" not in st.session_state:
                st.session_state.tmp_considerar_menor_preco = st.session_state.considerar_menor_preco

            # ================== FORM (SEM RERUN AUTOMÁTICO) ==================
            with st.form("form_configuracoes"):

                st.markdown("### Range de Competitividade")

                col1, col2 = st.columns(2)

                with col1:
                    tmp_min = st.number_input(
                        "Range mínimo (%)",
                        min_value=0.0,
                        max_value=1000.0,
                        value=st.session_state.tmp_range_min * 100,
                        step=5.0
                    )

                with col2:
                    tmp_max = st.number_input(
                        "Range máximo (%)",
                        min_value=0.0,
                        max_value=1000.0,
                        value=st.session_state.tmp_range_max * 100,
                        step=5.0
                    )

                st.divider()

                tmp_obs = st.checkbox(
                    "Considerar produtos com observação",
                    value=st.session_state.tmp_considerar_obs
                )

                tmp_menor_preco = st.checkbox(
                    'Considerar produtos com "(MENOR PREÇO)" no nome',
                    value=st.session_state.tmp_considerar_menor_preco
                )

                st.divider()

                salvar = st.form_submit_button("💾 Salvar Configurações", use_container_width=True)

                if salvar:
                    st.session_state.range_min = tmp_min / 100
                    st.session_state.range_max = tmp_max / 100
                    st.session_state.considerar_obs = tmp_obs
                    st.session_state.considerar_menor_preco = tmp_menor_preco

                    # Atualiza temporários também
                    st.session_state.tmp_range_min = tmp_min / 100
                    st.session_state.tmp_range_max = tmp_max / 100
                    st.session_state.tmp_considerar_obs = tmp_obs
                    st.session_state.tmp_considerar_menor_preco = tmp_menor_preco

                    st.success("Configurações aplicadas com sucesso!")
                    st.rerun()
                    
    elif st.session_state.perfil == "loja":
        if st.sidebar.button("⬅️ Sair / Trocar Loja"):
            st.session_state.autenticado = False
            st.rerun()

        # Filtros de Pesquisa
        df_f = df_raw[(df_raw[cols[0]] == st.session_state.loja_sel) & 
                      (df_raw[cols[5]] == st.session_state.concorrente_sel)]
        
        comp_sel = st.sidebar.selectbox("Filtrar por Setor:", ["Todos"] + sorted(df_f[cols[1]].unique()))
        if comp_sel != "Todos":
            df_f = df_f[df_f[cols[1]] == comp_sel]
                    
        st.image("banner.png", use_container_width=True)

        if not df_f.empty:
            # Progresso
            total = len(df_f)
            preenchidos = df_f[cols[3]].apply(lambda x: str(x).strip() != "").sum()
            st.progress(preenchidos / total)
            st.write(f"Progresso: {preenchidos} de {total}")

            # Seleção de Produto
            opcoes = [f"{('✅' if str(r[cols[3]]).strip() != '' else '❌')} {r[cols[2]]}" 
                      for _, r in df_f.sort_values(by=cols[2]).iterrows()]
            
            idx = min(st.session_state.prod_idx, len(opcoes)-1)
            escolha = st.selectbox("Selecione o Produto:", opcoes, index=idx)
            produto_nome = escolha[2:].strip()
            st.session_state.prod_idx = opcoes.index(escolha)

            item = df_f[df_f[cols[2]] == produto_nome]
            if not item.empty:
                idx_real = item.index[0]
                
                with st.container(border=True):
                    # --- LAYOUT DINÂMICO (ADAPTA AO MODO CLARO/ESCURO) ---
                    st.markdown(f"""
                        <div style="
                            padding: 12px 20px; 
                            border-radius: 10px; 
                            margin-bottom: 20px; 
                            border: 1px solid rgba(128, 128, 128, 0.3);
                            background-color: var(--secondary-bg-color);
                            display: flex;
                            justify-content: space-around;
                            align-items: center;
                            color: var(--text-color);
                        ">
                            <div style="font-size: 14px; font-weight: 500;">
                                Loja: <span style="font-weight: bold;">{st.session_state.loja_sel}</span>
                            </div>
                            <div style="width: 1px; height: 25px; background-color: rgba(128, 128, 128, 0.3);"></div>
                            <div style="font-size: 14px; font-weight: 500;">
                                Concorrente: <span style="font-weight: bold;">{st.session_state.concorrente_sel}</span>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    # -------------------------------------------------------

                    c1, c2 = st.columns(2)
                    with c1:
                        preco = st.text_input("Preço Concorrente (R$):", 
                                            value=str(item.iloc[0][cols[3]]),
                                            key=f"p_{idx_real}")
                    with c2:
                        obs = st.text_input("Observação:", 
                                        value=str(item.iloc[0][cols[4]]),
                                        key=f"o_{idx_real}")
                    
                    if st.button("💾 Salvar e Avançar", type="primary", use_container_width=True):
                        salvar_dados(id_atual, idx_real, preco, obs)
                        st.session_state.prod_idx = min(st.session_state.prod_idx + 1, len(opcoes)-1)
                        st.rerun()
except Exception as e: 
    st.error(f"Erro: {e}")
