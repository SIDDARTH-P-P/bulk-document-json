"""
API route tests for Flask endpoints:
- Multi-file upload under key 'file'
- Standard query params ?limit=1
- URL typo format &limit=1
- Key order preservation (success, pagination, data)
"""

import io
import os
import unittest
from unittest.mock import patch
from app import app

class TestAPIEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.samples_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")
        self.trk1_path = os.path.join(self.samples_dir, "trk1.pdf")
        self.trk2_path = os.path.join(self.samples_dir, "trk2.pdf")

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        json_data = resp.get_json()
        self.assertTrue(json_data["success"])

    def test_convert_multi_file_and_pagination(self):
        with open(self.trk1_path, "rb") as f1, open(self.trk2_path, "rb") as f2:
            data = {
                "file": [
                    (io.BytesIO(f1.read()), "trk1.pdf"),
                    (io.BytesIO(f2.read()), "trk2.pdf")
                ]
            }
            # Standard query string ?limit=1
            resp = self.client.post("/api/convert?limit=1", data=data, content_type="multipart/form-data")
            self.assertEqual(resp.status_code, 200)
            res = resp.get_json()
            self.assertTrue(res["success"])
            self.assertEqual(res["pagination"]["limit"], 1)
            self.assertEqual(res["pagination"]["totalCount"], 2)
            self.assertEqual(len(res["data"]), 1)

    def test_convert_typo_ampersand_limit(self):
        with open(self.trk1_path, "rb") as f1, open(self.trk2_path, "rb") as f2:
            data = {
                "file": [
                    (io.BytesIO(f1.read()), "trk1.pdf"),
                    (io.BytesIO(f2.read()), "trk2.pdf")
                ]
            }
            # URL typo &limit=1
            resp = self.client.post("/api/convert&limit=1", data=data, content_type="multipart/form-data")
            self.assertEqual(resp.status_code, 200)
            res = resp.get_json()
            self.assertTrue(res["success"])
            self.assertEqual(res["pagination"]["limit"], 1)
            self.assertEqual(res["pagination"]["totalCount"], 2)
            self.assertEqual(len(res["data"]), 1)

    def test_get_saved_documents(self):
        with patch("app.get_mongo_collection") as mongo_collection:
            mock_client = object()
            mock_collection = type("MockCollection", (), {})()
            mock_collection.find = lambda *args, **kwargs: [
                {"consignment_number": "QM122475425IN"},
                {"consignment_number": "QM122476960IN"},
            ]
            mongo_collection.return_value = (mock_client, mock_collection)

            resp = self.client.get("/api/get")
            self.assertEqual(resp.status_code, 200)
            res = resp.get_json()
            self.assertTrue(res["success"])
            self.assertEqual(len(res["data"]), 2)

if __name__ == "__main__":
    unittest.main()
