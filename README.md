# FileToJSON

A high-performance Python REST API and batch engine tailored for converting **Speed Post Consignment Tracking PDFs (`trk1.pdf`, `trk2.pdf`, etc.)** into clean, structured JSON.

Processes **1,000+ tracking documents in ~2 seconds** using multi-core parallel processing.

---

## 📁 Clean & Proper Folder Structure

```
file_to_json/
├── app.py                  # Flask REST API Server (Postman & curl ready)
├── cli.py                  # CLI command for terminal batch conversion
├── config.py               # Worker & server configuration
├── requirements.txt        # Minimal requirements (flask)
├── README.md               # Postman, curl, and architecture guide
│
├── parsers/                # 🔹 Small, Reusable Tracking Parser Functions
│   ├── __init__.py         # Exports parse_tracking_pdf()
│   ├── extractor.py        # extract_text_from_pdf_path(), extract_text_from_pdf_bytes()
│   ├── header.py           # extract_consignment_number(), extract_article_type(), extract_tariff()
│   ├── booking.py          # extract_booking_office(), extract_booking_date(), extract_destination_pin()
│   ├── routing.py          # parse_single_routing_step(), extract_routing_steps()
│   ├── status.py           # detect_return_info(), build_milestones(), format_status_label()
│   └── tracking_parser.py  # Orchestrator assembling the clean JSON dictionary
│
├── engine/                 # 🔹 High-Speed Parallel Batch Engine
│   ├── __init__.py         # Exports convert_batch_parallel()
│   └── batch.py            # Multi-worker thread pool (processes 1,000+ files in ~2s)
│
├── samples/                # Sample test files
│   ├── trk1.pdf            # Sample: Refused (QM122475425IN)
│   └── trk2.pdf            # Sample: No such person (QM122476960IN)
│
├── output/                 # Output directory for converted JSON files
│
└── tests/                  # Automated unit test suite
    └── test_tracking.py    # 4 unit tests (all passing)
```

---

## 🚀 How to Run the Server

Start the API server on `http://localhost:5000`:

```bash
python3 app.py
```

---

## 📮 How to Test in Postman

### 1. Test Single File Upload (`POST /api/convert`)
1. Open Postman and create a new request.
2. Set Method to **`POST`**.
3. Enter URL: `http://localhost:5000/api/convert`
4. Click on the **Body** tab below the URL bar.
5. Select **form-data**.
6. In the **KEY** column, enter: `file`
7. Hover over `file`, click the dropdown on the right side of the box, and select **File** (instead of Text).
8. In the **VALUE** column, click **Select Files** and choose `trk1.pdf` (or any tracking PDF).
9. Click **Send**.

---

### 2. Test Batch Multi-File Upload (`POST /api/convert-batch`)
1. Set Method to **`POST`**.
2. Enter URL: `http://localhost:5000/api/convert-batch`
3. Click on the **Body** tab -> select **form-data**.
4. In the **KEY** column, enter: `files` (set type to **File**).
5. In the **VALUE** column, select multiple PDF files at once.
6. Click **Send**.

---

### 3. Test Batch via Directory Path (`POST /api/convert-batch`)
To convert an entire folder of 1,000+ PDFs without uploading them through the browser:
1. Set Method to **`POST`**.
2. Enter URL: `http://localhost:5000/api/convert-batch`
3. Click **Body** -> select **raw** -> choose **JSON** in the dropdown.
4. Paste:
```json
{
  "directory": "/home/siddarth-fsc/Downloads/your_1000_pdfs_folder",
  "workers": 16,
  "output_dir": "output/converted_json"
}
```
5. Click **Send**.

---

## 💻 Ready-to-Run `curl` Commands

### 1. Health Check
```bash
curl -s http://localhost:5000/health
```

### 2. Single Tracking PDF Upload
```bash
curl -s -F "file=@samples/trk1.pdf" http://localhost:5000/api/convert
```

### 3. Batch Multi-File Upload
```bash
curl -s -F "files=@samples/trk1.pdf" -F "files=@samples/trk2.pdf" http://localhost:5000/api/convert-batch
```

### 4. 1-Click Sample Test
```bash
curl -s http://localhost:5000/api/sample/trk1
```

---

## ⚡ Command Line Tool (CLI)

You can also run batch conversions directly from the terminal without Postman:

```bash
# Convert a single file:
python3 cli.py samples/trk1.pdf -o output/trk1.json

# Convert an entire folder of 1,000+ PDFs:
python3 cli.py -i /path/to/pdf_folder/ -d output/json_records/

# Convert all PDFs into a single combined master JSON:
python3 cli.py -i /path/to/pdf_folder/ -o output/all_records.json
```

---

## 🧪 Run Unit Tests
```bash
python3 -m unittest discover -s tests
```
