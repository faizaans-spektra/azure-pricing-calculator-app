import app

queries = [
    ('App Service', 'P1v2', 'uksouth'),
    ('App Service', 'P1 v2', 'uksouth'),
    ('App Service', 'P1', 'uksouth'),
    ('SQL Database', 'GP_Gen5_2', 'centralindia'),
    ('SQL Database', '36 vCore', 'centralindia'),
]
for service, sku, region in queries:
    print('---', service, sku, region)
    match = app.search_prices(service, sku, region)
    print('match', match)
    if match:
        print(match.item.get('skuName'), match.item.get('meterName'), match.item.get('productName'), match.item.get('unitOfMeasure'))
    print()