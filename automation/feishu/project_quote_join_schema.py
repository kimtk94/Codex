#!/usr/bin/env python3
"""Show only metadata field names/types for the Quote-to-project reconciliation."""
import json
from sales_home_links import API, pages, extract_token, require, request

TABLES={
  "PROJECT_BOARD":"tblTZe5tkRUeOHM8",
  "QUOTE_INDEX":"tblkUTP09Sqy6vKk",
  "QUOTE_LINES":"tblHme64Ccdj4Fwv",
  "QUOTES":"tblaFDb2DZRJjCxy",
}
def main():
    auth=request("POST","/open-apis/auth/v3/tenant_access_token/internal",
         body={"app_id":require("FEISHU_APP_ID"),"app_secret":require("FEISHU_APP_SECRET")})
    token=extract_token(auth)
    for name,table in TABLES.items():
        fields=list(pages(API+"/tables/"+table+"/fields",token))
        print("FIELD_MAP",name,json.dumps([(f.get("field_name"),f.get("type")) for f in fields],ensure_ascii=False))
    print("RECORDS_READ=0 WRITES=0 CUSTOMER_VALUES_LOGGED=0")
if __name__=="__main__":main()
