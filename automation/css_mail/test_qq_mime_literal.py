#!/usr/bin/env python3
"""Regression: QQ IMAP returns long filename as tuple second element."""
import unittest
from tax_invoice_extract import imap_bodystructure_chunks,bodystructure_filenames,extract

class QQMimeTest(unittest.TestCase):
    def test_literal_payload(self):
        filename=b"TAX INVOICE-209126000964-H209SC26088039-SQ-AMEA2026073124-KRW4438500.00.pdf"
        response=[(b'9 (BODYSTRUCTURE (("APPLICATION" "PDF" ("NAME" {75}',filename),
                  (b' "ATTACHMENT" ("FILENAME" {75}',filename),b'))']
        chunks=imap_bodystructure_chunks(response)
        self.assertIn(filename,chunks)
        names=[n for chunk in chunks for n in bodystructure_filenames(chunk)]
        self.assertIn(filename.decode(),names)
        self.assertEqual(extract(filename.decode())[4],4438500)

if __name__=="__main__":unittest.main()
