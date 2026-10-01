"""
Flask REST API Server for FileToJSON.
Handles single and multi-file uploads (1 to 1,000+ files).
Supports pagination: ?limit=1&page=1, as well as URL typos like &limit=1.
Preserves key order: success, pagination, data.
"""

import os
import urllib.parse
from flask import Flask, request, jsonify
from parsers import parse_tracking_pdf
from engine import convert_batch_parallel
from config import HOST, PORT, DEFAULT_WORKERS, MAX_CONTENT_LENGTH

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.json.sort_keys = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(BASE_DIR, "samples")

def get_pagination_params(extra_url_str=""):
    """
    Extracts page and limit from:
      1. Standard query parameters (?limit=1&page=1)
      2. Typo in URL path (&limit=1)
      3. Form-data or JSON payload
    """
    page = request.args.get("page", type=int)
    limit = request.args.get("limit", type=int)

    # If user accidentally typed '&limit=1' into the URL path
    if extra_url_str:
        parsed_extra = urllib.parse.parse_qs(extra_url_str)
        if "limit" in parsed_extra and not limit:
            try:
                limit = int(parsed_extra["limit"][0])
            except (ValueError, TypeError):
                pass
        if "page" in parsed_extra and not page:
            try:
                page = int(parsed_extra["page"][0])
            except (ValueError, TypeError):
                pass

    # Check form-data or JSON body fallback
    if request.form:
        if "limit" in request.form and not limit:
            try:
                limit = int(request.form["limit"])
            except (ValueError, TypeError):
                pass
        if "page" in request.form and not page:
            try:
                page = int(request.form["page"])
            except (ValueError, TypeError):
                pass
    elif request.is_json and request.json:
        if "limit" in request.json and not limit:
            try:
                limit = int(request.json["limit"])
            except (ValueError, TypeError):
                pass
        if "page" in request.json and not page:
            try:
                page = int(request.json["page"])
            except (ValueError, TypeError):
                pass

    return page or 1, limit

