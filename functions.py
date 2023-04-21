import requests
from dateutil.parser import parse


def get_all_exchange_rates_erapi(src):
    url = f"https://open.er-api.com/v6/latest/{src}"
    data = requests.get(url).json()
    if data["result"] == "success":
        last_updated_datetime = parse(data["time_last_update_utc"])
        exchange_rates = data["rates"]
    return last_updated_datetime, exchange_rates


def convert_currency_erapi(src, dst, amount):
    last_updated_datetime, exchange_rates = get_all_exchange_rates_erapi(src)
    return last_updated_datetime, exchange_rates[dst] * amount