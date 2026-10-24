#!/usr/bin/env python3
from invoice_fallback import corroborated_filename as parse

invoice="209126000964"
amea="AMEA2026073124"
h="H209SC26088039"
filename=f"TAX INVOICE-{invoice}-SQ-{amea}-KRW4438500.00.pdf"
subject=f"Notice: Invoice Issued & Statement Confirmed - J001-X209SC26088039-Z01 -{invoice} - {h} - Name-{amea}"
assert parse(filename,subject)==(invoice,h,"",amea,4438500,"SUBJECT_CORROBORATED_FILENAME")
assert parse(filename,subject.replace(invoice,"209126000963")) is None
assert parse(filename,subject.replace(amea,"AMEA2026073125")) is None
assert parse(filename,subject.replace(h,"")) is None
assert parse(filename.replace(".00.pdf",".50.pdf"),subject) is None
assert parse(filename.replace("KRW4438500","USD4438500"),subject) is None
assert parse(filename.replace(invoice,"209126000965"),subject) is None
assert parse("TAX INVOICE.pdf",subject) is None
print("QQ_SUBJECT_CORROBORATION_PASS")
