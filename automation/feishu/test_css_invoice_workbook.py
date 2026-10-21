"""Run with a synthetic local XLSX (in-memory ZIP fixture); no customer data."""
import io, tempfile, zipfile
from pathlib import Path
from css_invoice_workbook import load,audit
from xml.sax.saxutils import escape

def worksheet(headers,values):
    rows=[headers,*values]
    body=""
    for ri,row in enumerate(rows,1):
        cells=""
        for ci,value in enumerate(row):
            col=chr(65+ci)
            cells+=f'<c r="{col}{ri}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
        body+=f'<row r="{ri}">{cells}</row>'
    return f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{body}</sheetData></worksheet>'

wb='<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="CSS Tax Invoices" sheetId="1" r:id="rId1"/><sheet name="Quotation Invoice Match" sheetId="2" r:id="rId2"/></sheets></workbook>'
rels='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>'
with tempfile.TemporaryDirectory() as d:
    fn=Path(d)/"test.xlsx"
    with zipfile.ZipFile(fn,"w") as z:
        z.writestr("xl/workbook.xml",wb)
        z.writestr("xl/_rels/workbook.xml.rels",rels)
        z.writestr("xl/worksheets/sheet1.xml",worksheet(
            ["invoice_number","amount_krw","project_id","institution"],[["INV001",100,"AMEA1","Test"]]))
        z.writestr("xl/worksheets/sheet2.xml",worksheet(
            ["invoice_number","match_type"],[["INV001","Exact quotation ID"]]))
    result=audit(fn)
    assert result["INVOICE_COUNT"]==1
    assert result["QUOTATION_MATCH_ROW_COUNT"]==1
    assert result["BASE_WRITES"]==0
print("CSS_INVOICE_WORKBOOK_OFFLINE_TEST: PASS")
