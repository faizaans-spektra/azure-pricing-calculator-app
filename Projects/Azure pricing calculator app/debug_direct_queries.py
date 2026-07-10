import requests
api = 'https://prices.azure.com/api/retail/prices'
queries = [
    "serviceName eq 'Azure App Service' and armRegionName eq 'uksouth' and skuName eq 'P1 v2'",
    "serviceName eq 'Azure App Service' and armRegionName eq 'uksouth' and contains(skuName,'P1 v2')",
    "serviceName eq 'Azure App Service' and armRegionName eq 'uksouth' and contains(skuName,'P1')",
    "serviceName eq 'Azure App Service' and armRegionName eq 'uksouth' and contains(productName,'Premium v2')",
    "serviceName eq 'SQL Database' and armRegionName eq 'centralindia' and skuName eq '36 vCore'",
    "serviceName eq 'SQL Database' and armRegionName eq 'centralindia' and contains(skuName,'36 vCore')",
    "serviceName eq 'SQL Database' and armRegionName eq 'centralindia' and contains(productName,'Compute FSv2 Series')",
]
for q in queries:
    print('---', q)
    r = requests.get(api, params={'$filter': q}, timeout=30)
    print('status', r.status_code)
    data = r.json()
    print('count', data.get('Count'), len(data.get('Items', [])))
    for item in data.get('Items', [])[:10]:
        print(item.get('skuName'), '|', item.get('meterName'), '|', item.get('productName'), '|', item.get('unitOfMeasure'), '|', item.get('armRegionName'))
    print()