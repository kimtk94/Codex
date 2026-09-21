from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE_BUILDER = ROOT / "kalman-toss-gateway/scripts/build_investment_hub_v7431_etf_display_price.py"
BASE_MANIFEST = ROOT / "kalman-hub-recovery/v7.4.31/source_manifest.ndjson"
OUT_DIR = ROOT / "kalman-hub-recovery/v7.4.32"
TARGET = "vNext.7.4.32"
API_REPLACEMENT_B64 = "ICBjb25zdCBfX2thbG1hblVybCA9IG5ldyBVUkwocmVxLnVybCB8fCAnL2FwaS9kYXNoYm9hcmQnLCAnaHR0cDovL2xvY2FsaG9zdCcpOwogIGlmICgoX19rYWxtYW5Vcmwuc2VhcmNoUGFyYW1zLmdldCgnbWFya2V0JykgfHwgJycpLnRvVXBwZXJDYXNlKCkgPT09ICdTSEFET1cnKSB7CiAgICByZXMuc2V0SGVhZGVyKCdDYWNoZS1Db250cm9sJywnbm8tc3RvcmUnKTsKICAgIHJlcy5zZXRIZWFkZXIoJ0NvbnRlbnQtVHlwZScsJ2FwcGxpY2F0aW9uL2pzb247IGNoYXJzZXQ9dXRmLTgnKTsKICAgIGlmKHJlcS5tZXRob2QhPT0nR0VUJylyZXR1cm4gcmVzLnN0YXR1cyg0MDUpLmpzb24oe2Vycm9yOidNRVRIT0RfTk9UX0FMTE9XRUQnfSk7CiAgICBjb25zdCBsZWdhY3lVcmw9J2h0dHBzOi8va2FsbWFuLXNoYWRvdy1yZWFkb25seS52ZXJjZWwuYXBwL2FwaS9zaGFkb3cnOwogICAgYXN5bmMgZnVuY3Rpb24gbGVnYWN5U2hhZG93KCl7CiAgICAgIGNvbnN0IGM9bmV3IEFib3J0Q29udHJvbGxlcigpLHRpbWVyPXNldFRpbWVvdXQoKCk9PmMuYWJvcnQoKSw4MDAwKTsKICAgICAgdHJ5ewogICAgICAgIGNvbnN0IHI9YXdhaXQgZmV0Y2gobGVnYWN5VXJsLHtoZWFkZXJzOntBY2NlcHQ6J2FwcGxpY2F0aW9uL2pzb24nfSxjYWNoZTonbm8tc3RvcmUnLHNpZ25hbDpjLnNpZ25hbH0pOwogICAgICAgIGlmKCFyLm9rKXRocm93IG5ldyBFcnJvcignTEVHQUNZX1NIQURPV19IVFRQXycrci5zdGF0dXMpOwogICAgICAgIHJldHVybiBhd2FpdCByLmpzb24oKTsKICAgICAgfWZpbmFsbHl7Y2xlYXJUaW1lb3V0KHRpbWVyKX0KICAgIH0KICAgIGZ1bmN0aW9uIG5vcm1hbGl6ZVNoYWRvd1NpZ25hbChyb3cpewogICAgICBjb25zdCBwPXJvdyYmcm93LnBheWxvYWR8fHt9OwogICAgICBjb25zdCB1aU1hcmtldD1TdHJpbmcocm93JiZyb3cubWFya2V0fHwnJykudG9VcHBlckNhc2UoKT09PSdDUllQVE8nPydCVEMnOlN0cmluZyhyb3cmJnJvdy5tYXJrZXR8fCcnKS50b1VwcGVyQ2FzZSgpOwogICAgICByZXR1cm4gewogICAgICAgIHN0YXR1czonUkVBRFknLG1hcmtldDp1aU1hcmtldCxzb3VyY2U6J05FT05fU1RSQVRFR1lfU0lHTkFMJywKICAgICAgICBzdHJhdGVneV92ZXJzaW9uOnJvdyYmcm93LnN0cmF0ZWd5X3ZlcnNpb258fG51bGwscnVuX2lkOnJvdyYmcm93LnJ1bl9pZHx8bnVsbCwKICAgICAgICBzeW1ib2w6cm93JiZyb3cuc3ltYm9sfHxudWxsLGFzX29mOnJvdyYmcm93LmFzX29mfHxudWxsLAogICAgICAgIHNpZ25hbDpwLnNoYWRvd19kaXJlY3Rpb258fCdXQVRDSCcsdGFibGVfc2lnbmFsOnJvdyYmcm93LnNpZ25hbHx8bnVsbCwKICAgICAgICBlbnRyeV9hbGxvd2VkOmZhbHNlLHJpc2tfZ2F0ZTpyb3cmJnJvdy5yaXNrX2dhdGV8fCdTSEFET1dfT05MWScsCiAgICAgICAgcG9zaXRpb25fc3RhdGU6cm93JiZyb3cucG9zaXRpb25fc3RhdGV8fG51bGwsCiAgICAgICAgcHJvYmFiaWxpdHk6cC5wcm9iYWJpbGl0eV91cD09bnVsbD9udWxsOk51bWJlcihwLnByb2JhYmlsaXR5X3VwKSwKICAgICAgICBwcm9iYWJpbGl0eV90aHJlc2hvbGQ6cC5wcm9iYWJpbGl0eV90aHJlc2hvbGQ9PW51bGw/bnVsbDpOdW1iZXIocC5wcm9iYWJpbGl0eV90aHJlc2hvbGQpLAogICAgICAgIHByZWRpY3RlZF9yZXR1cm46cC5wcmVkaWN0ZWRfcmV0dXJuPT1udWxsP251bGw6TnVtYmVyKHAucHJlZGljdGVkX3JldHVybiksCiAgICAgICAgbW9kZWxfZmFtaWx5OnAubW9kZWxfZmFtaWx5fHxudWxsLG1vZGVsX3ZlcnNpb246cC5tb2RlbF92ZXJzaW9ufHxudWxsLAogICAgICAgIHRyYWluZWRfdGhyb3VnaDpwLnRyYWluZWRfdGhyb3VnaHx8bnVsbCwKICAgICAgICBzZWxlY3RlZF9mZWF0dXJlX2NvdW50OnAuc2VsZWN0ZWRfZmVhdHVyZV9jb3VudD09bnVsbD9udWxsOk51bWJlcihwLnNlbGVjdGVkX2ZlYXR1cmVfY291bnQpLAogICAgICAgIG1pc3NpbmdfZmVhdHVyZV9yYXRpbzpwLm1pc3NpbmdfZmVhdHVyZV9yYXRpbz09bnVsbD9udWxsOk51bWJlcihwLm1pc3NpbmdfZmVhdHVyZV9yYXRpbyksCiAgICAgICAgYWxsb3dfdHJhZGVfc2hhZG93OmZhbHNlLGxpdmVfZXhlY3V0aW9uOmZhbHNlLGF1dG9fdHJhZGVfdmlzaWJsZTpmYWxzZSwKICAgICAgICBwcm9kdWN0aW9uX3Byb21vdGlvbjpmYWxzZSxuZW9uX21pcnJvcmVkOkJvb2xlYW4ocC5uZW9uX21pcnJvcmVkKSwKICAgICAgICBuZW9uX21pcnJvcmVkX2F0OnAubmVvbl9taXJyb3JlZF9hdHx8bnVsbCwKICAgICAgICByZWFzb25fY29kZXM6QXJyYXkuaXNBcnJheShyb3cmJnJvdy5yZWFzb25fY29kZXMpP3Jvdy5yZWFzb25fY29kZXM6W10sCiAgICAgICAgcmVzZWFyY2hfb25seTp0cnVlLHNoYWRvd19vbmx5OnRydWUKICAgICAgfTsKICAgIH0KICAgIHRyeXsKICAgICAgaWYoIXByb2Nlc3MuZW52LkRBVEFCQVNFX1VSTF9SRUFERVIpdGhyb3cgbmV3IEVycm9yKCdEQl9OT1RfQ09ORklHVVJFRCcpOwogICAgICBjb25zdCB7bmVvbn09YXdhaXQgaW1wb3J0KCdAbmVvbmRhdGFiYXNlL3NlcnZlcmxlc3MnKTsKICAgICAgY29uc3Qgc3FsPW5lb24ocHJvY2Vzcy5lbnYuREFUQUJBU0VfVVJMX1JFQURFUik7CiAgICAgIGNvbnN0IHJvd3M9YXdhaXQgc3FsYAogICAgICAgIFNFTEVDVCBESVNUSU5DVCBPTiAoc3RyYXRlZ3lfdmVyc2lvbikKICAgICAgICAgIHJ1bl9pZCxtYXJrZXQsc3ltYm9sLGFzX29mLHN0cmF0ZWd5X3ZlcnNpb24sc2lnbmFsLGVudHJ5X2FsbG93ZWQsCiAgICAgICAgICByaXNrX2dhdGUscG9zaXRpb25fc3RhdGUscmVhc29uX2NvZGVzLHBheWxvYWQKICAgICAgICBGUk9NIHN0cmF0ZWd5X3NpZ25hbAogICAgICAgIFdIRVJFIHN0cmF0ZWd5X3ZlcnNpb24gSU4gKAogICAgICAgICAgJ0tBTE1BTl9WMl9VU19MT0dJVF8wMDEnLCdLQUxNQU5fVjJfS1JfTE9HSVRfMDAxJywnS0FMTUFOX1YyX0JUQ19MT0dJVF8wMDEnCiAgICAgICAgKQogICAgICAgIE9SREVSIEJZIHN0cmF0ZWd5X3ZlcnNpb24sYXNfb2YgREVTQwogICAgICBgOwogICAgICBjb25zdCBzaWduYWxzPXt9OwogICAgICBmb3IoY29uc3Qgcm93IG9mIHJvd3N8fFtdKXtjb25zdCBzPW5vcm1hbGl6ZVNoYWRvd1NpZ25hbChyb3cpO2lmKFsnVVMnLCdLUicsJ0JUQyddLmluY2x1ZGVzKHMubWFya2V0KSlzaWduYWxzW3MubWFya2V0XT1zO30KICAgICAgZm9yKGNvbnN0IG1hcmtldCBvZiBbJ1VTJywnS1InLCdCVEMnXSlpZighc2lnbmFsc1ttYXJrZXRdKXRocm93IG5ldyBFcnJvcignTkVPTl9TSEFET1dfTUlTU0lOR18nK21hcmtldCk7CiAgICAgIGxldCBsZWdhY3k9bnVsbCxsZWdhY3lFcnJvcj1udWxsOwogICAgICB0cnl7bGVnYWN5PWF3YWl0IGxlZ2FjeVNoYWRvdygpO31jYXRjaChlKXtsZWdhY3lFcnJvcj1TdHJpbmcoZT8ubWVzc2FnZXx8ZSk7fQogICAgICBjb25zdCBhc09mcz1PYmplY3QudmFsdWVzKHNpZ25hbHMpLm1hcCh4PT5EYXRlLnBhcnNlKHguYXNfb2Z8fCcnKSkuZmlsdGVyKE51bWJlci5pc0Zpbml0ZSk7CiAgICAgIGNvbnN0IGxhdGVzdEFzT2Y9YXNPZnMubGVuZ3RoP25ldyBEYXRlKE1hdGgubWF4KC4uLmFzT2ZzKSkudG9JU09TdHJpbmcoKTpudWxsOwogICAgICBjb25zdCBtaXJyb3JlZD1PYmplY3QudmFsdWVzKHNpZ25hbHMpLm1hcCh4PT5EYXRlLnBhcnNlKHgubmVvbl9taXJyb3JlZF9hdHx8JycpKS5maWx0ZXIoTnVtYmVyLmlzRmluaXRlKTsKICAgICAgY29uc3QgdXBkYXRlZEF0PW1pcnJvcmVkLmxlbmd0aD9uZXcgRGF0ZShNYXRoLm1heCguLi5taXJyb3JlZCkpLnRvSVNPU3RyaW5nKCk6bmV3IERhdGUoKS50b0lTT1N0cmluZygpOwogICAgICBjb25zdCByYW5raW5nQXNPZj1sZWdhY3kmJmxlZ2FjeS5sYXRlc3RfYXNfb2Z8fG51bGwscmFua2luZ1VwZGF0ZWRBdD1sZWdhY3kmJmxlZ2FjeS51cGRhdGVkX2F0fHxudWxsOwogICAgICBjb25zdCByYW5raW5nU3RhbGU9Qm9vbGVhbighcmFua2luZ0FzT2Z8fCFsYXRlc3RBc09mfHxEYXRlLnBhcnNlKHJhbmtpbmdBc09mKTxEYXRlLnBhcnNlKGxhdGVzdEFzT2YpKTsKICAgICAgcmVzLnNldEhlYWRlcignWC1LYWxtYW4tU2hhZG93LVNvdXJjZScsJ25lb24tc3RyYXRlZ3ktc2lnbmFsJyk7CiAgICAgIHJldHVybiByZXMuc3RhdHVzKDIwMCkuanNvbih7CiAgICAgICAgc2NoZW1hX3ZlcnNpb246J2thbG1hbi1zaGFkb3ctcmVhZG9ubHktdjInLHN0YXR1czonUkVBRFknLHRyYWNraW5nX3N0YXR1czonVFJBQ0tJTkcnLAogICAgICAgIGV4cGVyaW1lbnQ6J05FT05fRk9SV0FSRF9TSEFET1dfUkVBRF9NT0RFTCcsc2lnbmFsX3NvdXJjZTonTkVPTl9TVFJBVEVHWV9TSUdOQUwnLAogICAgICAgIHNpZ25hbF9zb3VyY2VfZnJlc2g6dHJ1ZSxsYXRlc3RfYXNfb2Y6bGF0ZXN0QXNPZix1cGRhdGVkX2F0OnVwZGF0ZWRBdCxzaWduYWxzLAogICAgICAgIHJhbmtpbmdfc291cmNlOmxlZ2FjeT8nTEVHQUNZX1NUQU5EQUxPTkVfQkFLRU9GRic6J1VOQVZBSUxBQkxFJywKICAgICAgICByYW5raW5nX2FzX29mOnJhbmtpbmdBc09mLHJhbmtpbmdfdXBkYXRlZF9hdDpyYW5raW5nVXBkYXRlZEF0LHJhbmtpbmdfc3RhbGU6cmFua2luZ1N0YWxlLAogICAgICAgIHJhbmtpbmdfZXJyb3I6bGVnYWN5RXJyb3IsZm9yd2FyZF9yYW5raW5nOkFycmF5LmlzQXJyYXkobGVnYWN5JiZsZWdhY3kuZm9yd2FyZF9yYW5raW5nKT9sZWdhY3kuZm9yd2FyZF9yYW5raW5nOltdLAogICAgICAgIHBvc3Rfc2VlZF9yZXR1cm5fcm93czpsZWdhY3kmJmxlZ2FjeS5wb3N0X3NlZWRfcmV0dXJuX3Jvd3MhPW51bGw/bGVnYWN5LnBvc3Rfc2VlZF9yZXR1cm5fcm93czpudWxsLAogICAgICAgIGxlZ2FjeV9leHBlcmltZW50OmxlZ2FjeSYmbGVnYWN5LmV4cGVyaW1lbnR8fG51bGwsbGVnYWN5X3NlZWRfZW5kOmxlZ2FjeSYmbGVnYWN5LnNlZWRfZW5kfHxudWxsLAogICAgICAgIGludmFyaWFudHM6e3JlYWRfb25seTp0cnVlLHRyYWRlX2V4ZWN1dGlvbjpmYWxzZSxlbnRyeV9hbGxvd2VkX2Zvcl9yZWFsX29yZGVyczpmYWxzZSwKICAgICAgICAgIGF1dG9fdHJhZGVfdmlzaWJsZTpmYWxzZSxsaXZlX2V4ZWN1dGlvbjpmYWxzZSx0b3NzX2V4ZWN1dGlvbjpmYWxzZX0KICAgICAgfSk7CiAgICB9Y2F0Y2goZXJyKXsKICAgICAgdHJ5ewogICAgICAgIGNvbnN0IGxlZ2FjeT1hd2FpdCBsZWdhY3lTaGFkb3coKTsKICAgICAgICByZXMuc2V0SGVhZGVyKCdYLUthbG1hbi1TaGFkb3ctU291cmNlJywnbGVnYWN5LWZhbGxiYWNrJyk7CiAgICAgICAgcmV0dXJuIHJlcy5zdGF0dXMoMjAwKS5qc29uKHsuLi5sZWdhY3ksc2NoZW1hX3ZlcnNpb246J2thbG1hbi1zaGFkb3ctcmVhZG9ubHktdjInLAogICAgICAgICAgc2lnbmFsX3NvdXJjZTonTEVHQUNZX1NUQU5EQUxPTkVfQkFLRU9GRicsc2lnbmFsX3NvdXJjZV9mcmVzaDpmYWxzZSwKICAgICAgICAgIHNpZ25hbF9zb3VyY2VfZXJyb3I6U3RyaW5nKGVycj8ubWVzc2FnZXx8ZXJyKSxyYW5raW5nX3NvdXJjZTonTEVHQUNZX1NUQU5EQUxPTkVfQkFLRU9GRicsCiAgICAgICAgICByYW5raW5nX2FzX29mOmxlZ2FjeS5sYXRlc3RfYXNfb2Z8fG51bGwscmFua2luZ191cGRhdGVkX2F0OmxlZ2FjeS51cGRhdGVkX2F0fHxudWxsLHJhbmtpbmdfc3RhbGU6dHJ1ZSwKICAgICAgICAgIGludmFyaWFudHM6ey4uLihsZWdhY3kuaW52YXJpYW50c3x8e30pLHJlYWRfb25seTp0cnVlLHRyYWRlX2V4ZWN1dGlvbjpmYWxzZSwKICAgICAgICAgICAgZW50cnlfYWxsb3dlZF9mb3JfcmVhbF9vcmRlcnM6ZmFsc2UsYXV0b190cmFkZV92aXNpYmxlOmZhbHNlLGxpdmVfZXhlY3V0aW9uOmZhbHNlLHRvc3NfZXhlY3V0aW9uOmZhbHNlfQogICAgICAgIH0pOwogICAgICB9Y2F0Y2goZmFsbGJhY2tFcnIpewogICAgICAgIHJldHVybiByZXMuc3RhdHVzKDUwMikuanNvbih7ZXJyb3I6J1NIQURPV19SRUFEX01PREVMX0ZBSUxFRCcsbmVvbl9lcnJvcjpTdHJpbmcoZXJyPy5tZXNzYWdlfHxlcnIpLAogICAgICAgICAgbGVnYWN5X2Vycm9yOlN0cmluZyhmYWxsYmFja0Vycj8ubWVzc2FnZXx8ZmFsbGJhY2tFcnIpLHRyYWRlX2V4ZWN1dGlvbjpmYWxzZX0pOwogICAgICB9CiAgICB9CiAgfQo="
UI_REPLACEMENT_B64 = "ZnVuY3Rpb24gcmVuZGVyU2hhZG93KGopewogIGNvbnN0IHNpZ25hbHM9ai5zaWduYWxzfHx7fSxyYW5raW5nPWouZm9yd2FyZF9yYW5raW5nfHxbXTsKICBjb25zdCBzaWduYWxTb3VyY2U9U3RyaW5nKGouc2lnbmFsX3NvdXJjZXx8J1VOS05PV04nKTsKICBjb25zdCByYW5raW5nU291cmNlPVN0cmluZyhqLnJhbmtpbmdfc291cmNlfHwnVU5BVkFJTEFCTEUnKTsKICBjb25zdCBzaWduYWxCYWRnZT1zaWduYWxTb3VyY2U9PT0nTkVPTl9TVFJBVEVHWV9TSUdOQUwnP2JhZGdlKCdOZW9uIFNpZ25hbCcsJ29rJyk6YmFkZ2UoJ0xlZ2FjeSBTaWduYWwnLCd3YXJuJyk7CiAgY29uc3QgcmFua2luZ0JhZGdlPWoucmFua2luZ19zdGFsZT9iYWRnZSgnUmFua2luZyBzdGFsZScsJ3dhcm4nKToocmFua2luZ1NvdXJjZT09PSdVTkFWQUlMQUJMRSc/YmFkZ2UoJ1Jhbmtpbmcg7JeG7J2MJywnd2FybicpOmJhZGdlKCdSYW5raW5nIOy1nOyLoCcsJ29rJykpOwogIGNvbnN0IGNhcmRzPVsnVVMnLCdLUicsJ0JUQyddLm1hcChtPT57CiAgICBjb25zdCBzPXNpZ25hbHNbbV18fHt9LHNpZz1TdHJpbmcocy5zaWduYWx8fCfigJQnKSxraW5kPXNpZz09PSdCVVknPyd3YXJuJzonJzsKICAgIGNvbnN0IHNjb3JlPXMucHJvYmFiaWxpdHkhPW51bGw/YO2ZleuloCAke3BjdChzLnByb2JhYmlsaXR5LDEwMCl9YDpzLnByZWRpY3RlZF9yZXR1cm4hPW51bGw/YOyYiOyDgeyImOydtSAke3BjdChzLnByZWRpY3RlZF9yZXR1cm4sMTAwKX1gOifrqqjrjbgg7KCQ7IiYIOKAlCc7CiAgICBjb25zdCB0aHJlc2hvbGQ9cy5wcm9iYWJpbGl0eV90aHJlc2hvbGQhPW51bGw/JyDCtyBnYXRlICcrcGN0KHMucHJvYmFiaWxpdHlfdGhyZXNob2xkLDEwMCk6Jyc7CiAgICByZXR1cm4gYDxkaXYgY2xhc3M9ImNhcmQiPjxkaXYgY2xhc3M9InNlY3Rpb24tdGl0bGUiPjxoMz4ke219PC9oMz4ke2JhZGdlKHNpZyxraW5kKX08L2Rpdj48ZGl2IGNsYXNzPSJrcGkiPiR7ZXNjKHMuc3ltYm9sfHwn4oCUJyl9PC9kaXY+PGRpdiBjbGFzcz0ibWV0cmljLWxpbmUiPjxzcGFuIGNsYXNzPSJtdXRlZCI+66qo6424PC9zcGFuPjxiPiR7ZXNjKHMubW9kZWxfZmFtaWx5fHxzLnN0cmF0ZWd5X3ZlcnNpb258fCfigJQnKX08L2I+PC9kaXY+PGRpdiBjbGFzcz0ibWV0cmljLWxpbmUiPjxzcGFuIGNsYXNzPSJtdXRlZCI+U2NvcmU8L3NwYW4+PGI+JHtzY29yZX0ke3RocmVzaG9sZH08L2I+PC9kaXY+PGRpdiBjbGFzcz0ibWV0cmljLWxpbmUiPjxzcGFuIGNsYXNzPSJtdXRlZCI+6rKw7Lih66WgPC9zcGFuPjxiPiR7cy5taXNzaW5nX2ZlYXR1cmVfcmF0aW89PW51bGw/J+KAlCc6cGN0KHMubWlzc2luZ19mZWF0dXJlX3JhdGlvLDEwMCl9PC9iPjwvZGl2PjxkaXYgY2xhc3M9InNtYWxsIiBzdHlsZT0ibWFyZ2luLXRvcDo5cHgiPiR7dGltZShzLmFzX29mKX0gwrcgJHtlc2Mocy5zdHJhdGVneV92ZXJzaW9ufHwnJyl9PC9kaXY+PC9kaXY+YDsKICB9KS5qb2luKCcnKTsKICBjb25zdCByYW5rcz1yYW5raW5nLm1hcCgocixpKT0+YDxkaXYgY2xhc3M9InRvcCI+PGRpdiBjbGFzcz0icmFuayI+JHtyLmZvcndhcmRfcmFuaz09bnVsbD9pKzE6ci5mb3J3YXJkX3JhbmsrMX08L2Rpdj48ZGl2PjxkaXYgY2xhc3M9ImFzc2V0Ij4ke2VzYyhyLnN0cmF0ZWd5fHwn4oCUJyl9PC9kaXY+PGRpdiBjbGFzcz0ic21hbGwiPiR7ZXNjKHIuc3RhdHVzfHwn4oCUJyl9PC9kaXY+PC9kaXY+PGRpdiBjbGFzcz0icmlnaHQiPjxiPiR7ci5zaGFycGU9PW51bGw/J+KAlCc6YFNoYXJwZSAke2ZtdChyLnNoYXJwZSwyKX1gfTwvYj48ZGl2IGNsYXNzPSJzbWFsbCI+7IiY7J21ICR7ci50b3RhbF9yZXR1cm49PW51bGw/J+KAlCc6cGN0KHIudG90YWxfcmV0dXJuLDEwMCl9IMK3IE1ERCAke3IubWF4X2RyYXdkb3duPT1udWxsPyfigJQnOnBjdChyLm1heF9kcmF3ZG93biwxMDApfTwvZGl2PjwvZGl2PjwvZGl2PmApLmpvaW4oJycpOwogIGNvbnN0IHJhbmtpbmdXaGVuPWoucmFua2luZ19hc19vZj90aW1lKGoucmFua2luZ19hc19vZik6J+KAlCc7CiAgcmV0dXJuIGA8ZGl2IGNsYXNzPSJzdW1tYXJ5Ij4ke2JhZGdlKCfsobDtmowg7KCE7JqpJywnb2snKX0gJHtzaWduYWxCYWRnZX0gJHtyYW5raW5nQmFkZ2V9IDxzcGFuIGNsYXNzPSJtdXRlZCI+7Iug7Zi4ICR7dGltZShqLmxhdGVzdF9hc19vZil9PC9zcGFuPjwvZGl2PjxkaXYgY2xhc3M9Im5vdGljZSI+U0hBRE9XIOyLoO2YuOuKlCBOZW9uIOy1nOyLoCBtaXJyb3Lrpbwg7IKs7Jqp7ZWp64uI64ukLiBBL0IvQyByYW5raW5n7J2AIOuzhOuPhCBiYWtlb2ZmIGxlZ2FjeSBzbmFwc2hvdOydtOupsCDstZzsi6Ag7Iug7Zi47JmAIOq4sOykgOyLnOygkOydtCDri6Trpbwg7IiYIOyeiOyKteuLiOuLpC4g7J20IO2ZlOuptOydgCDso7zrrLjsnLzroZwg7KCE64us65CY7KeAIOyViuyKteuLiOuLpC48L2Rpdj48ZGl2IGNsYXNzPSJncmlkIHNlY3Rpb24iPiR7Y2FyZHN9PC9kaXY+PGRpdiBjbGFzcz0iY2FyZCBzZWN0aW9uIj48ZGl2IGNsYXNzPSJzZWN0aW9uLXRpdGxlIj48aDM+QS9CL0MgRm9yd2FyZCBSYW5raW5nPC9oMz48c3BhbiBjbGFzcz0ibXV0ZWQiPmxlZ2FjeSDquLDspIAgJHtyYW5raW5nV2hlbn0gwrcgcG9zdC1zZWVkICR7Zm10KGoucG9zdF9zZWVkX3JldHVybl9yb3dzLDApfSByb3dzPC9zcGFuPjwvZGl2PiR7cmFua3N8fCc8ZGl2IGNsYXNzPSJub3RpY2UiPu2YhOyerCBsZWdhY3kgZm9yd2FyZCByYW5raW5n7J2EIOydveydhCDsiJgg7JeG7Iq164uI64ukLjwvZGl2Pid9PC9kaXY+YDsKfQo="

