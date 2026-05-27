import streamlit as st
from lxml import etree
import io
from collections import defaultdict

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="SDD Multi-Splitter APE", layout="wide")

def process_sdd_xml(xml_bytes, split_requests):
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(io.BytesIO(xml_bytes), parser)
    root = tree.getroot()
    
    # 1. Raggruppamento transazioni per data
    # { data_scadenza: [lista_oggetti_transazione_pronti] }
    aggregator = defaultdict(list)
    
    # Riferimento al padre per rimuovere le vecchie tx
    # (assumiamo che il file abbia una struttura standard dove PmtInf è sotto Document)
    for req in split_requests:
        instr_id_target = req['instr_id']
        installments = req['installments']
        
        target_tx = None
        for tx in root.xpath(".//*[local-name()='DrctDbtTxInf']"):
            res = tx.xpath(".//*[local-name()='InstrId']")
            if res and res[0].text.strip() == str(instr_id_target).strip():
                target_tx = tx
                # Rimuoviamo la transazione originale dal file
                tx.getparent().remove(tx)
                break
        
        if target_tx is None: continue

        # Prepariamo le nuove rate
        for i, inst in enumerate(installments):
            new_tx = etree.fromstring(etree.tostring(target_tx))
            # Aggiornamento dati rata
            amt_nodes = new_tx.xpath(".//*[local-name()='InstdAmt']")
            if amt_nodes: amt_nodes[0].text = f"{inst['amount']:.2f}"
            for tag in ["InstrId", "EndToEndId"]:
                nodes = new_tx.xpath(f".//*[local-name()='{tag}']")
                if nodes: nodes[0].text = f"{instr_id_target}R{i+1}"
            
            aggregator[inst['date']].append(new_tx)

    # 2. Inserimento nel XML raggruppato per data
    # Troviamo dove inserire le nuove PmtInf (solitamente dopo l'ultimo PmtInf esistente o sotto il CstmrDrctDbtInitn)
    parent_node = root.xpath(".//*[local-name()='CstmrDrctDbtInitn']")[0]
    
    # Creiamo un template di PmtInf basandoci sulla struttura originale (se esistente)
    template_pmt = root.xpath(".//*[local-name()='PmtInf']")[0]
    
    for date, tx_list in aggregator.items():
        new_pmt_inf = etree.fromstring(etree.tostring(template_pmt))
        
        # Pulizia transazioni ereditate dal template
        for tx_to_rem in new_pmt_inf.xpath(".//*[local-name()='DrctDbtTxInf']"):
            new_pmt_inf.remove(tx_to_rem)
            
        # Impostazione dati PmtInf
        date_str = date.strftime('%Y-%m-%d')
        new_pmt_inf.xpath(".//*[local-name()='ReqdColltnDt']")[0].text = date_str
        
        # PmtInfId unico per data
        pmt_id = new_pmt_inf.xpath(".//*[local-name()='PmtInfId']")[0]
        pmt_id.text = f"SDD-{date.strftime('%Y%m%d')}"
        
        # Aggiunta delle transazioni raggruppate
        for tx in tx_list:
            new_pmt_inf.append(tx)
            
        # Aggiornamento NbOfTxs per questa PmtInf
        nb_txs = new_pmt_inf.xpath(".//*[local-name()='NbOfTxs']")[0]
        nb_txs.text = str(len(tx_list))
        
        parent_node.append(new_pmt_inf)

    # 3. Pulizia e conteggi finali globali
    total_count = len(root.xpath(".//*[local-name()='DrctDbtTxInf']"))
    grpHdr_nb = root.xpath(".//*[local-name()='GrpHdr']//*[local-name()='NbOfTxs']")
    if grpHdr_nb: grpHdr_nb[0].text = str(total_count)

    return etree.tostring(tree, pretty_print=True, encoding='ISO-8859-1', xml_declaration=True)

# --- UI STREAMLIT (Invariata) ---
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
    if uploaded_file:
        output = process_sdd_xml(uploaded_file.getvalue(), st.session_state.requests)
        st.download_button("📥 Scarica XML", output, "SDD_Multi_Rateizzato.xml")
    else:
        st.error("Carica prima un file XML!")
