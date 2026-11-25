import hashlib
import unittest
from unittest.mock import patch
from fetch_private_zip import (PINNED_CANDIDATE_ID, PINNED_CANDIDATE_SHA256,
                               APPROVED_READONLY_ARCHIVES, verify_pinned_candidate, download)


class PinnedArchiveContract(unittest.TestCase):
    def test_exact_owner_verified_candidate_identity(self):
        self.assertEqual(APPROVED_READONLY_ARCHIVES[PINNED_CANDIDATE_ID],
                         ('market_candidate_HOLD_2026-11-24_GH45533778910.zip', 2151240))
        self.assertEqual(PINNED_CANDIDATE_SHA256,
                         '62b08e06a84caef53889f17bf75afde5bb2d2cd01e9adc5c6433b9c2e7c89722')

    def test_hash_and_size_pin(self):
        with patch('fetch_private_zip.PINNED_CANDIDATE_BYTES',3), \
             patch('fetch_private_zip.PINNED_CANDIDATE_SHA256',hashlib.sha256(b'zip').hexdigest()):
            verify_pinned_candidate(PINNED_CANDIDATE_ID,b'zip')
            for changed in (b'zop',b'zip!'):
                with self.assertRaisesRegex(RuntimeError,'PINNED_CANDIDATE_BYTES_MISMATCH'):
                    verify_pinned_candidate(PINNED_CANDIDATE_ID,changed)

    def test_unknown_id_rejected_before_network(self):
        with self.assertRaisesRegex(ValueError,'UNAPPROVED_DRIVE_FILE'):
            download('unapproved_id','unused')


if __name__=='__main__':unittest.main()
