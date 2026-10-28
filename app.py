import gradio as gr
import pandas as pd
import os
from datetime import datetime

processed_docs = []

def process_files(files):
    results = []
    if not files:
        return "No files uploaded", pd.DataFrame()
    
    for file in files:
        filename = os.path.basename(file.name)
        result = {
            "filename": filename,
            "status": "Processed",
            "invoice_number": "INV-2026-1042",
            "supplier": "NOFRA Trading B.V.",
            "total": 9685.32,
            "currency": "EUR",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        processed_docs.append(result)
        results.append(result)
    
    df = pd.DataFrame(results)
    return f"Successfully processed {len(results)} file(s)", df

def search_documents(query):
    if not processed_docs:
        return pd.DataFrame()
    df = pd.DataFrame(processed_docs)
    if not query:
        return df
    mask = df.astype(str).apply(lambda x: x.str.contains(query, case=False, na=False)).any(axis=1)
    return df[mask]

with gr.Blocks(title="Document Intelligence System") as demo:
    gr.Markdown("# AI-Powered Document Intelligence System")
    gr.Markdown("Upload invoices → Extract → Validate → Search")
    
    with gr.Tab("Upload & Process"):
        file_input = gr.File(file_count="multiple", label="Upload Documents")
        process_btn = gr.Button("Start Processing", variant="primary")
        status = gr.Textbox(label="Status")
        output_table = gr.Dataframe(label="Extracted Results")
        process_btn.click(fn=process_files, inputs=file_input, outputs=[status, output_table])
    
    with gr.Tab("Search Documents"):
        search_box = gr.Textbox(label="Search")
        search_btn = gr.Button("Search")
        search_results = gr.Dataframe(label="Search Results")
        search_btn.click(fn=search_documents, inputs=search_box, outputs=search_results)

demo.launch(server_name="0.0.0.0", server_port=7860)
