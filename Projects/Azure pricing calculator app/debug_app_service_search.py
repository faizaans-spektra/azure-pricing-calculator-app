import app
from app import build_odata_filter

service = 'App Service'
sku = 'P1v2'
region = 'uksouth'
filter_values = {
    'serviceName': app.SERVICE_FILTERS.get(service, service),
    'armRegionName': app.normalize_region(region),
    'skuName': sku,
}
print('filter exact:', build_odata_filter(filter_values))
try:
    items = app.query_retail_prices(build_odata_filter(filter_values), max_records=20)
    print('exact count', len(items))
except Exception as e:
    print('exact error', e)
fallback_values = {
    'serviceName': app.SERVICE_FILTERS.get(service, service),
    'armRegionName': app.normalize_region(region),
}
print('filter fallback:', build_odata_filter(fallback_values))
try:
    items = app.query_retail_prices(build_odata_filter(fallback_values), max_records=20)
    print('fallback count', len(items))
    for item in items[:10]:
        print(item.get('skuName'), '|', item.get('meterName'), '|', item.get('productName'), '|', item.get('armRegionName'))
except Exception as e:
    print('fallback error', e)
print('search_prices match:', app.search_prices(service, sku, region, None))
