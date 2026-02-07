import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

# ================== CONFIGURAÇÃO ==================
st.set_page_config(page_title="Pesquisa Mart Minas", layout="wide", page_icon="icon.png")

# ID da pasta do Google Drive onde as fotos serão salvas
ID_PASTA_DRIVE = "1no08Luyn_UG0LwzfnPGCPKHjga7xN0t-" 

# ================== FUNÇÕES CORE ==================
@st.cache_resource
def authenticate_gspread():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    return gspread.authorize(creds)

def upload_foto_drive(imagem_bytes, nome_arquivo):
    try:
        creds_info = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/drive"])
        service = build('drive', 'v3', credentials=creds)

        file_metadata = {'name': nome_arquivo, 'parents': [ID_PASTA_DRIVE]}
        media = MediaIoBaseUpload(io.BytesIO(imagem_bytes), mimetype='image/jpeg')
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        return file.get('webViewLink')
    except Exception as e:
        st.error(f"Erro no upload: {e}")
        return None

@st.cache_data(ttl=60)
def fetch_data(_sheet):
    records = _sheet.get_all_records()
    return pd.DataFrame(records)

def salvar_dados(sheet, indice_original, preco, observacao, link_foto=None):
    try:
        preco_limpo = str(preco).replace(",", ".").strip()
        linha_sheets = int(indice_original + 2)
        
        # Atualiza Preço (D) e Observação (E)
        sheet.update(f"D{linha_sheets}:E{linha_sheets}", [[preco_limpo, observacao]])
        
        # Atualiza Link da Foto (G) se houver
        if link_foto:
            sheet.update_cell(linha_sheets, 7, link_foto)
            
        st.toast("Dados salvos com sucesso!", icon="✅")
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

# ================== APP ==================
try:
    client = authenticate_gspread()
    sheet = client.open("Pesquisas de Preços").get_worksheet(0)
    df_completo = fetch_data(sheet)

    col_loja, col_comprador, col_produto, col_preco = df_completo.columns[:4]
    col_obs = df_completo.columns[4] if len(df_completo.columns) > 4 else "Observação"
    col_concorrente = df_completo.columns[5]
    # Link da foto na coluna G (índice 6)
    col_link_foto = df_completo.columns[6] if len(df_completo.columns) > 6 else None

    st.image("banner.png", use_container_width=True)
    st.title("Pesquisa de Preços")

    # --- SIDEBAR ---
    st.sidebar.header("⚙️ Filtros")
    lista_lojas = sorted(df_completo[col_loja].unique())
    loja_sel = st.sidebar.selectbox("Selecione a Loja:", lista_lojas)
    df_f = df_completo[df_completo[col_loja] == loja_sel]

    lista_concorrentes = sorted(df_f[col_concorrente].unique())
    concorrente_sel = st.sidebar.selectbox("Selecione o Concorrente:", lista_concorrentes)
    df_f = df_f[df_f[col_concorrente] == concorrente_sel]

    comp_sel = st.sidebar.selectbox("Selecione o Setor:", ["Todos"] + sorted(df_f[col_comprador].unique()))
    if comp_sel != "Todos":
        df_f = df_f[df_f[col_comprador] == comp_sel]

    # --- TELA PRINCIPAL ---
    if not df_f.empty:
        # Progresso
        total_itens = len(df_f)
        itens_preenchidos = df_f[col_preco].apply(lambda x: str(x).strip() != "").sum()
        st.write(f"**Progresso:** {itens_preenchidos} de {total_itens}")
        st.progress(itens_preenchidos / total_itens)
        
        st.divider()

        lista_produtos = sorted(df_f[col_produto].unique())
        if "prod_idx" not in st.session_state: st.session_state.prod_idx = 0

        produto_sel = st.selectbox("Produto:", lista_produtos, index=min(st.session_state.prod_idx, len(lista_produtos)-1))
        st.session_state.prod_idx = lista_produtos.index(produto_sel)

        df_item = df_f[df_f[col_produto] == produto_sel]
        linha = df_item.iloc[0]
        indice_real = df_item.index[0]

        with st.container(border=True):
            st.caption(f"Loja: {linha[col_loja]} | Concorrente: {linha[col_concorrente]} | Setor: {linha[col_comprador]}")
            
            c1, c2 = st.columns(2)
            with c1:
                preco_novo = st.text_input("Preço (R$):", value=str(linha.get(col_preco, "")), key=f"pr_{produto_sel}")
            with c2:
                obs_nova = st.text_input("Observação:", value=str(linha.get(col_obs, "")), key=f"ob_{produto_sel}")

            # --- SEÇÃO DE FOTO ---
            st.write("---")
            col_foto, col_ver = st.columns([3, 1])
            with col_foto:
                nova_foto = st.camera_input("📸 Bater foto do produto", key=f"cam_{produto_sel}")
            with col_ver:
                link_existente = linha.get(col_link_foto) if col_link_foto else None
                if link_existente and str(link_existente).startswith("http"):
                    st.link_button("🖼️ Ver Foto", link_existente, use_container_width=True)
                else:
                    st.button("🖼️ Sem Foto", disabled=True, use_container_width=True)

        st.divider()

        if st.button("💾 Salvar e Próximo ➡️", type="primary", use_container_width=True):
            link_final = None
            if nova_foto:
                # Nome do arquivo com todos os campos separados por -
                nome_arq = f"{loja_sel}-{concorrente_sel}-{comp_sel}-{produto_sel}.jpg".replace("/", "_")
                with st.spinner("Enviando foto..."):
                    link_final = upload_foto_drive(nova_foto.getvalue(), nome_arq)
            
            salvar_dados(sheet, indice_real, preco_novo, obs_nova, link_final)
            
            if st.session_state.prod_idx < len(lista_produtos) - 1:
                st.session_state.prod_idx += 1
                st.rerun()
            else:
                st.balloons()
                st.success("✅ Pesquisa finalizada!")
    else:
        st.warning("Nenhum dado encontrado.")

except Exception as e:
    st.error(f"Erro inesperado: {e}")
