"""Flask REST API Server for FileToJSON."""

import io
import json
import os
import socket
import urllib.parse
import zipfile
from datetime import datetime, timezone

from bson.objectid import ObjectId
from flask import Flask, Response, jsonify, request
from pymongo import MongoClient

from config import (
    DEFAULT_WORKERS,
    HOST,
    MAX_CONTENT_LENGTH,
    MONGO_COLLECTION,
    MONGO_DB,
    MONGO_URI,
    PORT,
)
from engine import convert_batch_parallel
from parsers import parse_tracking_pdf

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
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

    client, collection = get_mongo_collection()
    if collection is None:
        return None

    doc_to_store = dict(document)
    doc_to_store["created_at"] = datetime.now(timezone.utc).isoformat()

    try:
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
    """Extract page and limit from query params, typoed URLs, form-data, or JSON payloads."""
    page = request.args.get("page", type=int)
    limit = request.args.get("limit", type=int)

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
    """Wrap the result in the standard { success, pagination, data } format."""
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
            "totalCount": total,
        },
        "data": data_list,
    }


def build_filter_from_request(payload=None, allow_empty=False):
    """Build a Mongo filter from payload JSON and query-string values."""
    filters = {}
    data = payload or {}

    if isinstance(data, dict):
        candidate = data.get("query") or data.get("filter") or data.get("conditions") or {}
        if isinstance(candidate, dict):
            filters.update(candidate)

        if data.get("all") is True or data.get("delete_all") is True or data.get("update_all") is True:
            return {}

        for key in [
            "id",
            "_id",
            "consignment_number",
            "source_file",
            "status",
            "delivery_status",
            "article_type",
            "tariff",
            "return_reason",
        ]:
            if key in data and data[key] not in (None, ""):
                filters[key] = data[key]

    for key, value in request.args.items():
        if key in {"page", "limit", "workers"}:
            continue
        if value not in (None, ""):
            filters[key] = value

    if not filters and not allow_empty:
        return {}
    return filters


def resolve_object_id(value):
    """Normalize a Mongo ObjectId or a string into a filter value."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return ObjectId(value)
        except Exception:
            return value
    return value


def get_all_uploaded_files():
    """Extracts all uploaded files from form-data regardless of field name."""
    uploaded = []
    for key in request.files:
        for f in request.files.getlist(key):
            if f and f.filename:
                uploaded.append(f)
    return uploaded


def extract_pdf_files_from_zip(zip_bytes):
    """Return PDF byte streams from a ZIP archive."""
    pdf_items = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in sorted(zf.namelist()):
            if name.lower().endswith(".pdf"):
                pdf_items.append((name, zf.read(name)))
    return pdf_items


def normalise_pdf_items(file_objects):
    """Flatten single files, zip uploads, and direct paths into a list of (filename, bytes)."""
    items = []
    for f in file_objects:
        if not f or not getattr(f, "filename", None):
            continue
        name = str(f.filename).lower()
        if name.endswith(".zip"):
            items.extend(extract_pdf_files_from_zip(f.read()))
        elif name.endswith(".pdf"):
            items.append((f.filename, f.read()))
    return items


def build_openapi_spec():
    """Generate a live OpenAPI 3.0 document from the current Flask routes."""
    paths = {}
    hidden_routes = {
        "/",
        "/health",
        "/swagger",
        "/openapi.json",
        "/api/add",
        "/api/getfromdb",
        "/api/get-from-db",
    }

    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if rule.endpoint == "static" or rule.rule in hidden_routes:
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

            if path.startswith("/api/get"):
                description = "Return saved extracted documents from MongoDB. Supports pagination with page and limit."
            elif path.startswith("/api/convert"):
                description = "Convert uploaded or local PDF files into structured JSON and save them to MongoDB."
            elif path.startswith("/api/delete"):
                description = "Delete one or multiple MongoDB records by filter or by document id."
            elif path.startswith("/api/update"):
                description = "Update one or multiple MongoDB records by filter or by document id."

            operation = {
                "summary": summary,
                "description": description,
                "responses": {
                    "200": {"description": "Successful response"},
                    "400": {"description": "Bad request"},
                    "404": {"description": "Document not found or no match"},
                    "500": {"description": "Parsing or conversion error"},
                },
                "parameters": [],
            }

            if path.startswith("/api"):
                operation["parameters"].append({
                    "name": "page",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "default": 1},
                })
                operation["parameters"].append({
                    "name": "limit",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "default": 10},
                })
                operation["parameters"].append({
                    "name": "workers",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "default": 8},
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
                                    "path": {"type": "string"},
                                    "paths": {"type": "array", "items": {"type": "string"}},
                                    "directory": {"type": "string"},
                                },
                            }
                        },
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "paths": {"type": "array", "items": {"type": "string"}},
                                    "directory": {"type": "string"},
                                    "workers": {"type": "integer"},
                                },
                            }
                        },
                    },
                }

            path_entry[lower_method] = operation

        if path_entry:
            paths[path] = path_entry

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "FileToJSON API",
            "version": "1.0.0",
            "description": "PDF-to-JSON converter with MongoDB persistence and document management operations.",
        },
        "servers": [{"url": "/", "description": "Current service"}],
        "paths": paths,
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


@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint showing service status and available endpoints."""
    return jsonify({
        "success": True,
        "service": "FileToJSON — Tracking PDF to JSON Converter API",
        "endpoints": {
            "POST /api/convert": "Upload a single PDF, multiple PDFs, or a ZIP archive and save all extracted records to MongoDB",
            "GET /api/get": "Fetch stored documents from MongoDB with optional filters",
            "GET /api/getfromdb": "Compatibility alias for fetching documents from MongoDB",
            "PUT /api/update": "Update one or many documents by condition or all documents",
            "PUT /api/update-all": "Update every document in MongoDB",
            "DELETE /api/delete": "Delete one or many documents by condition or all documents",
            "DELETE /api/delete-all": "Delete every document from MongoDB",
        },
    }), 200


