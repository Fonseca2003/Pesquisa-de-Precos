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
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def fetch_data(_sheet):
    records = _sheet.get_all_records()
    return pd.DataFrame(records)

def salvar_dados(sheet, indice_original, preco, observacao):
    try:
        preco_limpo = str(preco).replace(",", ".").strip()
        linha_sheets = int(indice_original + 2)
        sheet.update(f"D{linha_sheets}:E{linha_sheets}", [[preco_limpo, observacao]])
        st.toast("Dados salvos com sucesso!", icon="✅")
        # Limpa cache para refletir a mudança na próxima leitura
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

# ================== APP ==================
try:
    client = authenticate_gspread()
    sheet = client.open("Pesquisas de Preços").get_worksheet(0)
    df_completo = fetch_data(sheet)

    # Identificação das colunas
    col_loja, col_comprador, col_produto, col_preco = df_completo.columns[:4]
    col_obs = df_completo.columns[4] if len(df_completo.columns) > 4 else "Observação"

    # ================== SIDEBAR (FILTROS OBRIGATÓRIOS) ==================
    st.sidebar.header("⚙️ Filtros")
    
    # Loja: Removida a opção "Todas" para tornar obrigatória
    lista_lojas = sorted(df_completo[col_loja].unique())
    loja_sel = st.sidebar.selectbox("Selecione a Loja:", lista_lojas)
    
    df_f = df_completo[df_completo[col_loja] == loja_sel]

    # Comprador: Opcional (Todos)
    comp_sel = st.sidebar.selectbox("Filtrar por Comprador:", ["Todos"] + sorted(df_f[col_comprador].unique()))
    if comp_sel != "Todos":
        df_f = df_f[df_f[col_comprador] == comp_sel]

    # ================== TELA PRINCIPAL ==================
    st.image(
        "banner.png", 
        use_container_width=True
    )
    st.title("📝 Pesquisa de Preço")

    if not df_f.empty:
        # Filtro de Produto em Dropbox na tela principal
        lista_produtos = sorted(df_f[col_produto].unique())
        
        # Gerenciamento de índice no Session State para permitir o "Avançar"
        if "prod_idx" not in st.session_state:
            st.session_state.prod_idx = 0

        # Sincroniza o selectbox com o índice do session_state
        produto_sel = st.selectbox(
            "Selecione o Produto:", 
            lista_produtos, 
            index=min(st.session_state.prod_idx, len(lista_produtos)-1)
        )

        # Atualiza o índice se o usuário mudar manualmente o dropbox
        st.session_state.prod_idx = lista_produtos.index(produto_sel)

        # Extrai dados do item selecionado
        df_item = df_f[df_f[col_produto] == produto_sel]
        linha = df_item.iloc[0]
        indice_real = df_item.index[0]

        with st.container(border=True):
            st.caption(f"Loja: {linha[col_loja]} | Setor: {linha[col_comprador]}")
            
            c1, c2 = st.columns(2)
            with c1:
                preco_novo = st.text_input("Preço (R$):", value=str(linha.get(col_preco, "")), key=f"pr_{produto_sel}")
            with c2:
                obs_nova = st.text_input("Observação:", value=str(linha.get(col_obs, "")), key=f"ob_{produto_sel}")

        st.divider()

        # Botão Salvar e Avançar
        if st.button("💾 Salvar e Avançar ➡️", type="primary", use_container_width=True):
            # 1. Salva os dados
            salvar_dados(sheet, indice_real, preco_novo, obs_nova)
            
            # 2. Incrementa o índice para o próximo produto
            if st.session_state.prod_idx < len(lista_produtos) - 1:
                st.session_state.prod_idx += 1
                st.rerun()
            else:
                st.balloons()
                st.success("✅ Fim da lista para estes filtros!")

    else:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")

except Exception as e:
    st.error(f"Erro inesperado: {e}")
