import requests

api = 'https://prices.azure.com/api/retail/prices'
filters = [
    "serviceName eq 'Storage' and armRegionName eq 'eastus' and contains(meterName,'LRS Disk')",
    "serviceName eq 'Storage' and armRegionName eq 'eastus' and contains(meterName,'ZRS Disk')",
    "serviceName eq 'Storage' and armRegionName eq 'eastus' and contains(meterName,'Disk Mount')",
    "serviceName eq 'Storage' and armRegionName eq 'eastus' and contains(skuName,'P') and contains(meterName,'Disk')",
    "serviceName eq 'Storage' and armRegionName eq 'eastus' and contains(skuName,'E') and contains(meterName,'Disk')",
    "serviceName eq 'Storage' and armRegionName eq 'eastus' and contains(meterName,'Disk') and contains(productName,'Managed Disks')",
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
        print('retailPrice:', item.get('retailPrice'))
        print('armRegionName:', item.get('armRegionName'))
        print('')
