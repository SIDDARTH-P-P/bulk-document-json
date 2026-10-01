"""
Flask REST API Server for FileToJSON.
Handles single and multi-file uploads (1 to 1,000+ files).
Supports pagination: ?limit=1&page=1, as well as URL typos like &limit=1.
Preserves key order: success, pagination, data.
"""

import json
import os
import socket
import urllib.parse
from datetime import datetime, timezone
from flask import Flask, request, jsonify, Response
from pymongo import MongoClient
from parsers import parse_tracking_pdf
from engine import convert_batch_parallel
from config import HOST, PORT, DEFAULT_WORKERS, MAX_CONTENT_LENGTH, MONGO_URI, MONGO_DB, MONGO_COLLECTION

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.json.sort_keys = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_mongo_collection():
    """Return a Mongo client and collection pair, or (None, None) when unavailable."""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        db = client[MONGO_DB]
        return client, db[MONGO_COLLECTION]
    except Exception:
        return None, None


def persist_extracted_document(document):
    """Save a parsed document to MongoDB."""
    if not isinstance(document, dict):
        return None

    source_name = document.get("source_file") or ""
    client, collection = get_mongo_collection()
    if collection is None:
        return None

    doc_to_store = dict(document)
    doc_to_store["created_at"] = datetime.now(timezone.utc).isoformat()

    try:
        filter_query = {}
        if doc_to_store.get("consignment_number"):
            filter_query["consignment_number"] = doc_to_store["consignment_number"]
        elif source_name:
            filter_query["source_file"] = source_name

        if filter_query:
            if collection.find_one(filter_query):
                collection.update_one(filter_query, {"$set": doc_to_store})
            else:
                collection.insert_one(doc_to_store)
        else:
            collection.insert_one(doc_to_store)
    except Exception:
        return None
    finally:
        if client is not None and hasattr(client, "close"):
            client.close()

    return doc_to_store

def get_available_port(start_port=PORT):
    """Return the first free port, starting from the configured default."""
    port = int(start_port)
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((HOST, port))
                return port
            except OSError:
                port += 1


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


def build_openapi_spec():
    """Generate a live OpenAPI 3.0 document from the current Flask routes."""
    paths = {}

    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if rule.endpoint == "static":
            continue

        methods = sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"})
        if not methods:
            continue

        path = rule.rule
        path_entry = {}
        for method in methods:
            lower_method = method.lower()
            summary = f"{method.upper()} {path}"
            description = "Endpoint for the FileToJSON PDF to JSON converter API."

            if path == "/health":
                description = "Health check endpoint returning the service status and the available routes."
            elif path.startswith("/api/get") or path.startswith("/api/documents") or path.startswith("/api/list"):
                description = "Return saved extracted documents from MongoDB. Supports pagination with page and limit."
            elif path.startswith("/api/convert") or path == "/api/add":
                description = "Convert uploaded or local PDF files into structured JSON and optionally save them to MongoDB."

            operation = {
                "summary": summary,
                "description": description,
                "responses": {
                    "200": {"description": "Successful response"},
                    "400": {"description": "Bad request or no valid PDFs were provided"},
                    "500": {"description": "Parsing or conversion error"}
                },
                "parameters": []
            }

            if path.startswith("/api"):
                operation["parameters"].append({
                    "name": "page",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "default": 1}
                })
                operation["parameters"].append({
                    "name": "limit",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "default": 10}
                })
                operation["parameters"].append({
                    "name": "workers",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "default": 8}
                })

            if method in {"POST", "PUT", "PATCH"}:
                operation["requestBody"] = {
                    "required": False,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "file": {"type": "string", "format": "binary"},
                                    "files": {"type": "array", "items": {"type": "string", "format": "binary"}},
                                    "path": {"type": "string", "description": "Single PDF file path"},
                                    "paths": {"type": "array", "items": {"type": "string"}},
                                    "directory": {"type": "string", "description": "Folder containing PDFs"}
                                }
                            }
                        },
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "paths": {"type": "array", "items": {"type": "string"}},
                                    "directory": {"type": "string"},
                                    "workers": {"type": "integer"}
                                }
                            }
                        }
                    }
                }

            path_entry[lower_method] = operation

        if path_entry:
            paths[path] = path_entry

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "FileToJSON API",
            "version": "1.0.0",
            "description": "API for converting PDF tracking documents into structured JSON and saving results to MongoDB."
        },
        "servers": [{"url": "/", "description": "Current service"}],
        "paths": paths,
        "tags": [{
            "name": "Files",
            "description": "PDF conversion and extraction endpoints"
        }, {
            "name": "MongoDB",
            "description": "Saved document retrieval endpoints"
        }]
    }


@app.route("/openapi.json", methods=["GET"])
def openapi_json():
    """Expose the generated OpenAPI specification for Swagger UI."""
    spec = json.dumps(build_openapi_spec(), indent=2, ensure_ascii=False)
    return Response(spec, mimetype="application/json")


