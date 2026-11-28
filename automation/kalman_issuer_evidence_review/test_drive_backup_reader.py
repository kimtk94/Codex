import base64
import hashlib
import json
import unittest
from unittest.mock import patch, Mock
import drive_backup_reader as d

class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {"id":d.FILE_ID,"name":d.FILE_NAME,"mimeType":"application/zip",
                         "size":str(d.FILE_SIZE),"trashed":False}
        self.identity = {"type":"service_account","client_email":d.ACCOUNT}
    def test_exact_identity(self):
        self.assertEqual(d.validate_identity({"CKD_DRIVE_SA_JSON":json.dumps(self.identity)}),self.identity)
    def test_encoded_identity(self):
        encoded = base64.b64encode(json.dumps(self.identity).encode()).decode()
        self.assertEqual(d.validate_identity({"GDRIVE_SA_JSON_B64":encoded}),self.identity)
    def test_wrong_identity(self):
        with self.assertRaisesRegex(ValueError,"IDENTITY_MISMATCH"):
            d.validate_identity({"CKD_DRIVE_SA_JSON":json.dumps({"type":"service_account","client_email":"other"})})
    def test_missing_identity(self):
        with self.assertRaisesRegex(ValueError,"CREDENTIAL_MISSING"):
            d.validate_identity({})
    def test_exact_metadata(self):
        d.validate_metadata(self.metadata)
    def test_wrong_metadata(self):
        for key, value in [("id","wrong"),("name","wrong"),("size","0"),("trashed",True),("mimeType","text/plain")]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError,"TARGET_METADATA_MISMATCH"):
                d.validate_metadata({**self.metadata,key:value})
    def test_wrong_blob(self):
        with self.assertRaisesRegex(ValueError,"BACKUP_PIN_MISMATCH"):
            d.verify_blob(b"not archive")
    def test_bounded_buffer(self):
        with patch.object(d,"FILE_SIZE",3):
            stream=d.BoundedBuffer()
            stream.write(b"abc")
            with self.assertRaisesRegex(ValueError,"DOWNLOAD_OVERSIZE"):
                stream.write(b"d")
    def test_read_only_download(self):
        blob=b"abc"
        service=Mock()
        files=service.files.return_value
        files.get.return_value.execute.return_value={**self.metadata,"size":"3"}
        class Downloader:
            def __init__(self,stream,req,**kw): self.stream=stream
            def next_chunk(self,**kw):
                self.stream.write(blob)
                return None,True
        with patch.object(d,"FILE_SIZE",3),patch.object(d,"PRIOR_PIN",hashlib.sha256(blob).hexdigest()):
            self.assertEqual(d.download(service,Downloader),blob)
        files.get.assert_called_once()
        files.get_media.assert_called_once()
        files.update.assert_not_called()
        files.create.assert_not_called()
    def test_metadata_failure_before_media(self):
        service=Mock()
        service.files.return_value.get.return_value.execute.return_value={}
        with self.assertRaisesRegex(ValueError,"TARGET_METADATA_MISMATCH"):
            d.download(service,Mock())
        service.files.return_value.get_media.assert_not_called()
    def test_readonly_scope(self):
        self.assertEqual(d.SCOPE,"https://www.googleapis.com/auth/drive.readonly")

if __name__ == "__main__":
    unittest.main()
