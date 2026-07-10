import app

for service, sku, region, hint in [
    ('Managed Disk', 'Premium SSD Managed Disks', 'eastus', None),
    ('Managed Disk', 'Standard SSD Managed Disks', 'eastus', None),
    ('App Service', 'P1v2', 'uksouth', None),
    ('SQL Database', 'GP_Gen5_2', 'centralindia', None),
    ('SQL Database', '36 vCore', 'centralindia', None),
]:
    print('---', service, sku, region)
    match = app.search_prices(service, sku, region, meter_hint=hint)
    print('match', match)
    if match:
        item = match.item
        print('skuName', item.get('skuName'))
        print('meterName', item.get('meterName'))
        print('productName', item.get('productName'))
        print('uom', item.get('unitOfMeasure'))
        print('price', item.get('retailPrice'))
    print()