@app.route("/api/convert", methods=["POST"])
def convert_documents_route():
    """Convert single PDF, multiple PDFs, or ZIP uploads into JSON and save to MongoDB."""
    workers = request.args.get("workers", type=int) or DEFAULT_WORKERS
    page, limit = get_pagination_params()

    def finalize_results(results):
        persisted = []
        for item in results:
            if not isinstance(item, dict):
                continue
            record = persist_extracted_document(item)
            if record is not None:
                persisted.append(record)
        return persisted

    uploaded_files = get_all_uploaded_files()
    if uploaded_files:
        items = normalise_pdf_items(uploaded_files)
        if not items:
            return jsonify({"success": False, "error": "No valid PDF or ZIP files found in upload"}), 400

        if len(items) == 1 and (limit is None or limit >= 1):
            try:
                filename, content = items[0]
                result = parse_tracking_pdf(content, filename=filename)
                persist_extracted_document(result)
                return jsonify(build_api_response([result], page=1, limit=limit or 1, total_count=1)), 200
            except Exception as exc:
                return jsonify({"success": False, "error": str(exc)}), 500

        try:
            stats = convert_batch_parallel(items=items, workers=workers)
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

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
            total_count=total_count,
        )), 200

    if request.is_json:
        payload = request.get_json() or {}
        single_path = payload.get("path")
        paths = payload.get("paths", [])
        target_dir = payload.get("directory")
        zip_path = payload.get("zip_path")
        custom_workers = payload.get("workers", workers)

        items = []
        if single_path and os.path.isfile(single_path):
            if single_path.lower().endswith(".zip"):
                items = extract_pdf_files_from_zip(open(single_path, "rb").read())
            elif single_path.lower().endswith(".pdf"):
                items = [(os.path.basename(single_path), open(single_path, "rb").read())]
        elif zip_path and os.path.isfile(zip_path):
            items = extract_pdf_files_from_zip(open(zip_path, "rb").read())
        elif target_dir and os.path.isdir(target_dir):
            for fname in os.listdir(target_dir):
                path = os.path.join(target_dir, fname)
                if fname.lower().endswith(".pdf") and os.path.isfile(path):
                    items.append((fname, open(path, "rb").read()))
                elif fname.lower().endswith(".zip") and os.path.isfile(path):
                    items.extend(extract_pdf_files_from_zip(open(path, "rb").read()))
        elif paths:
            for p in paths:
                if not os.path.isfile(p):
                    continue
                if p.lower().endswith(".zip"):
                    items.extend(extract_pdf_files_from_zip(open(p, "rb").read()))
                elif p.lower().endswith(".pdf"):
                    items.append((os.path.basename(p), open(p, "rb").read()))

        if not items:
            return jsonify({"success": False, "error": "No valid PDF or ZIP files found in path, paths, directory, or zip_path"}), 400

        if len(items) == 1 and (limit is None or limit >= 1):
            try:
                filename, content = items[0]
                result = parse_tracking_pdf(content, filename=filename)
                persist_extracted_document(result)
                return jsonify(build_api_response([result], page=1, limit=limit or 1, total_count=1)), 200
            except Exception as exc:
                return jsonify({"success": False, "error": str(exc)}), 500

        try:
            stats = convert_batch_parallel(items=items, workers=custom_workers)
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

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
            total_count=total_count,
        )), 200

    return jsonify({
        "success": False,
        "error": "Attach PDF or ZIP file(s) in form-data under 'file'/'files'/'zip', or send JSON with 'path'/'paths'/'directory'/'zip_path'",
    }), 400


@app.route("/api/get", methods=["GET"])
@app.route("/api/getfromdb", methods=["GET"])
@app.route("/api/get-from-db", methods=["GET"])
def get_saved_documents():
    """Return all saved tracking documents stored in MongoDB."""
    page, limit = get_pagination_params()
    payload = request.get_json(silent=True) or {}
    filters = build_filter_from_request(payload) if isinstance(payload, dict) else {}
    if not filters and request.args:
        filters = build_filter_from_request({})

    client, collection = get_mongo_collection()
    if collection is None:
        return jsonify({"success": False, "error": "MongoDB is not available. Start MongoDB or set MONGO_URI."}), 503

    try:
        cursor = collection.find(filters, {"_id": 0})
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
        total_count=total_count,
    )), 200


