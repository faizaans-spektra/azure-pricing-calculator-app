import requests

print('--- sample items ---')
resp = requests.get('https://prices.azure.com/api/retail/prices', params={'$top': 20})
print('status', resp.status_code)
data = resp.json()
print('count', data.get('Count'))
for i, item in enumerate(data.get('Items', [])[:20]):
    print('--- item', i)
    print('serviceName:', item.get('serviceName'))
    print('skuName:', item.get('skuName'))
    print('productName:', item.get('productName'))
    print('meterName:', item.get('meterName'))
    print('armRegionName:', item.get('armRegionName'))
    print('unitOfMeasure:', item.get('unitOfMeasure'))
    print('retailPrice:', item.get('retailPrice'))

print('--- region names ---')
regions = set(item.get('armRegionName') for item in data.get('Items', []) if item.get('armRegionName'))
print(regions)

print('--- service names ---')
services = set(item.get('serviceName') for item in data.get('Items', []) if item.get('serviceName'))
print(services)
