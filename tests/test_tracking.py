"""
Unit tests for FileToJSON tracking parser and batch engine.
"""

import os
import unittest
from parsers import parse_tracking_pdf
from engine import convert_batch_parallel

class TestTrackingParser(unittest.TestCase):
    def setUp(self):
        self.samples_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")
        self.trk1_path = os.path.join(self.samples_dir, "trk1.pdf")
        self.trk2_path = os.path.join(self.samples_dir, "trk2.pdf")

    def test_trk1(self):
        if not os.path.exists(self.trk1_path):
            self.skipTest("trk1.pdf not found")

        data = parse_tracking_pdf(self.trk1_path)
        self.assertEqual(data["consignment_number"], "QM122475425IN")
        self.assertEqual(data["article_type"], "SP_INLAND_DOC")
        self.assertEqual(data["tariff"], "₹55")
        self.assertEqual(data["booked_at"], "Vashi BPC")
        self.assertEqual(data["destination_pincode"], "530016")
        self.assertTrue(data["is_returned_to_sender"])
        self.assertEqual(data["return_reason"], "Refused")
        self.assertEqual(data["delivery_status"], "Returned to Sender (Refused)")
        self.assertEqual(len(data["routing_steps"]), 31)

    def test_trk2(self):
        if not os.path.exists(self.trk2_path):
            self.skipTest("trk2.pdf not found")

        data = parse_tracking_pdf(self.trk2_path)
        self.assertEqual(data["consignment_number"], "QM122476960IN")
        self.assertEqual(data["destination_pincode"], "700015")
        self.assertTrue(data["is_returned_to_sender"])
        self.assertEqual(data["return_reason"], "No such person in the address")
        self.assertEqual(len(data["routing_steps"]), 22)

    def test_in_memory_bytes(self):
        if not os.path.exists(self.trk1_path):
            self.skipTest("trk1.pdf not found")

        with open(self.trk1_path, "rb") as f:
            content = f.read()

        data = parse_tracking_pdf(content, filename="upload_trk1.pdf")
        self.assertEqual(data["consignment_number"], "QM122475425IN")
        self.assertEqual(data["source_file"], "upload_trk1.pdf")

    def test_batch_parallel(self):
        files = [f for f in [self.trk1_path, self.trk2_path] if os.path.exists(f)]
        stats = convert_batch_parallel(files, workers=4)
        self.assertEqual(stats["total"], len(files))
        self.assertEqual(stats["failed"], 0)
        self.assertEqual(len(stats["results"]), len(files))

if __name__ == "__main__":
    unittest.main()
