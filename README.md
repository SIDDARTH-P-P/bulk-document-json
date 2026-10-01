# FileToJSON

A generic PDF-to-JSON conversion API for tracking documents and other PDF-based records. It parses uploaded PDFs, extracts structured fields, and can save the results to MongoDB.

---

## API Overview

This project exposes a Flask REST API that accepts:
- single PDF upload
- multiple PDF uploads
- JSON payloads with `path`, `paths`, or `directory`
- Mongo-backed retrieval via `GET /api/get`

Swagger docs are available at:
- `http://localhost:5000/swagger`
- `http://localhost:5000/openapi.json`

If port `5000` is already occupied, the app automatically selects the next free port and prints the correct URL in the terminal.

---

## 🚀 Run the Server

```bash
python3 app.py
```

If you want to force a port:

```bash
PORT=5001 python3 app.py
```

---

## 📮 API Examples

### 1. Upload a single PDF
```bash
curl -s -F "file=@/path/to/document.pdf" http://localhost:5000/api/convert
```

### 2. Upload multiple PDFs
```bash
curl -s -F "files=@/path/to/a.pdf" -F "files=@/path/to/b.pdf" http://localhost:5000/api/convert-batch
```

### 3. Convert from a local folder
```bash
curl -s -X POST http://localhost:5000/api/convert-batch \
  -H "Content-Type: application/json" \
  -d '{
    "directory": "/path/to/pdf_folder",
    "workers": 8
  }'
```

### 4. Fetch saved Mongo documents
```bash
curl -s http://localhost:5000/api/get
```

### 5. Health check
```bash
curl -s http://localhost:5000/health
```

### 6. Swagger UI
```bash
http://localhost:5000/swagger
```

---

## 🧪 Run Unit Tests

```bash
python3 -m unittest discover -s tests
```