def build_api_response(data_list, page=1, limit=None, total_count=None):
    """Wraps result in the standard { success, pagination, data } format."""
    if not isinstance(data_list, list):
        data_list = [data_list]

    total = total_count if total_count is not None else len(data_list)
    lim = limit if limit is not None and limit > 0 else (total if total > 0 else 1)
    total_pages = max(1, (total + lim - 1) // lim) if lim > 0 else 1

    return {
        "success": True,
        "pagination": {
            "page": page,
            "limit": lim,
            "totalPages": total_pages,
            "totalCount": total
        },
        "data": data_list
    }

def get_all_uploaded_files():
    """Extracts all uploaded files from form-data regardless of field name ('file', 'files', etc.)."""
    uploaded = []
    for key in request.files:
        for f in request.files.getlist(key):
            if f and f.filename:
                uploaded.append(f)
    return uploaded

@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint showing service status and available endpoints."""
    return jsonify({
        "success": True,
        "service": "FileToJSON — Tracking PDF to JSON Converter API",
        "endpoints": {
            "POST /api/convert": "Convert 1 or multiple PDF files (upload under 'file' or 'files', or JSON 'path'/'paths')",
            "POST /api/convert-batch": "Batch convert 1,000+ PDFs (upload 'files' or JSON 'directory')",
            "GET /api/sample/trk1": "Test endpoint returning parsed trk1.pdf",
            "GET /api/sample/trk2": "Test endpoint returning parsed trk2.pdf"
        }
    }), 200

@app.route("/api/convert", methods=["POST"])
@app.route("/api/convert&<path:extra>", methods=["POST"])
@app.route("/api/convert-batch", methods=["POST"])
@app.route("/api/convert-batch&<path:extra>", methods=["POST"])
def convert_documents(extra=""):
    """
    Unified conversion endpoint.
    Accepts:
      - 1 or multiple PDF files via form-data (key 'file' or 'files')
      - Query params ?limit=X&page=Y or URL typo &limit=X
      - OR JSON body: { "path": "..." } or { "paths": [...] } or { "directory": "..." }
    """
    workers = request.args.get("workers", type=int) or DEFAULT_WORKERS
    page, limit = get_pagination_params(extra)

    # 1. Process Multipart Form-Data (supports 1, 2, or 1000+ files)
    uploaded_files = get_all_uploaded_files()
    if uploaded_files:
        if len(uploaded_files) == 1 and (limit is None or limit >= 1):
            f = uploaded_files[0]
            try:
                result = parse_tracking_pdf(f.read(), filename=f.filename)
                return jsonify(build_api_response([result], page=1, limit=limit or 1, total_count=1)), 200
            except Exception as e:
                return jsonify({"success": False, "error": str(e)}), 500
        else:
            items = [(f.filename, f.read()) for f in uploaded_files]
            stats = convert_batch_parallel(items=items, workers=workers)
            all_results = stats.get("results", [])
            total_count = len(all_results)

            # Apply pagination if limit is specified
            if limit and limit > 0:
                start_idx = (page - 1) * limit
                end_idx = start_idx + limit
                paginated_data = all_results[start_idx:end_idx]
            else:
                paginated_data = all_results

            return jsonify(build_api_response(
                data_list=paginated_data,
                page=page,
                limit=limit or total_count,
                total_count=total_count
            )), 200

    # 2. Process JSON Payload
    if request.is_json:
        payload = request.get_json() or {}
        single_path = payload.get("path")
        paths = payload.get("paths", [])
        target_dir = payload.get("directory")
        custom_workers = payload.get("workers", workers)

        # Single path
        if single_path and os.path.isfile(single_path):
            try:
                result = parse_tracking_pdf(single_path)
                return jsonify(build_api_response([result], page=1, limit=limit or 1, total_count=1)), 200
            except Exception as e:
                return jsonify({"success": False, "error": str(e)}), 500

        # Multiple paths or directory
        items = []
        if target_dir and os.path.isdir(target_dir):
            for fname in os.listdir(target_dir):
                if fname.lower().endswith(".pdf") and not fname.startswith("."):
                    items.append(os.path.join(target_dir, fname))
        elif paths:
            items = [p for p in paths if os.path.isfile(p)]

        if items:
            stats = convert_batch_parallel(items=items, workers=custom_workers)
            all_results = stats.get("results", [])
            total_count = len(all_results)

            if limit and limit > 0:
                start_idx = (page - 1) * limit
                end_idx = start_idx + limit
                paginated_data = all_results[start_idx:end_idx]
            else:
                paginated_data = all_results

            return jsonify(build_api_response(
                data_list=paginated_data,
                page=page,
                limit=limit or total_count,
                total_count=total_count
            )), 200

        return jsonify({"success": False, "error": "No valid PDF files found in path, paths, or directory"}), 400

    return jsonify({
        "success": False,
        "error": "Attach PDF file(s) in form-data under 'file' or 'files', or send JSON with 'path'/'directory'"
    }), 400

@app.route("/api/sample/<name>", methods=["GET"])
def sample_test(name):
    """Convenience endpoint to test sample tracking documents."""
    sample_filename = f"{name}.pdf" if not name.endswith(".pdf") else name
    sample_path = os.path.join(SAMPLES_DIR, sample_filename)

    if not os.path.isfile(sample_path):
        return jsonify({"success": False, "error": f"Sample {sample_filename} not found"}), 404

    try:
        result = parse_tracking_pdf(sample_path)
        return jsonify(build_api_response([result], page=1, limit=1, total_count=1)), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    print(f"\n🚀 FileToJSON API Server running at http://{HOST}:{PORT}/")
    print(f"• Workers: {DEFAULT_WORKERS}")
    print(f"• Ready for Postman & curl requests (Single, Multi-file, & Pagination enabled)\n")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
