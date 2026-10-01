# FileToJSON

A generic PDF-to-JSON conversion API for tracking documents and other PDF-based records. It parses uploaded PDFs, extracts structured fields, and can save the results to MongoDB.

---

## API Overview

This project exposes a Flask REST API for converting PDF shipping/tracking documents into structured JSON and storing the results in MongoDB.

Use it like this:
- upload one PDF or many PDFs with `POST /api/convert`
- send a ZIP archive to the same endpoint to extract PDF files automatically
- read saved records with `GET /api/get` or one of its aliases
- update matching records with `PUT /api/update` or update a specific record by Mongo `_id`
- delete matching records or clear the collection using `DELETE /api/delete` and `DELETE /api/delete-all`

The API is designed for simple document workflows: upload -> parse -> save -> fetch -> update/delete as needed.

Swagger docs are available at:
- `http://localhost:5000/swagger`
- `http://localhost:5000/openapi.json`

Primary endpoints:
- `POST /api/convert` — upload one PDF, several PDFs, or a ZIP archive
- `GET /api/get` — fetch stored MongoDB records
- `GET /api/getfromdb` and `GET /api/get-from-db` — compatibility aliases
- `PUT /api/update` — update one or many documents by condition, or all documents
- `PUT /api/update-all` — update every document in MongoDB
- `PUT /api/update/<document_id>` — update a specific document by Mongo `_id`
- `DELETE /api/delete` — delete by condition or all documents
- `DELETE /api/delete/<document_id>` — delete by Mongo `_id`
- `DELETE /api/delete-all` — remove every document from MongoDB

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

### 2. Upload multiple PDFs in one request
```bash
curl -s -F "files=@/path/to/a.pdf" -F "files=@/path/to/b.pdf" http://localhost:5000/api/convert
```

### 3. Upload a ZIP archive of PDFs
```bash
curl -s -F "file=@/path/to/archive.zip" http://localhost:5000/api/convert
```

### 4. Fetch saved Mongo documents
```bash
curl -s http://localhost:5000/api/get
curl -s "http://localhost:5000/api/get?status=delivered"
curl -s http://localhost:5000/api/getfromdb
```

### 5. Update a document by status or id
```bash
curl -s -X PUT http://localhost:5000/api/update \
  -H "Content-Type: application/json" \
  -d '{
    "status": "in_transit",
    "data": { "status": "delivered", "delivery_status": "Delivered" }
  }'

curl -s -X PUT http://localhost:5000/api/update-all \
  -H "Content-Type: application/json" \
  -d '{
    "data": { "delivery_status": "Reviewed" }
  }'

curl -s -X PUT http://localhost:5000/api/update/64f5d1d6c9e9f0d9e2aa1234 \
  -H "Content-Type: application/json" \
  -d '{"status": "delivered"}'
```

### 6. Delete by status, id, or all documents
```bash
curl -s -X DELETE http://localhost:5000/api/delete \
  -H "Content-Type: application/json" \
  -d '{"status": "delivered"}'

curl -s -X DELETE http://localhost:5000/api/delete/64f5d1d6c9e9f0d9e2aa1234
curl -s -X DELETE http://localhost:5000/api/delete-all
```

### 7. Health check
```bash
curl -s http://localhost:5000/health
```

### 8. Swagger UI
```bash
http://localhost:5000/swagger
```

