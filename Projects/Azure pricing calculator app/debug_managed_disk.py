import requests

api = 'https://prices.azure.com/api/retail/prices'
filters = [
    "serviceName eq 'Storage'",
    "contains(meterName,'Premium SSD')",
    "contains(meterName,'Standard SSD')",
    "contains(meterName,'Premium') and contains(meterName,'Managed Disk')",
    "contains(meterName,'Standard') and contains(meterName,'Managed Disk')",
]

for f in filters:
    r = requests.get(api, params={'$filter': f})
    print('---', f)
    print('status', r.status_code)
    data = r.json()
    print('count', data.get('Count'))
    for item in data.get('Items', [])[:5]:
        print('skuName:', item.get('skuName'))
        print('meterName:', item.get('meterName'))
        print('productName:', item.get('productName'))
        print('armRegionName:', item.get('armRegionName'))
        print('unitOfMeasure:', item.get('unitOfMeasure'))
        print('retailPrice:', item.get('retailPrice'))
        print()
