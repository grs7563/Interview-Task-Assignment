# AI-Powered Document Intelligence System

Automated system for processing invoices, receipts, and financial documents (PDF, images, Excel, CSV). Extracts structured data, validates results, and provides a web interface for review and search.

## Features

- Multi-format document processing (PDF, JPG, PNG, TIFF, XLSX, CSV)
- Digital PDF text extraction + OCR for scanned documents
- Structured invoice field extraction (invoice number, date, supplier, totals, line items)
- Validation rules (missing fields, amount consistency, duplicates)
- SQLite database with keyword search
- Gradio web interface for upload, monitoring, correction, and search
- Automated tests and evaluation metrics

## Technology Stack

| Component | Technology |
|-----------|------------|
| Document Processing | pdfplumber, Tesseract OCR, pandas, openpyxl |
| Extraction | Rule-based (LLM-ready) |
| Frontend | Gradio |
| Database | SQLite |
| Language | Python 3 |

## Setup Instructions

### Option 1: Google Colab (Recommended)

1. Open [Google Colab](https://colab.research.google.com)
2. Upload `Document_Intelligence_System_Colab.ipynb`
3. Runtime → Change runtime type → GPU (optional)
4. Runtime → Run all
5. Open the Gradio public URL that appears

### Option 2: Local

```bash
# Install system dependencies
sudo apt-get install tesseract-ocr poppler-utils

# Install Python packages
pip install pdfplumber pdf2image pytesseract Pillow pandas openpyxl gradio

# Run the notebook or convert to script
jupyter notebook Document_Intelligence_System_Colab.ipynb
```

## Project Structure

```
.
├── Document_Intelligence_System_Colab.ipynb   # Main system
├── ARCHITECTURE.md                            # Diagram + DB schema
├── EVALUATION_REPORT.md                       # Metrics and analysis
├── sample_invoices/                           # Sample files for testing
│   ├── Invoice_NOFRA_2026-1042.pdf
│   ├── Invoice_NOFRA_2026-1042.png
│   ├── Invoice_NOFRA_2026-1042.xlsx
│   └── Invoice_NOFRA_2026-1042.csv
└── README.md
```

## Usage

1. Upload one or more documents via the Gradio interface
2. Click **Start Processing**
3. Review the extraction summary table
4. Use the **Search** tab to find previously processed documents
5. Use the **Manual Correction** tab to fix any fields

## Evaluation Results

| Metric | Result |
|--------|--------|
| Automated Tests | 6/6 passed |
| Field Extraction Accuracy | 85.7% |
| Document Success Rate | 100% (on sample set) |
| Average Extraction Time | < 0.1 sec (rule-based) |

See `EVALUATION_REPORT.md` for full details.

## AI Disclosure

This project was developed with AI assistance (Grok by xAI) for code generation, architecture design, and documentation. All logic was reviewed and adapted to meet the assignment requirements. The extraction system is primarily rule-based and does not invent missing values.

## License

For educational / assignment use.