@app.route("/swagger", methods=["GET"])
def swagger_ui():
    """Serve the Swagger UI page for the API documentation."""
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>FileToJSON Swagger</title>
      <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css" />
      <style>
        body { margin: 0; background: #f5f7fb; }
        #swagger-ui { max-width: 1200px; margin: 20px auto; }
      </style>
    </head>
    <body>
      <div id="swagger-ui"></div>
      <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
      <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-standalone-preset.js"></script>
      <script>
        window.onload = () => {
          if (window.SwaggerUIBundle && window.SwaggerUIStandalonePreset) {
            SwaggerUIBundle({
              url: '/openapi.json',
              dom_id: '#swagger-ui',
              deepLinking: true,
              presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
              layout: 'BaseLayout',
              docExpansion: 'list',
              defaultModelsExpandDepth: 1,
              persistAuthorization: true
            });
          } else {
            document.querySelector('#swagger-ui').innerHTML = '<h2>Swagger UI failed to load.</h2>';
          }
        };
      </script>
    </body>
    </html>
    """
    return html


@app.route("/api/add", methods=["POST"])
@app.route("/api/add&<path:extra>", methods=["POST"])
def add_document(extra=""):
    """Alias for extraction that stores the parsed result in MongoDB."""
    return convert_documents(extra)


@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint showing service status and available endpoints."""
    return jsonify({
        "success": True,
        "service": "FileToJSON — Tracking PDF to JSON Converter API",
        "endpoints": {
            "POST /api/convert": "Convert 1 or multiple PDF files and save them to MongoDB",
            "POST /api/convert-batch": "Convert many PDFs and save them to MongoDB",
            "POST /api/add": "Alias for extraction + save to MongoDB",
            "GET /api/get": "List saved documents from MongoDB",
            "GET /api/documents": "List saved documents from MongoDB",
            "GET /api/list": "List saved documents from MongoDB",
            "GET /swagger": "Swagger UI documentation page",
            "GET /openapi.json": "Machine-readable OpenAPI 3.0 spec"
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

    def finalize_results(results):
        persisted = []
        for item in results:
            if not isinstance(item, dict):
                continue
            record = persist_extracted_document(item)
            if record is not None:
                persisted.append(record)
        return persisted

    # 1. Process Multipart Form-Data (supports 1, 2, or 1000+ files)
    uploaded_files = get_all_uploaded_files()
    if uploaded_files:
        if len(uploaded_files) == 1 and (limit is None or limit >= 1):
            f = uploaded_files[0]
            try:
                result = parse_tracking_pdf(f.read(), filename=f.filename)
                persist_extracted_document(result)
                return jsonify(build_api_response([result], page=1, limit=limit or 1, total_count=1)), 200
            except Exception as e:
                return jsonify({"success": False, "error": str(e)}), 500
        else:
            items = [(f.filename, f.read()) for f in uploaded_files]
            stats = convert_batch_parallel(items=items, workers=workers)
            all_results = stats.get("results", [])
            persisted_results = finalize_results(all_results)
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
                persist_extracted_document(result)
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
            finalize_results(all_results)
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

@app.route("/api/get", methods=["GET"])
@app.route("/api/documents", methods=["GET"])
@app.route("/api/list", methods=["GET"])
def get_saved_documents():
    """Return all saved tracking documents stored in MongoDB."""
    page, limit = get_pagination_params()
    client, collection = get_mongo_collection()

    if collection is None:
        return jsonify({"success": False, "error": "MongoDB is not available. Start MongoDB or set MONGO_URI."}), 503

    try:
        cursor = collection.find({}, {"_id": 0})
        if hasattr(cursor, "sort"):
            try:
                cursor = cursor.sort("created_at", -1)
            except TypeError:
                cursor = sorted(cursor, key=lambda item: item.get("created_at", ""), reverse=True)

        records = list(cursor)
    except Exception:
        return jsonify({"success": False, "error": "MongoDB is not available. Start MongoDB or set MONGO_URI."}), 503
    finally:
        if client is not None and hasattr(client, "close"):
            client.close()

    total_count = len(records)

    if limit and limit > 0:
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_data = records[start_idx:end_idx]
    else:
        paginated_data = records

    return jsonify(build_api_response(
        data_list=paginated_data,
        page=page,
        limit=limit or total_count or 1,
        total_count=total_count
    )), 200


if __name__ == "__main__":
    runtime_port = get_available_port(PORT)
    print(f"\n🚀 FileToJSON API Server running at http://{HOST}:{runtime_port}/")
    print(f"• Workers: {DEFAULT_WORKERS}")
    print(f"• Swagger: http://{HOST}:{runtime_port}/swagger")
    print(f"• OpenAPI: http://{HOST}:{runtime_port}/openapi.json")
    print(f"• Ready for Postman & curl requests (Single, Multi-file, & Pagination enabled)\n")
    app.run(host=HOST, port=runtime_port, debug=False, threaded=True)