def build_base():
    subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
    if not BASE_MANIFEST.is_file():
        raise SystemExit("v7.4.31 base manifest was not generated")

def decode_manifest(manifest, out):
    rows=[json.loads(x) for x in manifest.read_text(encoding="utf-8").splitlines() if x.strip()]
    if len(rows)!=30:
        raise SystemExit(f"expected 30 files, got {len(rows)}")
    for row in rows:
        rel=Path(row["file"])
        if rel.is_absolute() or ".." in rel.parts:
            raise SystemExit(f"unsafe path: {rel}")
        p=out/rel
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(base64.b64decode(row["data_b64"]))

def patch_shadow_api(src):
    p=src/"api/assets.js"
    text=p.read_text(encoding="utf-8")
    start="  const __kalmanUrl = new URL(req.url || '/api/dashboard', 'http://localhost');\n  if ((__kalmanUrl.searchParams.get('market') || '').toUpperCase() === 'SHADOW') {"
    end="\n  if(req.method!=='GET')return res.status(405).json({error:'METHOD_NOT_ALLOWED'});"
    i=text.find(start)
    if i<0: raise SystemExit("SHADOW route start anchor missing")
    j=text.find(end,i)
    if j<0: raise SystemExit("SHADOW route end anchor missing")
    replacement=base64.b64decode(API_REPLACEMENT_B64).decode("utf-8")
    p.write_text(text[:i]+replacement+text[j:],encoding="utf-8")