@app.route("/api/delete", methods=["DELETE"])
@app.route("/api/delete-all", methods=["DELETE"])
@app.route("/api/deleteall", methods=["DELETE"])
@app.route("/api/delete/<document_id>", methods=["DELETE"])
def delete_document(document_id=None):
    """Delete one document, many documents by condition, or all documents when requested."""
    payload = request.get_json(silent=True) or {}
    filters = build_filter_from_request(payload, allow_empty=True)

    if document_id is not None:
        filters = {"_id": resolve_object_id(document_id)}
    elif request.args.get("all") == "true" or request.args.get("delete_all") == "true":
        filters = {}
    elif payload.get("all") is True or payload.get("delete_all") is True or payload.get("deleteAll") is True:
        filters = {}
    elif request.path.endswith("/delete-all") or request.path.endswith("/deleteall"):
        filters = {}

    if not filters and not (request.args.get("all") == "true" or request.args.get("delete_all") == "true") and not payload and not (request.path.endswith("/delete-all") or request.path.endswith("/deleteall")):
        return jsonify({"success": False, "error": "Provide an id, a filter, or set all=true to delete all documents"}), 400

    client, collection = get_mongo_collection()
    if collection is None:
        return jsonify({"success": False, "error": "MongoDB is not available. Start MongoDB or set MONGO_URI."}), 503

    try:
        if not filters:
            result = collection.delete_many({})
        else:
            result = collection.delete_many(filters)
        return jsonify({"success": True, "deleted_count": result.deleted_count, "filter": filters}), 200
    finally:
        if client is not None and hasattr(client, "close"):
            client.close()


@app.route("/api/update", methods=["PUT"])
@app.route("/api/update-all", methods=["PUT"])
@app.route("/api/updateall", methods=["PUT"])
@app.route("/api/update/<document_id>", methods=["PUT"])
def update_document(document_id=None):
    """Update one or more documents by condition, or all documents when requested."""
    payload = request.get_json(silent=True) or {}
    if not payload and not request.args:
        return jsonify({"success": False, "error": "JSON body required"}), 400

    filters = build_filter_from_request(payload, allow_empty=True)
    if document_id is not None:
        filters = {"_id": resolve_object_id(document_id)}
    elif request.path.endswith("/update-all") or request.path.endswith("/updateall"):
        filters = {}

    update_values = payload.get("data") or payload.get("set") or payload.get("update") or payload
    if document_id is None and not filters:
        search_key = payload.get("consignment_number") or payload.get("source_file") or payload.get("status")
        if search_key:
            if payload.get("consignment_number"):
                filters = {"consignment_number": payload["consignment_number"]}
            elif payload.get("source_file"):
                filters = {"source_file": payload["source_file"]}
            elif payload.get("status"):
                filters = {"status": payload["status"]}
        else:
            return jsonify({"success": False, "error": "Provide an id, consignment_number, source_file, status, or set all=true/update_all=true"}), 400

    if payload.get("all") is True or payload.get("update_all") is True or request.args.get("all") == "true":
        filters = {}
    if request.path.endswith("/update-all") or request.path.endswith("/updateall"):
        filters = {}

    if isinstance(update_values, dict):
        update_values = {
            key: value
            for key, value in update_values.items()
            if key not in {"all", "update_all", "delete_all", "query", "filter", "conditions", "id", "_id"}
        }
    else:
        return jsonify({"success": False, "error": "Update payload must be an object"}), 400

    if not update_values:
        return jsonify({"success": False, "error": "No fields were provided to update"}), 400

    client, collection = get_mongo_collection()
    if collection is None:
        return jsonify({"success": False, "error": "MongoDB is not available. Start MongoDB or set MONGO_URI."}), 503

    try:
        if not filters:
            result = collection.update_many({}, {"$set": update_values})
            return jsonify({"success": True, "updated": True, "modified_count": result.modified_count, "filter": filters, "data": update_values}), 200

        result = collection.update_many(filters, {"$set": update_values})
        if result.matched_count == 0:
            raise ValueError("No documents matched the provided condition")
        return jsonify({"success": True, "updated": True, "matched_count": result.matched_count, "modified_count": result.modified_count, "filter": filters, "data": update_values}), 200
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    finally:
        if client is not None and hasattr(client, "close"):
            client.close()


if __name__ == "__main__":
    runtime_port = get_available_port(PORT)
    print(f"\n🚀 FileToJSON API Server running at http://{HOST}:{runtime_port}/")
    print(f"• Workers: {DEFAULT_WORKERS}")
    print(f"• Swagger: http://{HOST}:{runtime_port}/swagger")
    print(f"• OpenAPI: http://{HOST}:{runtime_port}/openapi.json")
    print(f"• Ready for Postman & curl requests (Single, Multi-file, & Pagination enabled)\n")
    app.run(host=HOST, port=runtime_port, debug=False, threaded=True)
