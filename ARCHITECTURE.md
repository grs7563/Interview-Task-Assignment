# Architecture Diagram

```mermaid
flowchart TD
    A[User Uploads Files<br/>PDF / JPG / PNG / TIFF / XLSX / CSV] --> B[Gradio Frontend<br/>Task 6]
    B --> C[Job Queue<br/>Background Processing<br/>Task 4]
    
    C --> D[Task 1: Document Processing]
    D --> D1[Digital PDF<br/>pdfplumber]
    D --> D2[Scanned PDF / Image<br/>Tesseract OCR + Preprocessing]
    D --> D3[Spreadsheet<br/>pandas / openpyxl]
    
    D1 & D2 & D3 --> E[Task 2: AI Extraction<br/>Rule-based + Optional LLM]
    E --> F[Task 3: Validation Engine<br/>Missing fields, Amount checks,<br/>Duplicates, Manual review flags]
    
    F --> G[Task 5: Database<br/>SQLite]
    G --> G1[documents]
    G --> G2[extractions]
    G --> G3[validations]
    G --> G4[processing_history]
    
    G --> H[Search & Correction<br/>Keyword search + Manual edit]
    H --> B
    
    style A fill:#e1f5fe
    style B fill:#f3e5f5
    style G fill:#e8f5e9
    style E fill:#fff3e0
```

## Database Schema

```sql
-- documents
CREATE TABLE documents (
    id              TEXT PRIMARY KEY,
    original_name   TEXT NOT NULL,
    file_type       TEXT,
    status          TEXT DEFAULT 'pending',
    uploaded_at     TEXT,
    processed_at    TEXT,
    processing_time REAL,
    page_count      INTEGER DEFAULT 0,
    full_text       TEXT,
    error_message   TEXT
);

-- extractions
CREATE TABLE extractions (
    id              TEXT PRIMARY KEY,
    document_id     TEXT REFERENCES documents(id),
    invoice_number  TEXT,
    invoice_date    TEXT,
    supplier_name   TEXT,
    customer_name   TEXT,
    subtotal        REAL,
    tax_amount      REAL,
    total           REAL,
    currency        TEXT,
    extracted_json  TEXT,
    created_at      TEXT
);

-- validations
CREATE TABLE validations (
    id                  TEXT PRIMARY KEY,
    document_id         TEXT REFERENCES documents(id),
    is_valid            INTEGER,
    needs_manual_review INTEGER,
    score               REAL,
    errors_json         TEXT,
    warnings_json       TEXT,
    created_at          TEXT
);

-- processing_history
CREATE TABLE processing_history (
    id          TEXT PRIMARY KEY,
    document_id TEXT,
    event       TEXT,
    details     TEXT,
    created_at  TEXT
);
```
