import requests
api = 'https://prices.azure.com/api/retail/prices'
queries = [
    "serviceName eq 'SQL Database' and armRegionName eq 'centralindia' and skuName eq '2 vCore'",
    "serviceName eq 'SQL Database' and armRegionName eq 'centralindia' and skuName eq '36 vCore'",
    "serviceName eq 'SQL Database' and armRegionName eq 'centralindia' and skuName eq 'GP_Gen5_2'",
    "serviceName eq 'SQL Database' and armRegionName eq 'centralindia' and contains(productName,'2 vCore')",
    "serviceName eq 'SQL Database' and armRegionName eq 'centralindia' and contains(productName,'36 vCore')",
    "serviceName eq 'SQL Database' and armRegionName eq 'centralindia' and contains(meterName,'vCore')",
    "serviceName eq 'SQL Database' and armRegionName eq 'centralindia' and contains(skuName,'vCore')",
]
for q in queries:
    print('---', q)
    r = requests.get(api, params={'$filter': q}, timeout=30)
    print('status', r.status_code)
    if r.status_code != 200:
        print(r.text[:500])
        continue
    data = r.json()
    print('count', data.get('Count'), len(data.get('Items', [])))
    for item in data.get('Items', [])[:10]:
        print(item.get('skuName'), '|', item.get('meterName'), '|', item.get('productName'), '|', item.get('unitOfMeasure'), '|', item.get('armRegionName'))
    print()