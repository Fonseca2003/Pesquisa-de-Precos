import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ================== CONFIGURAÇÃO ==================
st.set_page_config(page_title="Pesquisa Mart Minas", layout="wide", page_icon="icon.png")

# ================== FUNÇÕES CORE ==================
@st.cache_resource
def authenticate_gspread():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_info = dict(st.secrets["gcp_service_account"])
    return Credentials.from_service_account_info(creds_info, scopes=scopes)

@st.cache_data(ttl=60)
def fetch_data(_sheet):
    data = _sheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])
    df = df.loc[:, df.columns != ''] 
    return df

def salvar_dados(sheet, indice_original, preco, observacao):
    try:
        preco_limpo = str(preco).replace(",", ".").strip()
        linha_sheets = int(indice_original + 2)
        sheet.update(f"D{linha_sheets}:E{linha_sheets}", [[preco_limpo, observacao]])
        st.toast("Dados salvos!", icon="✅")
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

# ================== APP ==================
try:
    client = gspread.authorize(authenticate_gspread())
    sheet = client.open("Pesquisas de Preços").get_worksheet(0)
    df_completo = fetch_data(sheet)

    col_loja = df_completo.columns[0]
    col_comprador = df_completo.columns[1]
    col_produto = df_completo.columns[2]
    col_preco = df_completo.columns[3]
    col_obs = df_completo.columns[4]
    col_concorrente = df_completo.columns[5]

    st.image("banner.png", use_container_width=True)
    st.title("Pesquisa de Preço")

    # --- SIDEBAR (FILTROS) ---
    st.sidebar.header("⚙️ Configurações")
    loja_sel = st.sidebar.selectbox("Selecione a Loja:", sorted(df_completo[col_loja].unique()))
    df_f = df_completo[df_completo[col_loja] == loja_sel]

    concorrente_sel = st.sidebar.selectbox("Selecione o Concorrente:", sorted(df_f[col_concorrente].unique()))
    df_f = df_f[df_f[col_concorrente] == concorrente_sel]

    comp_sel = st.sidebar.selectbox("Selecione o Comprador:", ["Todos"] + sorted(df_f[col_comprador].unique()))
    if comp_sel != "Todos":
        df_f = df_f[df_f[col_comprador] == comp_sel]

    # --- TELA PRINCIPAL ---
    if not df_f.empty:
        total_itens = len(df_f)
        itens_preenchidos = df_f[col_preco].apply(lambda x: str(x).strip() != "").sum()
        st.write(f"**Progresso da Pesquisa:** {itens_preenchidos} de {total_itens}")
        st.progress(itens_preenchidos / total_itens)
        st.divider()

        # --- LÓGICA DO EMOJI ✅ ---
        opcoes_menu = []
        mapa_nomes = {}
        produtos_do_filtro = sorted(df_f[col_produto].unique())
        
        for p in produtos_do_filtro:
            linha_p = df_f[df_f[col_produto] == p]
            preco_p = str(linha_p[col_preco].values[0]).strip()
            
            nome_com_status = f"{p} ✅" if preco_p != "" else p
            opcoes_menu.append(nome_com_status)
            mapa_nomes[nome_com_status] = p

        if "prod_idx" not in st.session_state: st.session_state.prod_idx = 0
        
        index_atual = min(st.session_state.prod_idx, len(opcoes_menu)-1)
        
        escolha_usuario = st.selectbox("Selecione o Produto:", opcoes_menu, index=index_atual)
        produto_sel = mapa_nomes[escolha_usuario]
        st.session_state.prod_idx = opcoes_menu.index(escolha_usuario)

        df_item = df_f[df_f[col_produto] == produto_sel]
        linha = df_item.iloc[0]
        indice_real = df_item.index[0]

        with st.container(border=True):
            espaco = "&nbsp;" * 3
            st.markdown(f"Loja: **{linha[col_loja]}**{espaco}|{espaco}Concorrente: **{linha[col_concorrente]}**{espaco}|{espaco}Setor: **{linha[col_comprador]}**", unsafe_allow_html=True)
            
            c1, c2 = st.columns(2)
            with c1:
                preco_novo = st.text_input("Preço (R$):", value=str(linha.get(col_preco, "")), key=f"pr_{produto_sel}")
            with c2:
                obs_nova = st.text_input("Observação:", value=str(linha.get(col_obs, "")), key=f"ob_{produto_sel}")

        if st.button("💾 Salvar e Avançar ➡️", type="primary", use_container_width=True):
            salvar_dados(sheet, indice_real, preco_novo, obs_nova)
            
            if st.session_state.prod_idx < len(opcoes_menu) - 1:
                st.session_state.prod_idx += 1
                st.rerun()
            else:
                st.balloons()
                st.success("✅ Pesquisa finalizada!")
    else:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")

except Exception as e:
    st.error(f"Erro inesperado: {e}")
