import requests

api = 'https://prices.azure.com/api/retail/prices'

print('--- SQL Database candidates ---')
for service in ['Azure SQL Database', 'SQL Database', 'SQL', 'Database']:
    r = requests.get(api, params={'$filter': f"serviceName eq '{service}'"})
    print('filter:', service, 'status', r.status_code)
    data = r.json()
    print('count', data.get('Count'))
    if data.get('Items'):
        item = data['Items'][0]
        print('sample skuName:', item.get('skuName'))
        print('sample meterName:', item.get('meterName'))
        print('sample productName:', item.get('productName'))
    print()

print('--- App Service candidates ---')
for service in ['App Service', 'App Services', 'Web Apps', 'App Service Environment', 'App Service Plan']:
    r = requests.get(api, params={'$filter': f"serviceName eq '{service}'"})
    print('filter:', service, 'status', r.status_code)
    data = r.json()
    print('count', data.get('Count'))
    if data.get('Items'):
        item = data['Items'][0]
        print('sample skuName:', item.get('skuName'))
        print('sample meterName:', item.get('meterName'))
        print('sample productName:', item.get('productName'))
    print()

print('--- Candidate services containing SQL or App ---')
services = set()
for term in ['SQL', 'App', 'Service', 'Database', 'Web']:
    r = requests.get(api, params={'$filter': f"contains(serviceName,'{term}')"})
    data = r.json()
    for item in data.get('Items', []):
        services.add(item.get('serviceName'))
print(sorted(services))
