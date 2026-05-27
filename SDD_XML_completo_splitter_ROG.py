import streamlit as st
from lxml import etree
import io

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="SDD Multi-Splitter APE", layout="wide")

def process_sdd_xml(xml_bytes, split_requests):
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(io.BytesIO(xml_bytes), parser)
    root = tree.getroot()
    
    # Processiamo ogni richiesta di split accumulata
    for req in split_requests:
        instr_id_target = req['instr_id']
        installments = req['installments']
        
        # 1. Ricerca della transazione
        target_tx = None
        for tx in root.xpath(".//*[local-name()='DrctDbtTxInf']"):
            res = tx.xpath(".//*[local-name()='InstrId']")
            if res and res[0].text.strip() == str(instr_id_target).strip():
                target_tx = tx
                break
        
        if target_tx is None: continue # Salta se non trovata

        parent_pmt_inf = target_tx.getparent()
        log_msg = parent_pmt_inf.getparent()
        parent_pmt_inf.remove(target_tx)
        
        # 2. Creazione rate
        for i, inst in enumerate(installments):
            new_pmt_inf = etree.fromstring(etree.tostring(parent_pmt_inf))
            for tx_to_rem in new_pmt_inf.xpath(".//*[local-name()='DrctDbtTxInf']"):
                new_pmt_inf.remove(tx_to_rem)
                
            # Dinamismo PmtInfId
            pmt_inf_id_nodes = new_pmt_inf.xpath(".//*[local-name()='PmtInfId']")
            if pmt_inf_id_nodes:
                data_str = inst['date'].strftime('%Y%m%d')
                base_id = pmt_inf_id_nodes[0].text
                suffix = base_id.split('-')[-1] if '-' in base_id else "291"
                pmt_inf_id_nodes[0].text = f"SottoDistinta-RCUR-{data_str}-{suffix}"
                
            new_tx = etree.fromstring(etree.tostring(target_tx))
            # Aggiornamento dati rata
            amt_nodes = new_tx.xpath(".//*[local-name()='InstdAmt']")
            if amt_nodes: amt_nodes[0].text = f"{inst['amount']:.2f}"
            for tag in ["InstrId", "EndToEndId"]:
                nodes = new_tx.xpath(f".//*[local-name()='{tag}']")
                if nodes: nodes[0].text = f"{instr_id_target}R{i+1}"
            
            new_pmt_inf.append(new_tx)
            colltn_dt = new_pmt_inf.xpath(".//*[local-name()='ReqdColltnDt']")
            if colltn_dt: colltn_dt[0].text = inst['date'].strftime('%Y-%m-%d')
            nb_txs = new_pmt_inf.xpath(".//*[local-name()='NbOfTxs']")
            if nb_txs: nb_txs[0].text = "1"
            log_msg.append(new_pmt_inf)

    # 3. Pulizia finale contatori globali
    for pmt in root.xpath(".//*[local-name()='PmtInf']"):
        count = len(pmt.xpath(".//*[local-name()='DrctDbtTxInf']"))
        nb = pmt.xpath(".//*[local-name()='NbOfTxs']")
        if nb: nb[0].text = str(count)
        
    total_count = len(root.xpath(".//*[local-name()='DrctDbtTxInf']"))
    grpHdr_nb = root.xpath(".//*[local-name()='GrpHdr']//*[local-name()='NbOfTxs']")
    if grpHdr_nb: grpHdr_nb[0].text = str(total_count)

    return etree.tostring(tree, pretty_print=True, encoding='ISO-8859-1', xml_declaration=True)

# --- UI STREAMLIT ---
st.title("✂️ SDD Multi-Splitter")
uploaded_file = st.file_uploader("Carica XML", type=["xml"])

if 'requests' not in st.session_state: st.session_state.requests = []

with st.expander("Aggiungi Fattura da Rateizzare"):
    instr = st.text_input("InstrId fattura")
    n_rate = st.number_input("Numero rate", 1, 12, 2)
    insts = []
    for i in range(n_rate):
        c1, c2 = st.columns(2)
        insts.append({'amount': c1.number_input(f"Importo {i+1}", min_value=0.0, key=f"a{i}"), 
                      'date': c2.date_input(f"Scadenza {i+1}", key=f"d{i}")})
    if st.button("Aggiungi alla lista"):
        st.session_state.requests.append({'instr_id': instr, 'installments': insts})

st.write("Fatture in coda:", st.session_state.requests)

if st.button("🚀 Genera XML Finale"):
    output = process_sdd_xml(uploaded_file.read(), st.session_state.requests)
    st.download_button("📥 Scarica XML", output, "SDD_Multi_Rateizzato.xml")