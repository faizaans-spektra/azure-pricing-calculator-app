import requests

api = 'https://prices.azure.com/api/retail/prices'

filters = [
    "serviceName eq 'Azure App Service' and contains(skuName,'P1') and armRegionName eq 'uksouth'",
    "serviceName eq 'Azure App Service' and contains(meterName,'P1') and armRegionName eq 'uksouth'",
    "serviceName eq 'Azure App Service' and contains(productName,'App') and armRegionName eq 'uksouth'",
    "serviceName eq 'SQL Database' and contains(skuName,'GP_Gen5_2') and armRegionName eq 'centralindia'",
    "serviceName eq 'SQL Database' and contains(meterName,'GP_Gen5_2') and armRegionName eq 'centralindia'",
    "serviceName eq 'SQL Database' and contains(productName,'GP_Gen5_2') and armRegionName eq 'centralindia'",
    "serviceName eq 'SQL Database' and contains(productName,'vCore') and armRegionName eq 'centralindia'",
]

for f in filters:
    print('---', f)
    r = requests.get(api, params={'$filter': f}, timeout=30)
    print('status', r.status_code)
    if r.status_code != 200:
        print(r.text[:500])
        continue
    data = r.json()
    print('count', data.get('Count'), 'items', len(data.get('Items', [])))
    for item in data.get('Items', [])[:20]:
        print('skuName:', item.get('skuName'))
        print('meterName:', item.get('meterName'))
        print('productName:', item.get('productName'))
        print('unitOfMeasure:', item.get('unitOfMeasure'))
        print('armRegionName:', item.get('armRegionName'))
        print('retailPrice:', item.get('retailPrice'))
        print()
