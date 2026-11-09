"""Normalized, content-addressed templates for repeated Salesforce Product Lines.

Customer-specific and Quote-specific prices, discounts, pack quantities, source
records and approval states ALWAYS stay on their own Quote snapshot. Only
identity-independent structure (Product name/category/process descriptions and
process *labels*) is shared. The source UI remains authoritative.
"""
import hashlib
import json

REF="__shared_product_line_ref"
PRODUCT_FIELDS=("productId","productName","productCategory","processNames")
CHILD_FIELDS=("productName","sourceProcessNames")
PROCESS_FIELDS=("processType","processName","dataUnit","isCloud")


class TemplateIntegrityError(ValueError):
    pass


def compact_json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))


def fingerprint(template):
    return hashlib.sha256(compact_json(template).encode("utf-8")).hexdigest()


def _template_for(record,kind):
    if not isinstance(record,dict) or REF in record:
        raise TemplateIntegrityError("INVALID_SOURCE_LINE")
    fields=PRODUCT_FIELDS if kind=="quote" else CHILD_FIELDS
    meta={k:record[k] for k in fields if k in record}
    # Product-specific identifiers such as Quote child a0N and user-specific
    # rates must NEVER contribute to a shared template.
    if not isinstance(meta.get("productName"),str) or not meta["productName"]:
        return None
    rows=record.get("processPriceLines") if kind=="quote" else None
    if rows is not None and not (isinstance(rows,list) and all(isinstance(x,dict) for x in rows)):
        raise TemplateIntegrityError("INVALID_PROCESS_ROWS")
    schema=[{k:r[k] for k in PROCESS_FIELDS if k in r} for r in rows] if rows is not None else None
    return {"kind":kind,"fields":meta,"process_schema":schema}


def _compact_line(record,kind,templates):
    template=_template_for(record,kind)
    if template is None:
        return
    key=fingerprint(template)
    templates[key]=template
    for field in template["fields"]:
        del record[field]
    rows=record.get("processPriceLines")
    if rows is not None:
        for row,stable in zip(rows,template["process_schema"]):
            for field in stable:
                del row[field]
    record[REF]=key


def compact(payload):
    """Return a fully separate persisted copy plus shared immutable templates."""
    result=json.loads(compact_json(payload))
    templates={}
    if result.get("resource")=="quote":
        _compact_line(result,"quote",templates)
    elif result.get("mode")=="bundle":
        for quote in result.get("linkedQuotes",[]):
            _compact_line(quote,"quote",templates)
            products=quote.get("sourceProductEvidence")
            if isinstance(products,list):
                if len(products)>12:
                    raise TemplateIntegrityError("TOO_MANY_SOURCE_PRODUCTS")
                for child in products:
                    _compact_line(child,"child",templates)
    return result,templates


def _restore_line(record,kind,fetch):
    key=record.get(REF)
    if key is None:
        return
    if not isinstance(key,str) or len(key)!=64:
        raise TemplateIntegrityError("INVALID_TEMPLATE_REFERENCE")
    template=fetch(key)
    if not isinstance(template,dict) or fingerprint(template)!=key or template.get("kind")!=kind:
        raise TemplateIntegrityError("TEMPLATE_MISSING_OR_TAMPERED")
    if set(template)!={"kind","fields","process_schema"}:
        raise TemplateIntegrityError("INVALID_TEMPLATE_SCHEMA")
    fields=template["fields"]
    allowed=PRODUCT_FIELDS if kind=="quote" else CHILD_FIELDS
    if not isinstance(fields,dict) or not all(k in allowed for k in fields):
        raise TemplateIntegrityError("INVALID_TEMPLATE_FIELDS")
    if any(k in record for k in fields):
        raise TemplateIntegrityError("SOURCE_TEMPLATE_CONFLICT")
    schema=template["process_schema"]
    rows=record.get("processPriceLines")
    if schema is not None:
        if not isinstance(schema,list) or not isinstance(rows,list) or len(schema)!=len(rows):
            raise TemplateIntegrityError("PROCESS_SCHEMA_LENGTH_MISMATCH")
        for row,stable in zip(rows,schema):
            if not isinstance(row,dict) or not isinstance(stable,dict) or any(k not in PROCESS_FIELDS or k in row for k in stable):
                raise TemplateIntegrityError("PROCESS_SCHEMA_TAMPERED")
            row.update(stable)
    elif rows is not None:
        raise TemplateIntegrityError("PROCESS_SCHEMA_UNEXPECTED")
    record.update(fields)
    del record[REF]


def expand(persisted,fetch,only_refs=None):
    """Rehydrate all templates, or just one selected hash for byte accounting."""
    result=json.loads(compact_json(persisted))
    def wanted(line):
        return only_refs is None or line.get(REF) in only_refs
    if result.get("resource")=="quote":
        if wanted(result):
            _restore_line(result,"quote",fetch)
    elif result.get("mode")=="bundle":
        for quote in result.get("linkedQuotes",[]):
            if wanted(quote):
                _restore_line(quote,"quote",fetch)
            for child in quote.get("sourceProductEvidence",[]):
                if wanted(child):
                    _restore_line(child,"child",fetch)
    return result


def refs(persisted):
    ids=[]
    if persisted.get("resource")=="quote" and REF in persisted:
        ids.append(persisted[REF])
    for q in persisted.get("linkedQuotes",[]):
        if REF in q:
            ids.append(q[REF])
        for child in q.get("sourceProductEvidence",[]):
            if REF in child:
                ids.append(child[REF])
    return ids