def patch_shadow_ui(src):
    p=src/"app.js"
    text=p.read_text(encoding="utf-8")
    i=text.find("function renderShadow(j){")
    j=text.find("\nfunction renderUS(j){",i)
    if i<0 or j<0: raise SystemExit("renderShadow/renderUS anchor missing")
    replacement=base64.b64decode(UI_REPLACEMENT_B64).decode("utf-8")
    p.write_text(text[:i]+replacement+text[j:],encoding="utf-8")

def patch_versions(src):
    for rel in ("index.html","api/health.js"):
        p=src/rel
        text=p.read_text(encoding="utf-8")
        if "vNext.7.4.31" not in text:
            raise SystemExit(f"v7.4.31 version anchor missing in {rel}")
        p.write_text(text.replace("vNext.7.4.31",TARGET),encoding="utf-8")

def validate(src):
    if len(sorted((src/"api").rglob("*.js")))!=12:
        raise SystemExit("API count changed")
    app=(src/"app.js").read_text(encoding="utf-8")
    assets=(src/"api/assets.js").read_text(encoding="utf-8")
    payload=(src/"lib/assets-payload.js").read_text(encoding="utf-8")
    market=(src/"api/market.js").read_text(encoding="utf-8")
    health=(src/"api/health.js").read_text(encoding="utf-8")
    index=(src/"index.html").read_text(encoding="utf-8")
    for marker in ("kalman-shadow-readonly-v2","NEON_STRATEGY_SIGNAL","KALMAN_V2_US_LOGIT_001","KALMAN_V2_KR_LOGIT_001","KALMAN_V2_BTC_LOGIT_001","LEGACY_STANDALONE_BAKEOFF","ranking_stale","entry_allowed_for_real_orders:false","trade_execution:false"):
        if marker not in assets: raise SystemExit(f"SHADOW API marker missing: {marker}")
    for marker in ("Neon Signal","Ranking stale","SHADOW 신호는 Neon 최신 mirror","legacy 기준"):
        if marker not in app: raise SystemExit(f"SHADOW UI marker missing: {marker}")
    for marker in ("overlayStaleEtfDisplayPrices","etf_display_price_source"):
        if marker not in payload: raise SystemExit(f"ETF marker missing: {marker}")
    if "investment-hub-market-v0.4" not in market: raise SystemExit("ETF market marker missing")
    for marker in ("function renderCommandAccount(","function renderCommandModel(","R5.1 2026 Annual Ledger","Execution Quality:"):
        if marker not in app: raise SystemExit(f"preserved UI marker missing: {marker}")
    for marker in ("augmentAssetsSelectorsFromNeon","_r5CanonicalLedger","canonical_ledger_source","if(v==null||v==='')return null;"):
        if marker not in assets: raise SystemExit(f"preserved API marker missing: {marker}")
    if TARGET not in index or TARGET not in health: raise SystemExit("version marker missing")
    if "trade_enabled:false" not in health or "account_trade_execution:false" not in health: raise SystemExit("read-only invariant missing")
    if shutil.which("node"):
        for q in sorted(src.rglob("*.js")):
            subprocess.run(["node","--check",str(q)],check=True,stdout=subprocess.DEVNULL)
    return {"version":TARGET,"shadow_signal_source":"NEON_STRATEGY_SIGNAL","shadow_ranking_source":"LEGACY_STANDALONE_BAKEOFF","shadow_ranking_stale_explicit":True,"etf_display_price_overlay_preserved":True,"canonical_r5_ledger_preserved":True,"command_renderers_preserved":True,"trade_gate_unchanged":True,"web_read_only":True,"base_version":"vNext.7.4.31"}

def emit_source_manifest(src,out):
    rows=[]
    for p in sorted(x for x in src.rglob("*") if x.is_file()):
        rows.append(json.dumps({"file":p.relative_to(src).as_posix(),"data_b64":base64.b64encode(p.read_bytes()).decode("ascii")},separators=(",",":"),ensure_ascii=False))
    out.write_text("\n".join(rows)+"\n",encoding="utf-8")

def main():
    build_base()
    OUT_DIR.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kalman-v7432-") as td:
        src=Path(td)/"source"; src.mkdir()
        decode_manifest(BASE_MANIFEST,src)
        patch_shadow_api(src)
        patch_shadow_ui(src)
        patch_versions(src)
        report=validate(src)
        manifest=OUT_DIR/"source_manifest.ndjson"
        emit_source_manifest(src,manifest)
        report["source_manifest_sha256"]=hashlib.sha256(manifest.read_bytes()).hexdigest()
        (OUT_DIR/"build_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
