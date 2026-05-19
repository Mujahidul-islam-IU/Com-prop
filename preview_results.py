import json

with open('./output/cre_sydney-region-nsw_Office_20260516_113503.json') as f:
    data = json.load(f)

print(f"Total listings scraped: {len(data)}\n")
for i, d in enumerate(data):
    print(f"{i+1}. Title    : {d.get('title','')[:80]}")
    print(f"   Address  : {d.get('address','')[:80]}")
    print(f"   Price    : {d.get('price','')}")
    print(f"   Size     : {d.get('size','')}")
    print(f"   Type     : {d.get('propertyType','')}")
    print(f"   Agent    : {d.get('agent','')}")
    print(f"   Agency   : {d.get('agency','')}")
    print(f"   Link     : {d.get('link','')[:100]}")
    print(f"   Tags     : {d.get('tags','')}")
    print()
