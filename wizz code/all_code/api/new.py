import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': 'id="hWNI32WWbY08l1Arphk2EFho", type="cn"',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-one-session-token': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shop-pay-token': 'eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaWQ6XC9cL3Nob3BpZnlcL1Nob3BcLzkyNTU0NDk0Mjk4IiwibmJmIjoxNzkyMTc5ODAxLCJzZXNzaW9uX3Rva2VuIjoiQUFFQld5Y0M5RnFEU19Lblg0MURKb1gzOF9RcjQwOVZZSnZfMU9fdTlVcURPMm5JSzh6RWpycDNqR0lpUDJzVi1lSy1WSVJPa3V4MmFGeWt2c2R1TndyS3BJQ00xQmxrNXdMVUgtMlVIeUU5UWFiQzJRcEd4dVdVa2x5dkNQRlYteXNOUVg3M29ITkEzNjlhYWVPdTh0by1lYnRMU3dKYzhqelZaSVF2MjROcmoxYU5OcmZrSno3d3VfM0ZMRVFPZF9USkxTMVlZVlB5TkdtRlA4OU94Q25Dc3VJYVJvcm9nMFN6dmV3Iiwic2Vzc2lvbl9jdXN0b21lcl9pZCI6MTA1MDczNjk4NDA5ODYsInNob3BfYWNjb3VudF91dWlkIjoiYTQ2ZWJiODUtNjc0Ny00NzhjLWE3ZmUtOTc5NDBjYzRiMWZmIiwic2hvcF9wYXlfZGF0YSI6IkNBSVNHWGRwZW1GeVpHeDVZWFZ5WVRrNU9VQm5iV0ZwYkM1amIyMGFFaGV3SEtTZEF1YVBZWVVfdkNNM3QwVU9oQ0lRcEc2N2hXZEhSNHluX3BlVURNU3hfempZX01uV0Jrb1NETm9uTXNVV2ZrX19wbHkwUTRDZGwxMEUiLCJjdXN0b21lcl9hdXRoZW50aWNhdGlvbl9hdXRoX3Byb3ZpZGVyIjoibG9naW5fd2l0aF9zaG9wIiwiZXhwIjoxNzkyMTgzNDAxLCJsYW5kaW5nX3BhZ2UiOiJcLyIsIm9yaWdfcmVmZXJyZXIiOiIiLCJtZXJjaGFudF9jb25zZW50IjoiM0FNUC5TIn0.eJ_036fE8fV7VlRQ_VrMQfgnE1KbP_duYqno-fhCrA0',
    'x-shopify-tracking-consent': '3S.AMP',
    'x-shopify-uniquetoken': 'c1e69033-8b91-45e6-8e70-d2adaeca3fe5',
    'x-shopify-visittoken': '9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2',
}

params = {
    'operationName': 'CountryDetails',
}

json_data = {
    'variables': {
        'country': 'US',
    },
    'operationName': 'CountryDetails',
    'id': 'e80d5f5c1e60593716690e3575add0ef2588b89c7ea211e423658d746ee06ffa',
}

response = requests.post(
    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"country":"US"},"operationName":"CountryDetails","id":"e80d5f5c1e60593716690e3575add0ef2588b89c7ea211e423658d746ee06ffa"}'
#response = requests.post(
#    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
#    params=params,
#    cookies=cookies,
#    headers=headers,
#    data=data,
#)




import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': 'id="hWNI32WWbY08l1Arphk2EFho", type="cn"',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-one-session-token': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shop-pay-token': 'eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaWQ6XC9cL3Nob3BpZnlcL1Nob3BcLzkyNTU0NDk0Mjk4IiwibmJmIjoxNzkyMTc5ODAxLCJzZXNzaW9uX3Rva2VuIjoiQUFFQld5Y0M5RnFEU19Lblg0MURKb1gzOF9RcjQwOVZZSnZfMU9fdTlVcURPMm5JSzh6RWpycDNqR0lpUDJzVi1lSy1WSVJPa3V4MmFGeWt2c2R1TndyS3BJQ00xQmxrNXdMVUgtMlVIeUU5UWFiQzJRcEd4dVdVa2x5dkNQRlYteXNOUVg3M29ITkEzNjlhYWVPdTh0by1lYnRMU3dKYzhqelZaSVF2MjROcmoxYU5OcmZrSno3d3VfM0ZMRVFPZF9USkxTMVlZVlB5TkdtRlA4OU94Q25Dc3VJYVJvcm9nMFN6dmV3Iiwic2Vzc2lvbl9jdXN0b21lcl9pZCI6MTA1MDczNjk4NDA5ODYsInNob3BfYWNjb3VudF91dWlkIjoiYTQ2ZWJiODUtNjc0Ny00NzhjLWE3ZmUtOTc5NDBjYzRiMWZmIiwic2hvcF9wYXlfZGF0YSI6IkNBSVNHWGRwZW1GeVpHeDVZWFZ5WVRrNU9VQm5iV0ZwYkM1amIyMGFFaGV3SEtTZEF1YVBZWVVfdkNNM3QwVU9oQ0lRcEc2N2hXZEhSNHluX3BlVURNU3hfempZX01uV0Jrb1NETm9uTXNVV2ZrX19wbHkwUTRDZGwxMEUiLCJjdXN0b21lcl9hdXRoZW50aWNhdGlvbl9hdXRoX3Byb3ZpZGVyIjoibG9naW5fd2l0aF9zaG9wIiwiZXhwIjoxNzkyMTgzNDAxLCJsYW5kaW5nX3BhZ2UiOiJcLyIsIm9yaWdfcmVmZXJyZXIiOiIiLCJtZXJjaGFudF9jb25zZW50IjoiM0FNUC5TIn0.eJ_036fE8fV7VlRQ_VrMQfgnE1KbP_duYqno-fhCrA0',
    'x-shopify-tracking-consent': '3S.AMP',
    'x-shopify-uniquetoken': 'c1e69033-8b91-45e6-8e70-d2adaeca3fe5',
    'x-shopify-visittoken': '9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2',
}

params = {
    'operationName': 'CountryDetails',
}

json_data = {
    'variables': {
        'country': 'SG',
    },
    'operationName': 'CountryDetails',
    'id': 'e80d5f5c1e60593716690e3575add0ef2588b89c7ea211e423658d746ee06ffa',
}

response = requests.post(
    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"country":"SG"},"operationName":"CountryDetails","id":"e80d5f5c1e60593716690e3575add0ef2588b89c7ea211e423658d746ee06ffa"}'
#response = requests.post(
#    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
#    params=params,
#    cookies=cookies,
#    headers=headers,
#    data=data,
#)


import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': 'id="hWNI32WWbY08l1Arphk2EFho", type="cn"',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-one-session-token': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shop-pay-token': 'eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaWQ6XC9cL3Nob3BpZnlcL1Nob3BcLzkyNTU0NDk0Mjk4IiwibmJmIjoxNzkyMTc5ODAxLCJzZXNzaW9uX3Rva2VuIjoiQUFFQld5Y0M5RnFEU19Lblg0MURKb1gzOF9RcjQwOVZZSnZfMU9fdTlVcURPMm5JSzh6RWpycDNqR0lpUDJzVi1lSy1WSVJPa3V4MmFGeWt2c2R1TndyS3BJQ00xQmxrNXdMVUgtMlVIeUU5UWFiQzJRcEd4dVdVa2x5dkNQRlYteXNOUVg3M29ITkEzNjlhYWVPdTh0by1lYnRMU3dKYzhqelZaSVF2MjROcmoxYU5OcmZrSno3d3VfM0ZMRVFPZF9USkxTMVlZVlB5TkdtRlA4OU94Q25Dc3VJYVJvcm9nMFN6dmV3Iiwic2Vzc2lvbl9jdXN0b21lcl9pZCI6MTA1MDczNjk4NDA5ODYsInNob3BfYWNjb3VudF91dWlkIjoiYTQ2ZWJiODUtNjc0Ny00NzhjLWE3ZmUtOTc5NDBjYzRiMWZmIiwic2hvcF9wYXlfZGF0YSI6IkNBSVNHWGRwZW1GeVpHeDVZWFZ5WVRrNU9VQm5iV0ZwYkM1amIyMGFFaGV3SEtTZEF1YVBZWVVfdkNNM3QwVU9oQ0lRcEc2N2hXZEhSNHluX3BlVURNU3hfempZX01uV0Jrb1NETm9uTXNVV2ZrX19wbHkwUTRDZGwxMEUiLCJjdXN0b21lcl9hdXRoZW50aWNhdGlvbl9hdXRoX3Byb3ZpZGVyIjoibG9naW5fd2l0aF9zaG9wIiwiZXhwIjoxNzkyMTgzNDAxLCJsYW5kaW5nX3BhZ2UiOiJcLyIsIm9yaWdfcmVmZXJyZXIiOiIiLCJtZXJjaGFudF9jb25zZW50IjoiM0FNUC5TIn0.eJ_036fE8fV7VlRQ_VrMQfgnE1KbP_duYqno-fhCrA0',
    'x-shopify-tracking-consent': '3S.AMP',
    'x-shopify-uniquetoken': 'c1e69033-8b91-45e6-8e70-d2adaeca3fe5',
    'x-shopify-visittoken': '9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2',
}

params = {
    'operationName': 'Proposal',
}

json_data = {
    'variables': {
        'sessionInput': {
            'sessionToken': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
        },
        'queueToken': 'A4ozW75MkD1GSmUS5g9a5cn6xOeDljXoucpe_fiXXYc4K3qvDx4HMTO3RQxTtLVfBrKi6LtIpaJ_jbJZcB8F8UecGYmbL_SvNRwhO-eH8VRJ8qtF5aD5dmLC1yGiPRfPow==',
        'discounts': {
            'lines': [],
            'acceptUnexpectedDiscounts': True,
        },
        'delivery': {
            'deliveryLines': [
                {
                    'destination': {
                        'partialStreetAddress': {
                            'address1': 'Bijipur Main Road Sundar Nagar',
                            'address2': '',
                            'city': 'Brahmapur',
                            'countryCode': 'IN',
                            'postalCode': '760001',
                            'firstName': 'Subham',
                            'lastName': 'Kumar',
                            'zoneCode': 'OR',
                            'phone': '+917853878533',
                            'oneTimeUse': False,
                        },
                    },
                    'selectedDeliveryStrategy': {
                        'deliveryStrategyMatchingConditions': {
                            'estimatedTimeInTransit': {
                                'any': True,
                            },
                            'shipments': {
                                'any': True,
                            },
                        },
                        'options': {},
                    },
                    'targetMerchandiseLines': {
                        'any': True,
                    },
                    'deliveryMethodTypes': [
                        'SHIPPING',
                    ],
                    'expectedTotalPrice': {
                        'any': True,
                    },
                    'destinationChanged': True,
                },
            ],
            'noDeliveryRequired': [],
            'useProgressiveRates': False,
            'prefetchShippingRatesStrategy': None,
            'interfaceFlow': 'SHOP_PAY',
            'supportsSplitShipping': True,
        },
        'deliveryExpectations': {
            'deliveryExpectationLines': [],
        },
        'merchandise': {
            'merchandiseLines': [
                {
                    'stableId': '9720debd-5883-45ef-bf0d-fdc7d9558d88',
                    'merchandise': {
                        'productVariantReference': {
                            'id': 'gid://shopify/ProductVariantMerchandise/51732384481626',
                            'variantId': 'gid://shopify/ProductVariant/51732384481626',
                            'properties': [],
                            'sellingPlanId': None,
                            'sellingPlanDigest': None,
                        },
                    },
                    'quantity': {
                        'items': {
                            'value': 1,
                        },
                    },
                    'expectedTotalPrice': {
                        'value': {
                            'amount': '4100.00',
                            'currencyCode': 'INR',
                        },
                    },
                    'lineComponentsSource': None,
                    'lineComponents': [],
                },
            ],
        },
        'memberships': {
            'memberships': [],
        },
        'payment': {
            'totalAmount': {
                'any': True,
            },
            'paymentLines': [],
            'billingAddress': {
                'streetAddress': {
                    'address1': 'Bijipur Main Road Sundar Nagar',
                    'city': 'Brahmapur',
                    'countryCode': 'IN',
                    'postalCode': '760001',
                    'firstName': 'Subham',
                    'lastName': 'Kumar',
                    'zoneCode': 'OR',
                    'phone': '+917853878533',
                },
            },
            'allowStoreCredit': False,
        },
        'buyerIdentity': {
            'customer': {
                'presentmentCurrency': 'INR',
                'countryCode': 'IN',
            },
            'email': 'wizardlyaura999@gmail.com',
            'emailChanged': False,
            'phoneCountryCode': 'IN',
            'marketingConsent': [],
            'shopPayOptInPhone': {
                'number': '+917853878533',
                'countryCode': 'IN',
            },
            'shopUserSecureData': 'eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s',
            'prefillSource': 'SHOP_PAY',
            'rememberMe': False,
        },
        'tip': {
            'tipLines': [],
        },
        'poNumber': None,
        'taxes': {
            'proposedAllocations': None,
            'proposedTotalAmount': {
                'value': {
                    'amount': '0',
                    'currencyCode': 'INR',
                },
            },
            'proposedTotalIncludedAmount': None,
            'proposedMixedStateTotalAmount': None,
            'proposedExemptions': [],
        },
        'note': {
            'message': None,
            'customAttributes': [],
        },
        'localizationExtension': {
            'fields': [],
        },
        'nonNegotiableTerms': None,
        'scriptFingerprint': {
            'signature': None,
            'signatureUuid': None,
            'lineItemScriptChanges': [],
            'paymentScriptChanges': [],
            'shippingScriptChanges': [],
        },
        'optionalDuties': {
            'buyerRefusesDuties': False,
        },
        'cartMetafields': [],
    },
    'operationName': 'Proposal',
    'id': '218ca3f4634df050ead785d9692d50bc444d93ef926a6c0d820c1c01a02d474f',
}

response = requests.post(
    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"sessionInput":{"sessionToken":"AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew"},"queueToken":"A4ozW75MkD1GSmUS5g9a5cn6xOeDljXoucpe_fiXXYc4K3qvDx4HMTO3RQxTtLVfBrKi6LtIpaJ_jbJZcB8F8UecGYmbL_SvNRwhO-eH8VRJ8qtF5aD5dmLC1yGiPRfPow==","discounts":{"lines":[],"acceptUnexpectedDiscounts":true},"delivery":{"deliveryLines":[{"destination":{"partialStreetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533","oneTimeUse":false}},"selectedDeliveryStrategy":{"deliveryStrategyMatchingConditions":{"estimatedTimeInTransit":{"any":true},"shipments":{"any":true}},"options":{}},"targetMerchandiseLines":{"any":true},"deliveryMethodTypes":["SHIPPING"],"expectedTotalPrice":{"any":true},"destinationChanged":true}],"noDeliveryRequired":[],"useProgressiveRates":false,"prefetchShippingRatesStrategy":null,"interfaceFlow":"SHOP_PAY","supportsSplitShipping":true},"deliveryExpectations":{"deliveryExpectationLines":[]},"merchandise":{"merchandiseLines":[{"stableId":"9720debd-5883-45ef-bf0d-fdc7d9558d88","merchandise":{"productVariantReference":{"id":"gid://shopify/ProductVariantMerchandise/51732384481626","variantId":"gid://shopify/ProductVariant/51732384481626","properties":[],"sellingPlanId":null,"sellingPlanDigest":null}},"quantity":{"items":{"value":1}},"expectedTotalPrice":{"value":{"amount":"4100.00","currencyCode":"INR"}},"lineComponentsSource":null,"lineComponents":[]}]},"memberships":{"memberships":[]},"payment":{"totalAmount":{"any":true},"paymentLines":[],"billingAddress":{"streetAddress":{"address1":"Bijipur Main Road Sundar Nagar","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533"}},"allowStoreCredit":false},"buyerIdentity":{"customer":{"presentmentCurrency":"INR","countryCode":"IN"},"email":"wizardlyaura999@gmail.com","emailChanged":false,"phoneCountryCode":"IN","marketingConsent":[],"shopPayOptInPhone":{"number":"+917853878533","countryCode":"IN"},"shopUserSecureData":"eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s","prefillSource":"SHOP_PAY","rememberMe":false},"tip":{"tipLines":[]},"poNumber":null,"taxes":{"proposedAllocations":null,"proposedTotalAmount":{"value":{"amount":"0","currencyCode":"INR"}},"proposedTotalIncludedAmount":null,"proposedMixedStateTotalAmount":null,"proposedExemptions":[]},"note":{"message":null,"customAttributes":[]},"localizationExtension":{"fields":[]},"nonNegotiableTerms":null,"scriptFingerprint":{"signature":null,"signatureUuid":null,"lineItemScriptChanges":[],"paymentScriptChanges":[],"shippingScriptChanges":[]},"optionalDuties":{"buyerRefusesDuties":false},"cartMetafields":[]},"operationName":"Proposal","id":"218ca3f4634df050ead785d9692d50bc444d93ef926a6c0d820c1c01a02d474f"}'
#response = requests.post(
#    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
#    params=params,
#    cookies=cookies,
#    headers=headers,
#    data=data,
#)


import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': 'id="hWNI32WWbY08l1Arphk2EFho", type="cn"',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-one-session-token': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shop-pay-token': 'eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaWQ6XC9cL3Nob3BpZnlcL1Nob3BcLzkyNTU0NDk0Mjk4IiwibmJmIjoxNzkyMTc5ODAxLCJzZXNzaW9uX3Rva2VuIjoiQUFFQld5Y0M5RnFEU19Lblg0MURKb1gzOF9RcjQwOVZZSnZfMU9fdTlVcURPMm5JSzh6RWpycDNqR0lpUDJzVi1lSy1WSVJPa3V4MmFGeWt2c2R1TndyS3BJQ00xQmxrNXdMVUgtMlVIeUU5UWFiQzJRcEd4dVdVa2x5dkNQRlYteXNOUVg3M29ITkEzNjlhYWVPdTh0by1lYnRMU3dKYzhqelZaSVF2MjROcmoxYU5OcmZrSno3d3VfM0ZMRVFPZF9USkxTMVlZVlB5TkdtRlA4OU94Q25Dc3VJYVJvcm9nMFN6dmV3Iiwic2Vzc2lvbl9jdXN0b21lcl9pZCI6MTA1MDczNjk4NDA5ODYsInNob3BfYWNjb3VudF91dWlkIjoiYTQ2ZWJiODUtNjc0Ny00NzhjLWE3ZmUtOTc5NDBjYzRiMWZmIiwic2hvcF9wYXlfZGF0YSI6IkNBSVNHWGRwZW1GeVpHeDVZWFZ5WVRrNU9VQm5iV0ZwYkM1amIyMGFFaGV3SEtTZEF1YVBZWVVfdkNNM3QwVU9oQ0lRcEc2N2hXZEhSNHluX3BlVURNU3hfempZX01uV0Jrb1NETm9uTXNVV2ZrX19wbHkwUTRDZGwxMEUiLCJjdXN0b21lcl9hdXRoZW50aWNhdGlvbl9hdXRoX3Byb3ZpZGVyIjoibG9naW5fd2l0aF9zaG9wIiwiZXhwIjoxNzkyMTgzNDAxLCJsYW5kaW5nX3BhZ2UiOiJcLyIsIm9yaWdfcmVmZXJyZXIiOiIiLCJtZXJjaGFudF9jb25zZW50IjoiM0FNUC5TIn0.eJ_036fE8fV7VlRQ_VrMQfgnE1KbP_duYqno-fhCrA0',
    'x-shopify-tracking-consent': '3S.AMP',
    'x-shopify-uniquetoken': 'c1e69033-8b91-45e6-8e70-d2adaeca3fe5',
    'x-shopify-visittoken': '9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2',
}

params = {
    'operationName': 'PostPurchaseData',
}

json_data = {
    'variables': {
        'input': {
            'forShouldRender': {
                'purchaseProposal': {
                    'discounts': {
                        'lines': [],
                        'acceptUnexpectedDiscounts': True,
                    },
                    'delivery': {
                        'deliveryLines': [
                            {
                                'destination': {
                                    'partialStreetAddress': {
                                        'address1': 'Bijipur Main Road Sundar Nagar',
                                        'address2': '',
                                        'city': 'Brahmapur',
                                        'countryCode': 'IN',
                                        'postalCode': '760001',
                                        'firstName': 'Subham',
                                        'lastName': 'Kumar',
                                        'zoneCode': 'OR',
                                        'phone': '+917853878533',
                                        'oneTimeUse': False,
                                    },
                                },
                                'selectedDeliveryStrategy': {
                                    'deliveryStrategyMatchingConditions': {
                                        'estimatedTimeInTransit': {
                                            'any': True,
                                        },
                                        'shipments': {
                                            'any': True,
                                        },
                                    },
                                    'options': {},
                                },
                                'targetMerchandiseLines': {
                                    'any': True,
                                },
                                'deliveryMethodTypes': [
                                    'SHIPPING',
                                ],
                                'expectedTotalPrice': {
                                    'any': True,
                                },
                                'destinationChanged': True,
                            },
                        ],
                        'noDeliveryRequired': [],
                        'useProgressiveRates': False,
                        'prefetchShippingRatesStrategy': None,
                        'interfaceFlow': 'SHOP_PAY',
                        'supportsSplitShipping': True,
                    },
                    'deliveryExpectations': {
                        'deliveryExpectationLines': [],
                    },
                    'merchandise': {
                        'merchandiseLines': [
                            {
                                'stableId': '9720debd-5883-45ef-bf0d-fdc7d9558d88',
                                'merchandise': {
                                    'productVariantReference': {
                                        'id': 'gid://shopify/ProductVariantMerchandise/51732384481626',
                                        'variantId': 'gid://shopify/ProductVariant/51732384481626',
                                        'properties': [],
                                        'sellingPlanId': None,
                                        'sellingPlanDigest': None,
                                    },
                                },
                                'quantity': {
                                    'items': {
                                        'value': 1,
                                    },
                                },
                                'expectedTotalPrice': {
                                    'value': {
                                        'amount': '4100.00',
                                        'currencyCode': 'INR',
                                    },
                                },
                                'lineComponentsSource': None,
                                'lineComponents': [],
                            },
                        ],
                    },
                    'memberships': {
                        'memberships': [],
                    },
                    'payment': {
                        'totalAmount': {
                            'any': True,
                        },
                        'paymentLines': [],
                        'billingAddress': {
                            'streetAddress': {
                                'address1': 'Bijipur Main Road Sundar Nagar',
                                'city': 'Brahmapur',
                                'countryCode': 'IN',
                                'postalCode': '760001',
                                'firstName': 'Subham',
                                'lastName': 'Kumar',
                                'zoneCode': 'OR',
                                'phone': '+917853878533',
                            },
                        },
                        'allowStoreCredit': False,
                    },
                    'buyerIdentity': {
                        'customer': {
                            'presentmentCurrency': 'INR',
                            'countryCode': 'IN',
                        },
                        'email': 'wizardlyaura999@gmail.com',
                        'emailChanged': False,
                        'phoneCountryCode': 'IN',
                        'marketingConsent': [],
                        'shopPayOptInPhone': {
                            'number': '+917853878533',
                            'countryCode': 'IN',
                        },
                        'shopUserSecureData': 'eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s',
                        'prefillSource': 'SHOP_PAY',
                        'rememberMe': False,
                    },
                    'tip': {
                        'tipLines': [],
                    },
                    'poNumber': None,
                    'taxes': {
                        'proposedAllocations': None,
                        'proposedTotalAmount': {
                            'value': {
                                'amount': '0',
                                'currencyCode': 'INR',
                            },
                        },
                        'proposedTotalIncludedAmount': None,
                        'proposedMixedStateTotalAmount': None,
                        'proposedExemptions': [],
                    },
                    'note': {
                        'message': None,
                        'customAttributes': [],
                    },
                    'localizationExtension': {
                        'fields': [],
                    },
                    'nonNegotiableTerms': None,
                    'scriptFingerprint': {
                        'signature': None,
                        'signatureUuid': None,
                        'lineItemScriptChanges': [],
                        'paymentScriptChanges': [],
                        'shippingScriptChanges': [],
                    },
                    'optionalDuties': {
                        'buyerRefusesDuties': False,
                    },
                    'cartMetafields': [],
                },
                'sessionToken': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
            },
        },
    },
    'operationName': 'PostPurchaseData',
    'id': '6e80fbaa48c55e585de6accb0c4efcf5389f92340be06a6c32f0e5ce451de978',
}

response = requests.post(
    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"input":{"forShouldRender":{"purchaseProposal":{"discounts":{"lines":[],"acceptUnexpectedDiscounts":true},"delivery":{"deliveryLines":[{"destination":{"partialStreetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533","oneTimeUse":false}},"selectedDeliveryStrategy":{"deliveryStrategyMatchingConditions":{"estimatedTimeInTransit":{"any":true},"shipments":{"any":true}},"options":{}},"targetMerchandiseLines":{"any":true},"deliveryMethodTypes":["SHIPPING"],"expectedTotalPrice":{"any":true},"destinationChanged":true}],"noDeliveryRequired":[],"useProgressiveRates":false,"prefetchShippingRatesStrategy":null,"interfaceFlow":"SHOP_PAY","supportsSplitShipping":true},"deliveryExpectations":{"deliveryExpectationLines":[]},"merchandise":{"merchandiseLines":[{"stableId":"9720debd-5883-45ef-bf0d-fdc7d9558d88","merchandise":{"productVariantReference":{"id":"gid://shopify/ProductVariantMerchandise/51732384481626","variantId":"gid://shopify/ProductVariant/51732384481626","properties":[],"sellingPlanId":null,"sellingPlanDigest":null}},"quantity":{"items":{"value":1}},"expectedTotalPrice":{"value":{"amount":"4100.00","currencyCode":"INR"}},"lineComponentsSource":null,"lineComponents":[]}]},"memberships":{"memberships":[]},"payment":{"totalAmount":{"any":true},"paymentLines":[],"billingAddress":{"streetAddress":{"address1":"Bijipur Main Road Sundar Nagar","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533"}},"allowStoreCredit":false},"buyerIdentity":{"customer":{"presentmentCurrency":"INR","countryCode":"IN"},"email":"wizardlyaura999@gmail.com","emailChanged":false,"phoneCountryCode":"IN","marketingConsent":[],"shopPayOptInPhone":{"number":"+917853878533","countryCode":"IN"},"shopUserSecureData":"eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s","prefillSource":"SHOP_PAY","rememberMe":false},"tip":{"tipLines":[]},"poNumber":null,"taxes":{"proposedAllocations":null,"proposedTotalAmount":{"value":{"amount":"0","currencyCode":"INR"}},"proposedTotalIncludedAmount":null,"proposedMixedStateTotalAmount":null,"proposedExemptions":[]},"note":{"message":null,"customAttributes":[]},"localizationExtension":{"fields":[]},"nonNegotiableTerms":null,"scriptFingerprint":{"signature":null,"signatureUuid":null,"lineItemScriptChanges":[],"paymentScriptChanges":[],"shippingScriptChanges":[]},"optionalDuties":{"buyerRefusesDuties":false},"cartMetafields":[]},"sessionToken":"AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew"}}},"operationName":"PostPurchaseData","id":"6e80fbaa48c55e585de6accb0c4efcf5389f92340be06a6c32f0e5ce451de978"}'
#response = requests.post(
#    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
#    params=params,
#    cookies=cookies,
#    headers=headers,
#    data=data,
#)



import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': 'id="hWNI32WWbY08l1Arphk2EFho", type="cn"',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-one-session-token': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shop-pay-token': 'eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaWQ6XC9cL3Nob3BpZnlcL1Nob3BcLzkyNTU0NDk0Mjk4IiwibmJmIjoxNzkyMTc5ODAxLCJzZXNzaW9uX3Rva2VuIjoiQUFFQld5Y0M5RnFEU19Lblg0MURKb1gzOF9RcjQwOVZZSnZfMU9fdTlVcURPMm5JSzh6RWpycDNqR0lpUDJzVi1lSy1WSVJPa3V4MmFGeWt2c2R1TndyS3BJQ00xQmxrNXdMVUgtMlVIeUU5UWFiQzJRcEd4dVdVa2x5dkNQRlYteXNOUVg3M29ITkEzNjlhYWVPdTh0by1lYnRMU3dKYzhqelZaSVF2MjROcmoxYU5OcmZrSno3d3VfM0ZMRVFPZF9USkxTMVlZVlB5TkdtRlA4OU94Q25Dc3VJYVJvcm9nMFN6dmV3Iiwic2Vzc2lvbl9jdXN0b21lcl9pZCI6MTA1MDczNjk4NDA5ODYsInNob3BfYWNjb3VudF91dWlkIjoiYTQ2ZWJiODUtNjc0Ny00NzhjLWE3ZmUtOTc5NDBjYzRiMWZmIiwic2hvcF9wYXlfZGF0YSI6IkNBSVNHWGRwZW1GeVpHeDVZWFZ5WVRrNU9VQm5iV0ZwYkM1amIyMGFFaGV3SEtTZEF1YVBZWVVfdkNNM3QwVU9oQ0lRcEc2N2hXZEhSNHluX3BlVURNU3hfempZX01uV0Jrb1NETm9uTXNVV2ZrX19wbHkwUTRDZGwxMEUiLCJjdXN0b21lcl9hdXRoZW50aWNhdGlvbl9hdXRoX3Byb3ZpZGVyIjoibG9naW5fd2l0aF9zaG9wIiwiZXhwIjoxNzkyMTgzNDAxLCJsYW5kaW5nX3BhZ2UiOiJcLyIsIm9yaWdfcmVmZXJyZXIiOiIiLCJtZXJjaGFudF9jb25zZW50IjoiM0FNUC5TIn0.eJ_036fE8fV7VlRQ_VrMQfgnE1KbP_duYqno-fhCrA0',
    'x-shopify-tracking-consent': '3S.AMP',
    'x-shopify-uniquetoken': 'c1e69033-8b91-45e6-8e70-d2adaeca3fe5',
    'x-shopify-visittoken': '9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2',
}

params = {
    'operationName': 'Proposal',
}

json_data = {
    'variables': {
        'sessionInput': {
            'sessionToken': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
        },
        'queueToken': 'A671per85Pbj_0xp8z927AZffPxbSLQMw1sGLBiSXvAYCizbErT6oTLQTFqI5bzgV14u3erk2uFp5bLUkn-ti3e-6BBK1OqmnBIbBr5UXSGA82IknvkjYZSvLJk0ckXBPw==',
        'discounts': {
            'lines': [],
            'acceptUnexpectedDiscounts': True,
        },
        'delivery': {
            'deliveryLines': [
                {
                    'destination': {
                        'partialStreetAddress': {
                            'address1': 'Bijipur Main Road Sundar Nagar',
                            'address2': '',
                            'city': 'Brahmapur',
                            'countryCode': 'IN',
                            'postalCode': '760001',
                            'firstName': 'Subham',
                            'lastName': 'Kumar',
                            'zoneCode': 'OR',
                            'phone': '+917853878533',
                            'oneTimeUse': False,
                        },
                    },
                    'selectedDeliveryStrategy': {
                        'deliveryStrategyMatchingConditions': {
                            'estimatedTimeInTransit': {
                                'any': True,
                            },
                            'shipments': {
                                'any': True,
                            },
                        },
                        'options': {},
                    },
                    'targetMerchandiseLines': {
                        'any': True,
                    },
                    'deliveryMethodTypes': [
                        'SHIPPING',
                    ],
                    'expectedTotalPrice': {
                        'any': True,
                    },
                    'destinationChanged': True,
                },
            ],
            'noDeliveryRequired': [],
            'useProgressiveRates': False,
            'prefetchShippingRatesStrategy': None,
            'interfaceFlow': 'SHOP_PAY',
            'supportsSplitShipping': True,
        },
        'deliveryExpectations': {
            'deliveryExpectationLines': [],
        },
        'merchandise': {
            'merchandiseLines': [
                {
                    'stableId': '9720debd-5883-45ef-bf0d-fdc7d9558d88',
                    'merchandise': {
                        'productVariantReference': {
                            'id': 'gid://shopify/ProductVariantMerchandise/51732384481626',
                            'variantId': 'gid://shopify/ProductVariant/51732384481626',
                            'properties': [],
                            'sellingPlanId': None,
                            'sellingPlanDigest': None,
                        },
                    },
                    'quantity': {
                        'items': {
                            'value': 1,
                        },
                    },
                    'expectedTotalPrice': {
                        'value': {
                            'amount': '4100.00',
                            'currencyCode': 'INR',
                        },
                    },
                    'lineComponentsSource': None,
                    'lineComponents': [],
                },
            ],
        },
        'memberships': {
            'memberships': [],
        },
        'payment': {
            'totalAmount': {
                'any': True,
            },
            'paymentLines': [],
            'billingAddress': {
                'streetAddress': {
                    'address1': 'Bijipur Main Road Sundar Nagar',
                    'city': 'Brahmapur',
                    'countryCode': 'IN',
                    'postalCode': '760001',
                    'firstName': 'Subham',
                    'lastName': 'Kumar',
                    'zoneCode': 'OR',
                    'phone': '+917853878533',
                },
            },
            'allowStoreCredit': False,
        },
        'buyerIdentity': {
            'customer': {
                'presentmentCurrency': 'INR',
                'countryCode': 'IN',
            },
            'email': 'wizardlyaura999@gmail.com',
            'emailChanged': False,
            'phoneCountryCode': 'IN',
            'marketingConsent': [],
            'shopPayOptInPhone': {
                'number': '+917853878533',
                'countryCode': 'IN',
            },
            'shopUserSecureData': 'eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s',
            'prefillSource': 'SHOP_PAY',
            'rememberMe': False,
        },
        'tip': {
            'tipLines': [],
        },
        'poNumber': None,
        'taxes': {
            'proposedAllocations': None,
            'proposedTotalAmount': {
                'value': {
                    'amount': '0',
                    'currencyCode': 'INR',
                },
            },
            'proposedTotalIncludedAmount': None,
            'proposedMixedStateTotalAmount': None,
            'proposedExemptions': [],
        },
        'note': {
            'message': None,
            'customAttributes': [],
        },
        'localizationExtension': {
            'fields': [],
        },
        'nonNegotiableTerms': None,
        'scriptFingerprint': {
            'signature': None,
            'signatureUuid': None,
            'lineItemScriptChanges': [],
            'paymentScriptChanges': [],
            'shippingScriptChanges': [],
        },
        'optionalDuties': {
            'buyerRefusesDuties': False,
        },
        'cartMetafields': [],
    },
    'operationName': 'Proposal',
    'id': '218ca3f4634df050ead785d9692d50bc444d93ef926a6c0d820c1c01a02d474f',
}

response = requests.post(
    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"sessionInput":{"sessionToken":"AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew"},"queueToken":"A671per85Pbj_0xp8z927AZffPxbSLQMw1sGLBiSXvAYCizbErT6oTLQTFqI5bzgV14u3erk2uFp5bLUkn-ti3e-6BBK1OqmnBIbBr5UXSGA82IknvkjYZSvLJk0ckXBPw==","discounts":{"lines":[],"acceptUnexpectedDiscounts":true},"delivery":{"deliveryLines":[{"destination":{"partialStreetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533","oneTimeUse":false}},"selectedDeliveryStrategy":{"deliveryStrategyMatchingConditions":{"estimatedTimeInTransit":{"any":true},"shipments":{"any":true}},"options":{}},"targetMerchandiseLines":{"any":true},"deliveryMethodTypes":["SHIPPING"],"expectedTotalPrice":{"any":true},"destinationChanged":true}],"noDeliveryRequired":[],"useProgressiveRates":false,"prefetchShippingRatesStrategy":null,"interfaceFlow":"SHOP_PAY","supportsSplitShipping":true},"deliveryExpectations":{"deliveryExpectationLines":[]},"merchandise":{"merchandiseLines":[{"stableId":"9720debd-5883-45ef-bf0d-fdc7d9558d88","merchandise":{"productVariantReference":{"id":"gid://shopify/ProductVariantMerchandise/51732384481626","variantId":"gid://shopify/ProductVariant/51732384481626","properties":[],"sellingPlanId":null,"sellingPlanDigest":null}},"quantity":{"items":{"value":1}},"expectedTotalPrice":{"value":{"amount":"4100.00","currencyCode":"INR"}},"lineComponentsSource":null,"lineComponents":[]}]},"memberships":{"memberships":[]},"payment":{"totalAmount":{"any":true},"paymentLines":[],"billingAddress":{"streetAddress":{"address1":"Bijipur Main Road Sundar Nagar","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533"}},"allowStoreCredit":false},"buyerIdentity":{"customer":{"presentmentCurrency":"INR","countryCode":"IN"},"email":"wizardlyaura999@gmail.com","emailChanged":false,"phoneCountryCode":"IN","marketingConsent":[],"shopPayOptInPhone":{"number":"+917853878533","countryCode":"IN"},"shopUserSecureData":"eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s","prefillSource":"SHOP_PAY","rememberMe":false},"tip":{"tipLines":[]},"poNumber":null,"taxes":{"proposedAllocations":null,"proposedTotalAmount":{"value":{"amount":"0","currencyCode":"INR"}},"proposedTotalIncludedAmount":null,"proposedMixedStateTotalAmount":null,"proposedExemptions":[]},"note":{"message":null,"customAttributes":[]},"localizationExtension":{"fields":[]},"nonNegotiableTerms":null,"scriptFingerprint":{"signature":null,"signatureUuid":null,"lineItemScriptChanges":[],"paymentScriptChanges":[],"shippingScriptChanges":[]},"optionalDuties":{"buyerRefusesDuties":false},"cartMetafields":[]},"operationName":"Proposal","id":"218ca3f4634df050ead785d9692d50bc444d93ef926a6c0d820c1c01a02d474f"}'
#response = requests.post(
#    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
#    params=params,
#    cookies=cookies,
#    headers=headers,
#    data=data,
#)



import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shopify-tracking-consent': '3S.AMP',
}

params = {
    'operationName': 'CreditCardCreate',
}

json_data = {
    'variables': {
        'billingAddress': {
            'firstName': 'Subham',
            'lastName': 'Kumar',
            'address1': 'Bijipur Main Road Sundar Nagar',
            'city': 'Brahmapur',
            'countryCode': 'IN',
            'zoneCode': 'OR',
            'zip': '760001',
            'phone': '+917853878533',
        },
        'origin': 'checkout_one',
        'sessionId': 'west-b05ed2018457ee6286928f1dda8caccc',
        'nickname': None,
        'checkoutContext': {
            'checkoutIdentifier': 'daadf5d473ea94fde5b8c3a5893e2c72',
            'checkoutVersion': 'checkout_one',
            'shopId': '92554494298',
            'shopifyDomain': '4s0wfh-i6.myshopify.com',
        },
    },
    'operationName': 'CreditCardCreate',
    'query': 'mutation CreditCardCreate($billingAddress:AddressInput!,$origin:String!,$sessionId:ID!,$nickname:String,$checkoutContext:CheckoutContextInput!){creditCardCreate(billingAddress:$billingAddress origin:$origin sessionId:$sessionId nickname:$nickname checkoutContext:$checkoutContext){creditCard{...CreditCardFragment __typename}threeDSecureAuthenticationRequest{redirectUrl verificationId __typename}userErrors{field message __typename}__typename}}fragment CreditCardFragment on CreditCard{bank brand expired expiring expiryMonth expiryYear funding id uuid lastDigits lastUsedAt name nickname preferred supportsInstallmentsInterestLoan supportsInstallmentsSplitPayLoan installmentsInterestLoanNotSupportedReason installmentsSplitPayLoanNotSupportedReason verified billingAddressValid billingAddress{addressLineComponents{additionalInformation district streetName streetNumber subdistrict __typename}fields{key value __typename}__typename}__typename}',
}

response = requests.post('https://shop.app/pay/users/graphql', params=params, cookies=cookies, headers=headers, json=json_data)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"billingAddress":{"firstName":"Subham","lastName":"Kumar","address1":"Bijipur Main Road Sundar Nagar","city":"Brahmapur","countryCode":"IN","zoneCode":"OR","zip":"760001","phone":"+917853878533"},"origin":"checkout_one","sessionId":"west-b05ed2018457ee6286928f1dda8caccc","nickname":null,"checkoutContext":{"checkoutIdentifier":"daadf5d473ea94fde5b8c3a5893e2c72","checkoutVersion":"checkout_one","shopId":"92554494298","shopifyDomain":"4s0wfh-i6.myshopify.com"}},"operationName":"CreditCardCreate","query":"mutation CreditCardCreate($billingAddress:AddressInput!,$origin:String!,$sessionId:ID!,$nickname:String,$checkoutContext:CheckoutContextInput!){creditCardCreate(billingAddress:$billingAddress origin:$origin sessionId:$sessionId nickname:$nickname checkoutContext:$checkoutContext){creditCard{...CreditCardFragment __typename}threeDSecureAuthenticationRequest{redirectUrl verificationId __typename}userErrors{field message __typename}__typename}}fragment CreditCardFragment on CreditCard{bank brand expired expiring expiryMonth expiryYear funding id uuid lastDigits lastUsedAt name nickname preferred supportsInstallmentsInterestLoan supportsInstallmentsSplitPayLoan installmentsInterestLoanNotSupportedReason installmentsSplitPayLoanNotSupportedReason verified billingAddressValid billingAddress{addressLineComponents{additionalInformation district streetName streetNumber subdistrict __typename}fields{key value __typename}__typename}__typename}"}'
#response = requests.post('https://shop.app/pay/users/graphql', params=params, cookies=cookies, headers=headers, data=data)



import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shopify-tracking-consent': '3S.AMP',
}

params = {
    'operationName': 'ShopPayCheckoutSession',
}

json_data = {
    'variables': {
        'checkoutContextInput': {
            'checkoutVersion': 'checkout_one',
            'checkoutIdentifier': 'daadf5d473ea94fde5b8c3a5893e2c72',
            'shopifyDomain': '4s0wfh-i6.myshopify.com',
            'shopId': '92554494298',
        },
        'shopifyDomain': '4s0wfh-i6.myshopify.com',
    },
    'operationName': 'ShopPayCheckoutSession',
    'query': 'query ShopPayCheckoutSession($checkoutContextInput:CheckoutContextInput!,$shopifyDomain:String!,$redirectSource:String){checkoutSession(checkoutContextInput:$checkoutContextInput redirectSource:$redirectSource){session{unverifiedEnrollment __typename}user{publicId email phone phoneCountryCode addresses{...ShippingAddressFragment __typename}paymentMethods{...on CreditCard{...CreditCardFragment __typename}...on PaymentMethod{id paymentMethod paymentMethodName paymentAttributes lastUsedAt __typename}__typename}wallet{latestDiscount(shopifyDomain:$shopifyDomain){id shopifyDomain code redeemedAt __typename}__typename}installmentsRejected preselectSpiForReturningBuyer newUser shopAccountUuid enabledFlags installmentsPrequalification{prequalifiedAmount{value currency __typename}expiredAt __typename}installmentCredential{outcome requiresAdditionalInformation countryCode newUser __typename}experiments __typename}secureData spiServiceAvailable paymentMethodRequirementRemovalVariant paymentMethodRequirementRemovalChallenge selectedPaymentMethodId selectedPaymentMethodOption __typename}userPrivacySettings{...UserPrivacySettingsFragment __typename}}fragment ShippingAddressFragment on Address{addressLineComponents{additionalInformation district streetName streetNumber subdistrict __typename}fields{key value __typename}id uuid lastUsedAt valid userPreferred explicitlyPreferred __typename}fragment CreditCardFragment on CreditCard{bank brand expired expiring expiryMonth expiryYear funding id uuid lastDigits lastUsedAt name nickname preferred supportsInstallmentsInterestLoan supportsInstallmentsSplitPayLoan installmentsInterestLoanNotSupportedReason installmentsSplitPayLoanNotSupportedReason verified billingAddressValid billingAddress{addressLineComponents{additionalInformation district streetName streetNumber subdistrict __typename}fields{key value __typename}__typename}__typename}fragment UserPrivacySettingsFragment on UserPrivacySettings{dataSharingOptOut trackingConsentHeader consent{analytics{consented providedAt isExpired defaultConsented __typename}marketing{consented providedAt isExpired defaultConsented __typename}displayBanner __typename}__typename}',
}

response = requests.post('https://shop.app/pay/users/graphql', params=params, cookies=cookies, headers=headers, json=json_data)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"checkoutContextInput":{"checkoutVersion":"checkout_one","checkoutIdentifier":"daadf5d473ea94fde5b8c3a5893e2c72","shopifyDomain":"4s0wfh-i6.myshopify.com","shopId":"92554494298"},"shopifyDomain":"4s0wfh-i6.myshopify.com"},"operationName":"ShopPayCheckoutSession","query":"query ShopPayCheckoutSession($checkoutContextInput:CheckoutContextInput!,$shopifyDomain:String!,$redirectSource:String){checkoutSession(checkoutContextInput:$checkoutContextInput redirectSource:$redirectSource){session{unverifiedEnrollment __typename}user{publicId email phone phoneCountryCode addresses{...ShippingAddressFragment __typename}paymentMethods{...on CreditCard{...CreditCardFragment __typename}...on PaymentMethod{id paymentMethod paymentMethodName paymentAttributes lastUsedAt __typename}__typename}wallet{latestDiscount(shopifyDomain:$shopifyDomain){id shopifyDomain code redeemedAt __typename}__typename}installmentsRejected preselectSpiForReturningBuyer newUser shopAccountUuid enabledFlags installmentsPrequalification{prequalifiedAmount{value currency __typename}expiredAt __typename}installmentCredential{outcome requiresAdditionalInformation countryCode newUser __typename}experiments __typename}secureData spiServiceAvailable paymentMethodRequirementRemovalVariant paymentMethodRequirementRemovalChallenge selectedPaymentMethodId selectedPaymentMethodOption __typename}userPrivacySettings{...UserPrivacySettingsFragment __typename}}fragment ShippingAddressFragment on Address{addressLineComponents{additionalInformation district streetName streetNumber subdistrict __typename}fields{key value __typename}id uuid lastUsedAt valid userPreferred explicitlyPreferred __typename}fragment CreditCardFragment on CreditCard{bank brand expired expiring expiryMonth expiryYear funding id uuid lastDigits lastUsedAt name nickname preferred supportsInstallmentsInterestLoan supportsInstallmentsSplitPayLoan installmentsInterestLoanNotSupportedReason installmentsSplitPayLoanNotSupportedReason verified billingAddressValid billingAddress{addressLineComponents{additionalInformation district streetName streetNumber subdistrict __typename}fields{key value __typename}__typename}__typename}fragment UserPrivacySettingsFragment on UserPrivacySettings{dataSharingOptOut trackingConsentHeader consent{analytics{consented providedAt isExpired defaultConsented __typename}marketing{consented providedAt isExpired defaultConsented __typename}displayBanner __typename}__typename}"}'
#response = requests.post('https://shop.app/pay/users/graphql', params=params, cookies=cookies, headers=headers, data=data)



import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': 'id="hWNI32WWbY08l1Arphk2EFho", type="cn"',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-one-session-token': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shop-pay-token': 'eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaWQ6XC9cL3Nob3BpZnlcL1Nob3BcLzkyNTU0NDk0Mjk4IiwibmJmIjoxNzkyMTc5ODAxLCJzZXNzaW9uX3Rva2VuIjoiQUFFQld5Y0M5RnFEU19Lblg0MURKb1gzOF9RcjQwOVZZSnZfMU9fdTlVcURPMm5JSzh6RWpycDNqR0lpUDJzVi1lSy1WSVJPa3V4MmFGeWt2c2R1TndyS3BJQ00xQmxrNXdMVUgtMlVIeUU5UWFiQzJRcEd4dVdVa2x5dkNQRlYteXNOUVg3M29ITkEzNjlhYWVPdTh0by1lYnRMU3dKYzhqelZaSVF2MjROcmoxYU5OcmZrSno3d3VfM0ZMRVFPZF9USkxTMVlZVlB5TkdtRlA4OU94Q25Dc3VJYVJvcm9nMFN6dmV3Iiwic2Vzc2lvbl9jdXN0b21lcl9pZCI6MTA1MDczNjk4NDA5ODYsInNob3BfYWNjb3VudF91dWlkIjoiYTQ2ZWJiODUtNjc0Ny00NzhjLWE3ZmUtOTc5NDBjYzRiMWZmIiwic2hvcF9wYXlfZGF0YSI6IkNBSVNHWGRwZW1GeVpHeDVZWFZ5WVRrNU9VQm5iV0ZwYkM1amIyMGFFaGV3SEtTZEF1YVBZWVVfdkNNM3QwVU9oQ0lRcEc2N2hXZEhSNHluX3BlVURNU3hfempZX01uV0Jrb1NETm9uTXNVV2ZrX19wbHkwUTRDZGwxMEUiLCJjdXN0b21lcl9hdXRoZW50aWNhdGlvbl9hdXRoX3Byb3ZpZGVyIjoibG9naW5fd2l0aF9zaG9wIiwiZXhwIjoxNzkyMTgzNDAxLCJsYW5kaW5nX3BhZ2UiOiJcLyIsIm9yaWdfcmVmZXJyZXIiOiIiLCJtZXJjaGFudF9jb25zZW50IjoiM0FNUC5TIn0.eJ_036fE8fV7VlRQ_VrMQfgnE1KbP_duYqno-fhCrA0',
    'x-shopify-tracking-consent': '3S.AMP',
    'x-shopify-uniquetoken': 'c1e69033-8b91-45e6-8e70-d2adaeca3fe5',
    'x-shopify-visittoken': '9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2',
}

params = {
    'operationName': 'Proposal',
}

json_data = {
    'variables': {
        'sessionInput': {
            'sessionToken': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
        },
        'queueToken': 'Ax8rcSsaKIuHr7YRnyqbmoJ6ypEQqQychKUTQ1jIqb0_0FVKZVeHiVsHWsYLuEeBSSxzfPj_V8bl9EBRQaNyxbpsaifLa9VtbZYR7i0TS1YYDlkDFHRY0f2kjyOFi3TC4g==',
        'discounts': {
            'lines': [],
            'acceptUnexpectedDiscounts': True,
        },
        'delivery': {
            'deliveryLines': [
                {
                    'destination': {
                        'partialStreetAddress': {
                            'address1': 'Bijipur Main Road Sundar Nagar',
                            'address2': '',
                            'city': 'Brahmapur',
                            'countryCode': 'IN',
                            'postalCode': '760001',
                            'firstName': 'Subham',
                            'lastName': 'Kumar',
                            'zoneCode': 'OR',
                            'phone': '+917853878533',
                            'oneTimeUse': False,
                        },
                    },
                    'selectedDeliveryStrategy': {
                        'deliveryStrategyByHandle': {
                            'handle': 'daadf5d473ea94fde5b8c3a5893e2c72-1857f5edbd56cb87c7e3af188778f2e4',
                            'customDeliveryRate': False,
                        },
                        'options': {
                            'phone': '+917853878533',
                        },
                    },
                    'targetMerchandiseLines': {
                        'lines': [
                            {
                                'stableId': '9720debd-5883-45ef-bf0d-fdc7d9558d88',
                            },
                        ],
                    },
                    'deliveryMethodTypes': [
                        'SHIPPING',
                    ],
                    'expectedTotalPrice': {
                        'value': {
                            'amount': '1700.00',
                            'currencyCode': 'INR',
                        },
                    },
                    'destinationChanged': False,
                },
            ],
            'noDeliveryRequired': [],
            'useProgressiveRates': False,
            'prefetchShippingRatesStrategy': None,
            'interfaceFlow': 'SHOP_PAY',
            'supportsSplitShipping': True,
        },
        'deliveryExpectations': {
            'deliveryExpectationLines': [
                {
                    'signedHandle': 'SfRTAIzncThVQ2SBc28YsiRKifiGdhaic70IqA0UJyS0ALr+3gY9fux/1btN5PMaq4QdWjVUm/qPO52EvT8hvi9QL/6QKFrpu2SOHcIbkAaSoeQTiK/r8F9ldXhzGxuSFWyEuzPtKUg0EA0eRI+TcYx2q45QWSFZPKz6Qh+Te+kzDXoFBYR1WaKUUdAppZZZKq7AYpJQT9KwwPexXp8TC2DvDfqS5j4k3igUwX8+Q4iJBKTNfXxPJWn5lqDs7N48shcY/qVNBRp9dKA7xD0tsSyO3wqEHhtRYvJXP4fRVNObahW4v1DSkyg2B8C2ESFzRP48oAOfPXJTeXSs2NYeNh204S0zn/hmPRTKWqYYBxnZPXavYxcBwlKBtA8tW2Nl25VND6fOYXqsyBWI3D8KreJUisb9Fz+m+LRZZwj9ZKkfIeeKD7ez/Dt1yZpvdqAS4kdtyr79XLI6xpOmGRf5JyY/qyjLv9yo0tV+1ukq9BNCe8Ru0KyANMfaXhi9JhA25ICza9iMTCxozkw4A1ZJpjxIWS54ufGoZckgphran+jN6R8WwNawv49g6rsdxwFH5N+DvIcopgiiqZ8jH8+ymOPQ+Uyw9Emyildzbm8/r/6Sr3fqXq3Vt7bq9MxSNJNaI1eHh1vgq35tGHQe9M0dSF7QUMaegJomJSyxYeWIHuzn3l9qsqmnaC0d4JWfrOhQKxKXqN48tc8PsBpMnxzKxX99eQWh2soDtVozZZ3+72L9yqWtWSFJWhc1qjGqHwWkwDSibayDi7FFYEhE3YIkqEqySzZWoRq38HEIhFn1crB5+eiBhGcwwTdrLurbG/1DK6K3dA/H1N9zLHjLBxxt5Bu024gjiIRpBKbQwh0Yh1sAnUFwrWwrOPjliAf6OWmIbOSvaIBn7BBBs+hEvnqJKIQdSdwY2lAcNjlK/zVmQLNYXfFJXSX4o+Y9omAlUXuM/fBvnU3pCaKd7UCFoG6SlJ8U6pvXDZ9FboOTUBlDSnHRApZoHoBO0kl/h97wJXnxEV0B+/DuFKzHFRjx/Tzvc8hq4BdYZBuMN0NOAUaedAky3XiKcihyzQ0joilAkp2ERgkOoowyT91u3w53aOEusE4PfMNd0YJNwJo6HKc3cVpRBSxwA91nmpg7giHnrviMDR5cD/hSAdpOklIaLBlRRHceMSfBLmsDgcH5okB/nLQrU6KzQL+xwUU/KtuCXkG/y2WW2tYB4U9frx/5CMGkdmOso+U581GAvWl+jmMQQLChb0qldwsiy+H9Q03VxGeebMRQQvaZQ4r1Jvkz5JEnNQeM/L8Sc6dUDswpmWomP0b7/Kh7uWN7AIZaWY2wbUQGq2Vf5KeqqgUfPJ4opsAsWr9UvWbZlSy+ctS21zD0rHDTaBmIXnpNSZ+lQhr7K+ee2Q2a3k7EtNrKlLDmE2iJ4mxpkBD5OfRZoMujrnAn/eCmPGmRgLt4CAp9UBnoKX+w3mBXbLeH7RlWq/j9rakazlxuzXo6CxPs/iYu/LJZ5E6yn2p6zSrT3MNOPn7nQbH0--uLG1E+I2ICkHKmLb--ALxiIbboyrxBS52l3Hq3SA==',
                },
            ],
        },
        'merchandise': {
            'merchandiseLines': [
                {
                    'stableId': '9720debd-5883-45ef-bf0d-fdc7d9558d88',
                    'merchandise': {
                        'productVariantReference': {
                            'id': 'gid://shopify/ProductVariantMerchandise/51732384481626',
                            'variantId': 'gid://shopify/ProductVariant/51732384481626',
                            'properties': [],
                            'sellingPlanId': None,
                            'sellingPlanDigest': None,
                        },
                    },
                    'quantity': {
                        'items': {
                            'value': 1,
                        },
                    },
                    'expectedTotalPrice': {
                        'value': {
                            'amount': '4100.00',
                            'currencyCode': 'INR',
                        },
                    },
                    'lineComponentsSource': None,
                    'lineComponents': [],
                },
            ],
        },
        'memberships': {
            'memberships': [],
        },
        'payment': {
            'totalAmount': {
                'any': True,
            },
            'paymentLines': [],
            'billingAddress': {
                'streetAddress': {
                    'address1': 'Bijipur Main Road Sundar Nagar',
                    'address2': '',
                    'city': 'Brahmapur',
                    'countryCode': 'IN',
                    'postalCode': '760001',
                    'firstName': 'Subham',
                    'lastName': 'Kumar',
                    'zoneCode': 'OR',
                    'phone': '+917853878533',
                },
            },
            'creditCardBin': '40089500',
            'allowStoreCredit': False,
        },
        'buyerIdentity': {
            'customer': {
                'presentmentCurrency': 'INR',
                'countryCode': 'IN',
            },
            'email': 'wizardlyaura999@gmail.com',
            'emailChanged': False,
            'phoneCountryCode': 'IN',
            'marketingConsent': [
                {
                    'email': {
                        'consentState': 'DECLINED',
                        'value': 'wizardlyaura999@gmail.com',
                    },
                },
            ],
            'shopPayOptInPhone': {
                'number': '+917853878533',
                'countryCode': 'IN',
            },
            'shopUserSecureData': 'eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s',
            'prefillSource': 'SHOP_PAY',
            'rememberMe': False,
        },
        'tip': {
            'tipLines': [],
        },
        'taxes': {
            'proposedAllocations': None,
            'proposedTotalAmount': {
                'value': {
                    'amount': '0',
                    'currencyCode': 'INR',
                },
            },
            'proposedTotalIncludedAmount': None,
            'proposedMixedStateTotalAmount': None,
            'proposedExemptions': [],
        },
        'note': {
            'message': None,
            'customAttributes': [],
        },
        'localizationExtension': {
            'fields': [],
        },
        'nonNegotiableTerms': None,
        'scriptFingerprint': {
            'signature': None,
            'signatureUuid': None,
            'lineItemScriptChanges': [],
            'paymentScriptChanges': [],
            'shippingScriptChanges': [],
        },
        'optionalDuties': {
            'buyerRefusesDuties': False,
        },
        'cartMetafields': [],
    },
    'operationName': 'Proposal',
    'id': '218ca3f4634df050ead785d9692d50bc444d93ef926a6c0d820c1c01a02d474f',
}

response = requests.post(
    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"sessionInput":{"sessionToken":"AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew"},"queueToken":"Ax8rcSsaKIuHr7YRnyqbmoJ6ypEQqQychKUTQ1jIqb0_0FVKZVeHiVsHWsYLuEeBSSxzfPj_V8bl9EBRQaNyxbpsaifLa9VtbZYR7i0TS1YYDlkDFHRY0f2kjyOFi3TC4g==","discounts":{"lines":[],"acceptUnexpectedDiscounts":true},"delivery":{"deliveryLines":[{"destination":{"partialStreetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533","oneTimeUse":false}},"selectedDeliveryStrategy":{"deliveryStrategyByHandle":{"handle":"daadf5d473ea94fde5b8c3a5893e2c72-1857f5edbd56cb87c7e3af188778f2e4","customDeliveryRate":false},"options":{"phone":"+917853878533"}},"targetMerchandiseLines":{"lines":[{"stableId":"9720debd-5883-45ef-bf0d-fdc7d9558d88"}]},"deliveryMethodTypes":["SHIPPING"],"expectedTotalPrice":{"value":{"amount":"1700.00","currencyCode":"INR"}},"destinationChanged":false}],"noDeliveryRequired":[],"useProgressiveRates":false,"prefetchShippingRatesStrategy":null,"interfaceFlow":"SHOP_PAY","supportsSplitShipping":true},"deliveryExpectations":{"deliveryExpectationLines":[{"signedHandle":"SfRTAIzncThVQ2SBc28YsiRKifiGdhaic70IqA0UJyS0ALr+3gY9fux/1btN5PMaq4QdWjVUm/qPO52EvT8hvi9QL/6QKFrpu2SOHcIbkAaSoeQTiK/r8F9ldXhzGxuSFWyEuzPtKUg0EA0eRI+TcYx2q45QWSFZPKz6Qh+Te+kzDXoFBYR1WaKUUdAppZZZKq7AYpJQT9KwwPexXp8TC2DvDfqS5j4k3igUwX8+Q4iJBKTNfXxPJWn5lqDs7N48shcY/qVNBRp9dKA7xD0tsSyO3wqEHhtRYvJXP4fRVNObahW4v1DSkyg2B8C2ESFzRP48oAOfPXJTeXSs2NYeNh204S0zn/hmPRTKWqYYBxnZPXavYxcBwlKBtA8tW2Nl25VND6fOYXqsyBWI3D8KreJUisb9Fz+m+LRZZwj9ZKkfIeeKD7ez/Dt1yZpvdqAS4kdtyr79XLI6xpOmGRf5JyY/qyjLv9yo0tV+1ukq9BNCe8Ru0KyANMfaXhi9JhA25ICza9iMTCxozkw4A1ZJpjxIWS54ufGoZckgphran+jN6R8WwNawv49g6rsdxwFH5N+DvIcopgiiqZ8jH8+ymOPQ+Uyw9Emyildzbm8/r/6Sr3fqXq3Vt7bq9MxSNJNaI1eHh1vgq35tGHQe9M0dSF7QUMaegJomJSyxYeWIHuzn3l9qsqmnaC0d4JWfrOhQKxKXqN48tc8PsBpMnxzKxX99eQWh2soDtVozZZ3+72L9yqWtWSFJWhc1qjGqHwWkwDSibayDi7FFYEhE3YIkqEqySzZWoRq38HEIhFn1crB5+eiBhGcwwTdrLurbG/1DK6K3dA/H1N9zLHjLBxxt5Bu024gjiIRpBKbQwh0Yh1sAnUFwrWwrOPjliAf6OWmIbOSvaIBn7BBBs+hEvnqJKIQdSdwY2lAcNjlK/zVmQLNYXfFJXSX4o+Y9omAlUXuM/fBvnU3pCaKd7UCFoG6SlJ8U6pvXDZ9FboOTUBlDSnHRApZoHoBO0kl/h97wJXnxEV0B+/DuFKzHFRjx/Tzvc8hq4BdYZBuMN0NOAUaedAky3XiKcihyzQ0joilAkp2ERgkOoowyT91u3w53aOEusE4PfMNd0YJNwJo6HKc3cVpRBSxwA91nmpg7giHnrviMDR5cD/hSAdpOklIaLBlRRHceMSfBLmsDgcH5okB/nLQrU6KzQL+xwUU/KtuCXkG/y2WW2tYB4U9frx/5CMGkdmOso+U581GAvWl+jmMQQLChb0qldwsiy+H9Q03VxGeebMRQQvaZQ4r1Jvkz5JEnNQeM/L8Sc6dUDswpmWomP0b7/Kh7uWN7AIZaWY2wbUQGq2Vf5KeqqgUfPJ4opsAsWr9UvWbZlSy+ctS21zD0rHDTaBmIXnpNSZ+lQhr7K+ee2Q2a3k7EtNrKlLDmE2iJ4mxpkBD5OfRZoMujrnAn/eCmPGmRgLt4CAp9UBnoKX+w3mBXbLeH7RlWq/j9rakazlxuzXo6CxPs/iYu/LJZ5E6yn2p6zSrT3MNOPn7nQbH0--uLG1E+I2ICkHKmLb--ALxiIbboyrxBS52l3Hq3SA=="}]},"merchandise":{"merchandiseLines":[{"stableId":"9720debd-5883-45ef-bf0d-fdc7d9558d88","merchandise":{"productVariantReference":{"id":"gid://shopify/ProductVariantMerchandise/51732384481626","variantId":"gid://shopify/ProductVariant/51732384481626","properties":[],"sellingPlanId":null,"sellingPlanDigest":null}},"quantity":{"items":{"value":1}},"expectedTotalPrice":{"value":{"amount":"4100.00","currencyCode":"INR"}},"lineComponentsSource":null,"lineComponents":[]}]},"memberships":{"memberships":[]},"payment":{"totalAmount":{"any":true},"paymentLines":[],"billingAddress":{"streetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533"}},"creditCardBin":"40089500","allowStoreCredit":false},"buyerIdentity":{"customer":{"presentmentCurrency":"INR","countryCode":"IN"},"email":"wizardlyaura999@gmail.com","emailChanged":false,"phoneCountryCode":"IN","marketingConsent":[{"email":{"consentState":"DECLINED","value":"wizardlyaura999@gmail.com"}}],"shopPayOptInPhone":{"number":"+917853878533","countryCode":"IN"},"shopUserSecureData":"eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s","prefillSource":"SHOP_PAY","rememberMe":false},"tip":{"tipLines":[]},"taxes":{"proposedAllocations":null,"proposedTotalAmount":{"value":{"amount":"0","currencyCode":"INR"}},"proposedTotalIncludedAmount":null,"proposedMixedStateTotalAmount":null,"proposedExemptions":[]},"note":{"message":null,"customAttributes":[]},"localizationExtension":{"fields":[]},"nonNegotiableTerms":null,"scriptFingerprint":{"signature":null,"signatureUuid":null,"lineItemScriptChanges":[],"paymentScriptChanges":[],"shippingScriptChanges":[]},"optionalDuties":{"buyerRefusesDuties":false},"cartMetafields":[]},"operationName":"Proposal","id":"218ca3f4634df050ead785d9692d50bc444d93ef926a6c0d820c1c01a02d474f"}'
#response = requests.post(
#    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
#    params=params,
#    cookies=cookies,
#    headers=headers,
#    data=data,
#)



import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shopify-tracking-consent': '3S.AMP',
}

params = {
    'operationName': 'CheckoutSessionUpdateSelections',
}

json_data = {
    'variables': {
        'checkoutContextInput': {
            'checkoutIdentifier': 'daadf5d473ea94fde5b8c3a5893e2c72',
            'checkoutVersion': 'checkout_one',
            'shopId': '92554494298',
            'shopifyDomain': '4s0wfh-i6.myshopify.com',
        },
        'selectedPaymentMethodId': '21c88226-4b75-4ad5-b7d4-94f3bae12d55',
        'selectedPaymentMethodOption': 'SHOP_PAY',
    },
    'operationName': 'CheckoutSessionUpdateSelections',
    'query': 'mutation CheckoutSessionUpdateSelections($checkoutContextInput:CheckoutContextInput!,$selectedPaymentMethodId:String,$selectedPaymentMethodOption:String){checkoutSessionUpdateSelections(checkoutContextInput:$checkoutContextInput selectedPaymentMethodId:$selectedPaymentMethodId selectedPaymentMethodOption:$selectedPaymentMethodOption){userErrors{message field __typename}__typename}}',
}

response = requests.post('https://shop.app/pay/users/graphql', params=params, cookies=cookies, headers=headers, json=json_data)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"checkoutContextInput":{"checkoutIdentifier":"daadf5d473ea94fde5b8c3a5893e2c72","checkoutVersion":"checkout_one","shopId":"92554494298","shopifyDomain":"4s0wfh-i6.myshopify.com"},"selectedPaymentMethodId":"21c88226-4b75-4ad5-b7d4-94f3bae12d55","selectedPaymentMethodOption":"SHOP_PAY"},"operationName":"CheckoutSessionUpdateSelections","query":"mutation CheckoutSessionUpdateSelections($checkoutContextInput:CheckoutContextInput!,$selectedPaymentMethodId:String,$selectedPaymentMethodOption:String){checkoutSessionUpdateSelections(checkoutContextInput:$checkoutContextInput selectedPaymentMethodId:$selectedPaymentMethodId selectedPaymentMethodOption:$selectedPaymentMethodOption){userErrors{message field __typename}__typename}}"}'
#response = requests.post('https://shop.app/pay/users/graphql', params=params, cookies=cookies, headers=headers, data=data)



import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shopify-tracking-consent': '3S.AMP',
}

params = {
    'operationName': 'PaymentSession',
}

json_data = {
    'variables': {
        'checkoutSessionIdentifier': 'daadf5d473ea94fde5b8c3a5893e2c72',
        'shopifyDomain': '4s0wfh-i6.myshopify.com',
        'addressId': 'c3a95b5f-5dab-4b52-bce2-12cf78d1577a',
        'checkoutClientSource': 'shop_pay',
        'creditCardId': '21c88226-4b75-4ad5-b7d4-94f3bae12d55',
        'batchCheckouts': [],
        'batchOnly': False,
        'stepUpChallengeSupported': True,
    },
    'operationName': 'PaymentSession',
    'query': 'mutation PaymentSession($addressId:ID,$creditCardId:ID!,$checkoutSessionIdentifier:String!,$shopifyDomain:String!,$installmentsAgreements:InstallmentsAgreementsInput,$unvaultedShippingAddress:AddressInput,$checkoutClientSource:CheckoutClientSourceEnum,$batchCheckouts:[BatchCheckoutsInput!],$batchOnly:Boolean,$publicCvvSessionId:String,$stepUpChallengeSupported:Boolean){paymentSessionGenerate(addressId:$addressId creditCardId:$creditCardId checkoutIdentifier:$checkoutSessionIdentifier shopifyDomain:$shopifyDomain installmentsAgreements:$installmentsAgreements unvaultedShippingAddress:$unvaultedShippingAddress checkoutClientSource:$checkoutClientSource batchCheckouts:$batchCheckouts batchOnly:$batchOnly publicCvvSessionId:$publicCvvSessionId stepUpChallengeSupported:$stepUpChallengeSupported){userErrors{message field __typename}sessionId batchCheckoutSessionIds{sessionId shopId __typename}__typename}}',
}

response = requests.post('https://shop.app/pay/users/graphql', params=params, cookies=cookies, headers=headers, json=json_data)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"checkoutSessionIdentifier":"daadf5d473ea94fde5b8c3a5893e2c72","shopifyDomain":"4s0wfh-i6.myshopify.com","addressId":"c3a95b5f-5dab-4b52-bce2-12cf78d1577a","checkoutClientSource":"shop_pay","creditCardId":"21c88226-4b75-4ad5-b7d4-94f3bae12d55","batchCheckouts":[],"batchOnly":false,"stepUpChallengeSupported":true},"operationName":"PaymentSession","query":"mutation PaymentSession($addressId:ID,$creditCardId:ID!,$checkoutSessionIdentifier:String!,$shopifyDomain:String!,$installmentsAgreements:InstallmentsAgreementsInput,$unvaultedShippingAddress:AddressInput,$checkoutClientSource:CheckoutClientSourceEnum,$batchCheckouts:[BatchCheckoutsInput!],$batchOnly:Boolean,$publicCvvSessionId:String,$stepUpChallengeSupported:Boolean){paymentSessionGenerate(addressId:$addressId creditCardId:$creditCardId checkoutIdentifier:$checkoutSessionIdentifier shopifyDomain:$shopifyDomain installmentsAgreements:$installmentsAgreements unvaultedShippingAddress:$unvaultedShippingAddress checkoutClientSource:$checkoutClientSource batchCheckouts:$batchCheckouts batchOnly:$batchOnly publicCvvSessionId:$publicCvvSessionId stepUpChallengeSupported:$stepUpChallengeSupported){userErrors{message field __typename}sessionId batchCheckoutSessionIds{sessionId shopId __typename}__typename}}"}'
#response = requests.post('https://shop.app/pay/users/graphql', params=params, cookies=cookies, headers=headers, data=data)




import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': 'id="hWNI32WWbY08l1Arphk2EFho", type="cn"',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-one-session-token': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shop-pay-token': 'eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaWQ6XC9cL3Nob3BpZnlcL1Nob3BcLzkyNTU0NDk0Mjk4IiwibmJmIjoxNzkyMTc5ODAxLCJzZXNzaW9uX3Rva2VuIjoiQUFFQld5Y0M5RnFEU19Lblg0MURKb1gzOF9RcjQwOVZZSnZfMU9fdTlVcURPMm5JSzh6RWpycDNqR0lpUDJzVi1lSy1WSVJPa3V4MmFGeWt2c2R1TndyS3BJQ00xQmxrNXdMVUgtMlVIeUU5UWFiQzJRcEd4dVdVa2x5dkNQRlYteXNOUVg3M29ITkEzNjlhYWVPdTh0by1lYnRMU3dKYzhqelZaSVF2MjROcmoxYU5OcmZrSno3d3VfM0ZMRVFPZF9USkxTMVlZVlB5TkdtRlA4OU94Q25Dc3VJYVJvcm9nMFN6dmV3Iiwic2Vzc2lvbl9jdXN0b21lcl9pZCI6MTA1MDczNjk4NDA5ODYsInNob3BfYWNjb3VudF91dWlkIjoiYTQ2ZWJiODUtNjc0Ny00NzhjLWE3ZmUtOTc5NDBjYzRiMWZmIiwic2hvcF9wYXlfZGF0YSI6IkNBSVNHWGRwZW1GeVpHeDVZWFZ5WVRrNU9VQm5iV0ZwYkM1amIyMGFFaGV3SEtTZEF1YVBZWVVfdkNNM3QwVU9oQ0lRcEc2N2hXZEhSNHluX3BlVURNU3hfempZX01uV0Jrb1NETm9uTXNVV2ZrX19wbHkwUTRDZGwxMEUiLCJjdXN0b21lcl9hdXRoZW50aWNhdGlvbl9hdXRoX3Byb3ZpZGVyIjoibG9naW5fd2l0aF9zaG9wIiwiZXhwIjoxNzkyMTgzNDAxLCJsYW5kaW5nX3BhZ2UiOiJcLyIsIm9yaWdfcmVmZXJyZXIiOiIiLCJtZXJjaGFudF9jb25zZW50IjoiM0FNUC5TIn0.eJ_036fE8fV7VlRQ_VrMQfgnE1KbP_duYqno-fhCrA0',
    'x-shopify-tracking-consent': '3S.AMP',
    'x-shopify-uniquetoken': 'c1e69033-8b91-45e6-8e70-d2adaeca3fe5',
    'x-shopify-visittoken': '9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2',
}

params = {
    'operationName': 'SubmitForCompletion',
}

json_data = {
    'variables': {
        'input': {
            'sessionInput': {
                'sessionToken': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
            },
            'queueToken': 'AxgaZG9f7b6IJjHw38EE3GrbpkKkB3GYMiDi7SHPoAc0tEYZH5c4iSY-U7WQzYJ0NuEaewvQJc_PTj0DYGTLxusIhS8XisE9zEMGTlD3f2v4IuH2lrMj_eM-NGbTP7uRzg==',
            'discounts': {
                'lines': [],
                'acceptUnexpectedDiscounts': True,
            },
            'delivery': {
                'deliveryLines': [
                    {
                        'destination': {
                            'streetAddress': {
                                'address1': 'Bijipur Main Road Sundar Nagar',
                                'address2': '',
                                'city': 'Brahmapur',
                                'countryCode': 'IN',
                                'postalCode': '760001',
                                'firstName': 'Subham',
                                'lastName': 'Kumar',
                                'zoneCode': 'OR',
                                'phone': '+917853878533',
                                'oneTimeUse': False,
                            },
                        },
                        'selectedDeliveryStrategy': {
                            'deliveryStrategyByHandle': {
                                'handle': 'daadf5d473ea94fde5b8c3a5893e2c72-1857f5edbd56cb87c7e3af188778f2e4',
                                'customDeliveryRate': False,
                            },
                            'options': {
                                'phone': '+917853878533',
                            },
                        },
                        'targetMerchandiseLines': {
                            'lines': [
                                {
                                    'stableId': '9720debd-5883-45ef-bf0d-fdc7d9558d88',
                                },
                            ],
                        },
                        'deliveryMethodTypes': [
                            'SHIPPING',
                        ],
                        'expectedTotalPrice': {
                            'value': {
                                'amount': '1700.00',
                                'currencyCode': 'INR',
                            },
                        },
                        'destinationChanged': False,
                    },
                ],
                'noDeliveryRequired': [],
                'useProgressiveRates': False,
                'prefetchShippingRatesStrategy': None,
                'interfaceFlow': 'SHOP_PAY',
                'supportsSplitShipping': True,
            },
            'deliveryExpectations': {
                'deliveryExpectationLines': [
                    {
                        'signedHandle': 'JtrIwQhz1zKpMDJcEVzpg4VS8UIp0/2JdzVu1lLNDYIEGik4MAwFBP+ZSBen45iacN/vVuOSTwH4XFzHytdV973s3yL0FgA2cEKgi0ICLASR5lDtAsfTbM+jzmnfzlMHXvE5uNTK3UvLZ3qMcntYG4HCjYgdYwwQIObanTd4VE+bgoJZ8hzQW1uWEZkMsK9wmTpKBWIbEr1ISYg17h+pkoMEdmxfCYWRimBKs28UCn6G4l7zKDGRK48iH9kkeJq7x8pXNurr01RP4YXx3yZlSGn0oqyDVT+VGwdEDlrrT26Fyi6AxxJeVpgyJ33aycCDIogsqjiGvFO295kd1fY+nYlbIWwIyrSKIKuxIB0Flraj/GuFg2mKnoBb9K25LA7xAQ8wiqmerrTrL3FFMgoC8y8Zvf+sGvOOaEWZgR9+H1OcXQ7W72oHKw7brfAMicZB4/NVRgyAIhivnZhGemXTRx9RuPwe4tT/Oh90iAapsADmccl30B0L6Mq+K9cpaVQu1PZlYiL+UVHR6Sea1uyY69cDTqrHmYw3nNlwP5sO6j/jeusgP3Ppi6C2ljgV/+AVcRvGcdWdTo7U9IBivbI+gdbYMdtMTp2Gcjoji+T+USM8HzBuKWcBZHqqgu9gN7bEE8cyA8qWs2iA677liuoWDQB9x/rKHeGnylXUEc2BLyz7S0myhA4KUjsUw0wAk6RWUS3PW4WqwblOQK5iOZJ9EZ2nw0grTZruIskbB5xKTrvw4rtFezSTeCBxMS/NjkUOR06GWWrnY46nIj2gxekYVRQkpWr2WqLcChH7toS0gophzYVG5stW5lnlKaXCPchTWRolADzOjMx0cDtUm+XIW3v59RUjbj+a4l9yw3+CkoZgB0O2ZknVTG5vsdeKQB/2IiOlEohilfs0TM6lsWkYbsUBOoplfYvWBn4yNIyc1Gcxw/99jBqRA5/4FbfYnp2MXEntEvKVAvmX0O4AAyNjISO/kd8/qmRPY9W6UUM61uLRin1D+wLyw7hePlyl4kvg30mKI6DnaxxyuhN01KNXl2wLWgbkSKayJM7ePJcSbWdyiczQMFRaj3lMqHEfBNqntcbk4Mrk5+cjQU9QE/mcrgwu0/o9QD9qjVMCgJJgQO7Rd/BpSbS2Qb7kjwfnnyCJly0g7aLrY+yMyJZo7YQHdMo04thNxtRWOJiRaguIqmLjYFjAWXlV7WdAeYop/ULFn8WjMTPKiK5AaB1QhzowDuWRJVeMhqDwJViOYXT3RENq2ba1xXb9ISDqyZsOjpAK7dHu4qz+r7IPoJILh+Lx88um8TJv8ZX4pNAA4/ltTD6oQ8PoDXeFlpXtlibODkWTqFf3NrTW369ATf0lzZARawuU3fDyHsaGbR8DYz/9P20rfsg0OjyYc0sKz3y6/MG/5FnTD/4nJ+nZgQJWMMb4zsRAneBDS0wAOQ4GyAjsqmRL6M09PVyHCLk2QVSlEc8HWgulPXFjPs5mYRVhYLys31CNfOOllKI0enjR3afK0GWjrdaCAmCCDd4FG2C99AQO--tnPVvH4t8iXFOe5w--VE1ObAnUQ4Eq6Pd19h2Lcw==',
                    },
                ],
            },
            'merchandise': {
                'merchandiseLines': [
                    {
                        'stableId': '9720debd-5883-45ef-bf0d-fdc7d9558d88',
                        'merchandise': {
                            'productVariantReference': {
                                'id': 'gid://shopify/ProductVariantMerchandise/51732384481626',
                                'variantId': 'gid://shopify/ProductVariant/51732384481626',
                                'properties': [],
                                'sellingPlanId': None,
                                'sellingPlanDigest': None,
                            },
                        },
                        'quantity': {
                            'items': {
                                'value': 1,
                            },
                        },
                        'expectedTotalPrice': {
                            'value': {
                                'amount': '4100.00',
                                'currencyCode': 'INR',
                            },
                        },
                        'lineComponentsSource': None,
                        'lineComponents': [],
                    },
                ],
            },
            'memberships': {
                'memberships': [],
            },
            'payment': {
                'totalAmount': {
                    'any': True,
                },
                'paymentLines': [
                    {
                        'paymentMethod': {
                            'directPaymentMethod': None,
                            'giftCardPaymentMethod': None,
                            'ownedGiftCardPaymentMethod': None,
                            'redeemablePaymentMethod': None,
                            'walletPaymentMethod': {
                                'name': 'SHOP_PAY',
                                'walletContent': {
                                    'shopPayWalletContent': {
                                        'sessionToken': 'spt_S1JySVppZTRiRUJsRzBxeDRVeWtaS0dHTXFXanNXM0RuV01NZlNtY1hwZVo3YmkzQjRZYytGdG1rZmF4dGZzcmFZd05VWUx6Qmx6OG1RcGluRGJlSHc5a3dJRFJCbVZ6MVdxSmZURUt5cldOUWNwMDkrTGZYYzFuclI4akZBRHJPWkEyQm1PWGJrK24yYzArZnI1ZCtoOENtVGF2QlozUTMrZk82T0pXR2ljbTFYSDRiY3pjejRZU0lhdU9INVlHSnJ4d3h4ZzdOSGY2bnUzTWZLcmd2TWs0VWJlRDdmaE5CUzFJUFZzZ3d4dCt0NE9mMkFVSGJDa09GOU8zcHdEUDB6WTgxL3FyU25XRnU5TmFPcm1adEtNK2Q0V25kc25wUzRCb0hsNVNFRHREb2QzMnp3Z1FRR2tKVFVjVG1Nb1lBeXVjRHVrbkRhNHRkclQxTmZhOU9nRExpUm1lYlFWbzVwdzYxRGVFVUVaUGZZWlIxOWM1eEk0WlVIdUl2WDk1QTlxTU4yT09KVldXMjFzbDU5akFHTFF4T3RpUU90QTkrWkZ2UmRpOGU5bGM1a3dDZE5JT3pUaW10QUx6Tkl1ME9lRFNBYjFlWWdZNlNmRlcvNmhMQXo1YmtWcGxwZHhuQW1Dd1pMbHpLdW9LUXFyYkpRN2dWV200eEhqVmJmV2hRdW5VT2M5Sk1LeWlZYWlqS0FqZXRTR05sL1duYnlqR0s2MWRsZ3hGSDRHVWNOSnNveEpzY3ZyS1NhMTlxYUJ6UlBzV0FiVkdnOFVRRmc0UmlLT2p0UFpzSWNFMVJlSng2RTRpVFA0cmRPVC9HMUtzblBrUzdRZDM4NE54TkVqQmNKcjdic3NRV3g2WHg0anpTbTFFQ05EWEx4dU5TaUQxZytOdkhleUR5Qjc2ZEk0TUxZczJOTTZvTTZIbVgzWjNSUWtJazRMMUdCbDZlSCtURTFBMWxkSXJNNXozVVJudGFYS1BkR0lqL1UrM2FBY25mR2VlNEF5YUtlSDN5Uk1heDRkd0doYTZiQUxRRWtSMXY4dFNQbHNqYlhjNnhJRlk4YlpTUDI3emEzRGdoS1VLaGtJeUd1dW1CVkJpNHBKL25jMFZjSmduYnc0cGhzYUV1MFptblZET3BMdCtBLzhyQ3U2U0hCK085bmxqMjladkZzVEhLbU1xeVBJVWwyMjJ4bk9qSkJ3SEhuU1ZpL2o3MU1KQkFBSWMrSGJRN24rTEl6ZVlLaFh5TW9NeWJzWnhlNjJpbWthZ05QOHV0WkFUMHNhRzRKS3dtNDd4bEs4YkwzR0tqK2pkUm1xZEFZbm1KTXZqcFZkSTIzV0FtNTArRFh5b2x1OEdoRXJ1VEplVld5bWFDUVRZcjBid2hLOGlYdDU3VHBaYXFoL25qa1VIenh4QTM1bVJ4VHhtT3cyNDJ0UVdMMFFMMll2MHJmTFJtK2ZGUkc1ZStQNVArMDVMckgyTGZjSW9hTi9zaEFZek9aR3dTSTJOS08raE9FTEt3Y1JnZStJR0NpcE9CVnNVM2psZGJxdWhXcEpGalYzQzdGZDVTUTNwQk0yanFvRWQwaUNpSGhzUnBjWStRbHljVXd1MzdBUnBHSXdTdndvNjZCOGFINHgyZzRqRmJkbjMyRFllUEFtMllTR3JvN0NJQ200Skw0TWNCdjR6eVZnSTNidDJOakV4WnRUeFppUkx0dndmRFFDU1h2WDRBa0dIVExyZEQyQXY2NUxoWDRaQ1pkZGp5eEVFWkN2SFFzNXRzUFF4ZnpEbzZjTmhRemVxYU44c3dhOFNRNDRjTkorZk1FS1lERVVmT2ZwUGhZU0lPR0NyRDN1dTdRM0g3d3VFZHRhV000UHNFdEdEcCtBcEpaK2tSMTBNUmozUFNUTlRId1lNTHNBb2tNMC9rM2FKL0EzODB4VDBEelREb0taUHU3Y3I5elhBeTkzeHdTQ3pieHRobk9vMkJtUnRqaVMrN281b1N6TExwTjZOSlV1UnlJQTdKejBKZnNwZ2pTRlFPSmZ5ditlRHRQVGJoODdOcHdPajdCdUFocmVEdURxTmRxd2hNY0ZubmNKa2FSbG9DeUs4dHptQ2R1SFZHMGJXb2IvV2xxa1k0U0huSy9vTXl1UE5HRnYvNm9LcmhSaEZmQTZpVDZPZ3hzL2IxSnFHY3V2dFErMmdKL2d1bVBZNDhVQ05STFJDSlp4VFpqaG14Smc1Q2tZUHdTRzlPU0JHazFRU01BPT0tLUQzTFB2aVJPaVhPZFU0TE9YMlNwdWc9PQ==--8746169c50ee5bd780c3c614a7a475abd524f9f2',
                                        'billingAddress': {
                                            'streetAddress': {
                                                'address1': 'Bijipur Main Road Sundar Nagar',
                                                'address2': '',
                                                'city': 'Brahmapur',
                                                'countryCode': 'IN',
                                                'postalCode': '760001',
                                                'firstName': 'Subham',
                                                'lastName': 'Kumar',
                                                'zoneCode': 'OR',
                                                'phone': '+917853878533',
                                            },
                                        },
                                        'paymentMethod': 'CREDIT_CARD',
                                        'paymentMethodIdentifier': '12ba72fffce249eb2764c19cac64fb92',
                                    },
                                },
                            },
                            'walletsPlatformPaymentMethod': None,
                            'localPaymentMethod': None,
                            'paymentOnDeliveryMethod': None,
                            'paymentOnDeliveryMethod2': None,
                            'manualPaymentMethod': None,
                            'customPaymentMethod': None,
                            'offsitePaymentMethod': None,
                            'customOnsitePaymentMethod': None,
                            'deferredPaymentMethod': None,
                            'customerCreditCardPaymentMethod': None,
                            'paypalBillingAgreementPaymentMethod': None,
                            'remotePaymentInstrument': None,
                        },
                        'amount': {
                            'value': {
                                'amount': '5800',
                                'currencyCode': 'INR',
                            },
                        },
                    },
                ],
                'billingAddress': {
                    'streetAddress': {
                        'address1': 'Bijipur Main Road Sundar Nagar',
                        'address2': '',
                        'city': 'Brahmapur',
                        'countryCode': 'IN',
                        'postalCode': '760001',
                        'firstName': 'Subham',
                        'lastName': 'Kumar',
                        'zoneCode': 'OR',
                        'phone': '+917853878533',
                    },
                },
                'creditCardBin': '40089500',
                'allowStoreCredit': False,
            },
            'buyerIdentity': {
                'customer': {
                    'presentmentCurrency': 'INR',
                    'countryCode': 'IN',
                },
                'email': 'wizardlyaura999@gmail.com',
                'emailChanged': False,
                'phoneCountryCode': 'IN',
                'marketingConsent': [
                    {
                        'email': {
                            'consentState': 'DECLINED',
                            'value': 'wizardlyaura999@gmail.com',
                        },
                    },
                ],
                'shopPayOptInPhone': {
                    'number': '+917853878533',
                    'countryCode': 'IN',
                },
                'shopUserSecureData': 'eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s',
                'prefillSource': 'SHOP_PAY',
                'rememberMe': False,
            },
            'tip': {
                'tipLines': [],
            },
            'taxes': {
                'proposedAllocations': None,
                'proposedTotalAmount': {
                    'value': {
                        'amount': '0',
                        'currencyCode': 'INR',
                    },
                },
                'proposedTotalIncludedAmount': None,
                'proposedMixedStateTotalAmount': None,
                'proposedExemptions': [],
            },
            'note': {
                'message': None,
                'customAttributes': [],
            },
            'localizationExtension': {
                'fields': [],
            },
            'shopPayArtifact': {
                'shopUser': {
                    'uuid': 'eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s',
                },
            },
            'nonNegotiableTerms': None,
            'scriptFingerprint': {
                'signature': None,
                'signatureUuid': None,
                'lineItemScriptChanges': [],
                'paymentScriptChanges': [],
                'shippingScriptChanges': [],
            },
            'optionalDuties': {
                'buyerRefusesDuties': False,
            },
            'cartMetafields': [],
        },
        'attemptToken': 'hWNI32WWbY08l1Arphk2EFho-u9nlpsorwrn',
        'metafields': [],
        'analytics': {
            'requestUrl': 'https://shop.app/checkout/92554494298/cn/hWNI32WWbY08l1Arphk2EFho/en-in/shoppay?_mcs=3AMP.S&_r=AQABmZF3Ltqhl3wpt0SwuxklVyW0MgVzr1HrqXesuvADkXoltzmB&tracking_unique=c1e69033-8b91-45e6-8e70-d2adaeca3fe5&tracking_visit=9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2&_cs=3S.AMP',
            'pageId': '463db52b-67E3-4F5A-9822-978E79640BDB',
        },
    },
    'operationName': 'SubmitForCompletion',
    'id': 'f02c160f316aa090cc8d2746ab840109be3265dcac12fef341e51d697ac5b2b8',
}

response = requests.post(
    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"input":{"sessionInput":{"sessionToken":"AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew"},"queueToken":"AxgaZG9f7b6IJjHw38EE3GrbpkKkB3GYMiDi7SHPoAc0tEYZH5c4iSY-U7WQzYJ0NuEaewvQJc_PTj0DYGTLxusIhS8XisE9zEMGTlD3f2v4IuH2lrMj_eM-NGbTP7uRzg==","discounts":{"lines":[],"acceptUnexpectedDiscounts":true},"delivery":{"deliveryLines":[{"destination":{"streetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533","oneTimeUse":false}},"selectedDeliveryStrategy":{"deliveryStrategyByHandle":{"handle":"daadf5d473ea94fde5b8c3a5893e2c72-1857f5edbd56cb87c7e3af188778f2e4","customDeliveryRate":false},"options":{"phone":"+917853878533"}},"targetMerchandiseLines":{"lines":[{"stableId":"9720debd-5883-45ef-bf0d-fdc7d9558d88"}]},"deliveryMethodTypes":["SHIPPING"],"expectedTotalPrice":{"value":{"amount":"1700.00","currencyCode":"INR"}},"destinationChanged":false}],"noDeliveryRequired":[],"useProgressiveRates":false,"prefetchShippingRatesStrategy":null,"interfaceFlow":"SHOP_PAY","supportsSplitShipping":true},"deliveryExpectations":{"deliveryExpectationLines":[{"signedHandle":"JtrIwQhz1zKpMDJcEVzpg4VS8UIp0/2JdzVu1lLNDYIEGik4MAwFBP+ZSBen45iacN/vVuOSTwH4XFzHytdV973s3yL0FgA2cEKgi0ICLASR5lDtAsfTbM+jzmnfzlMHXvE5uNTK3UvLZ3qMcntYG4HCjYgdYwwQIObanTd4VE+bgoJZ8hzQW1uWEZkMsK9wmTpKBWIbEr1ISYg17h+pkoMEdmxfCYWRimBKs28UCn6G4l7zKDGRK48iH9kkeJq7x8pXNurr01RP4YXx3yZlSGn0oqyDVT+VGwdEDlrrT26Fyi6AxxJeVpgyJ33aycCDIogsqjiGvFO295kd1fY+nYlbIWwIyrSKIKuxIB0Flraj/GuFg2mKnoBb9K25LA7xAQ8wiqmerrTrL3FFMgoC8y8Zvf+sGvOOaEWZgR9+H1OcXQ7W72oHKw7brfAMicZB4/NVRgyAIhivnZhGemXTRx9RuPwe4tT/Oh90iAapsADmccl30B0L6Mq+K9cpaVQu1PZlYiL+UVHR6Sea1uyY69cDTqrHmYw3nNlwP5sO6j/jeusgP3Ppi6C2ljgV/+AVcRvGcdWdTo7U9IBivbI+gdbYMdtMTp2Gcjoji+T+USM8HzBuKWcBZHqqgu9gN7bEE8cyA8qWs2iA677liuoWDQB9x/rKHeGnylXUEc2BLyz7S0myhA4KUjsUw0wAk6RWUS3PW4WqwblOQK5iOZJ9EZ2nw0grTZruIskbB5xKTrvw4rtFezSTeCBxMS/NjkUOR06GWWrnY46nIj2gxekYVRQkpWr2WqLcChH7toS0gophzYVG5stW5lnlKaXCPchTWRolADzOjMx0cDtUm+XIW3v59RUjbj+a4l9yw3+CkoZgB0O2ZknVTG5vsdeKQB/2IiOlEohilfs0TM6lsWkYbsUBOoplfYvWBn4yNIyc1Gcxw/99jBqRA5/4FbfYnp2MXEntEvKVAvmX0O4AAyNjISO/kd8/qmRPY9W6UUM61uLRin1D+wLyw7hePlyl4kvg30mKI6DnaxxyuhN01KNXl2wLWgbkSKayJM7ePJcSbWdyiczQMFRaj3lMqHEfBNqntcbk4Mrk5+cjQU9QE/mcrgwu0/o9QD9qjVMCgJJgQO7Rd/BpSbS2Qb7kjwfnnyCJly0g7aLrY+yMyJZo7YQHdMo04thNxtRWOJiRaguIqmLjYFjAWXlV7WdAeYop/ULFn8WjMTPKiK5AaB1QhzowDuWRJVeMhqDwJViOYXT3RENq2ba1xXb9ISDqyZsOjpAK7dHu4qz+r7IPoJILh+Lx88um8TJv8ZX4pNAA4/ltTD6oQ8PoDXeFlpXtlibODkWTqFf3NrTW369ATf0lzZARawuU3fDyHsaGbR8DYz/9P20rfsg0OjyYc0sKz3y6/MG/5FnTD/4nJ+nZgQJWMMb4zsRAneBDS0wAOQ4GyAjsqmRL6M09PVyHCLk2QVSlEc8HWgulPXFjPs5mYRVhYLys31CNfOOllKI0enjR3afK0GWjrdaCAmCCDd4FG2C99AQO--tnPVvH4t8iXFOe5w--VE1ObAnUQ4Eq6Pd19h2Lcw=="}]},"merchandise":{"merchandiseLines":[{"stableId":"9720debd-5883-45ef-bf0d-fdc7d9558d88","merchandise":{"productVariantReference":{"id":"gid://shopify/ProductVariantMerchandise/51732384481626","variantId":"gid://shopify/ProductVariant/51732384481626","properties":[],"sellingPlanId":null,"sellingPlanDigest":null}},"quantity":{"items":{"value":1}},"expectedTotalPrice":{"value":{"amount":"4100.00","currencyCode":"INR"}},"lineComponentsSource":null,"lineComponents":[]}]},"memberships":{"memberships":[]},"payment":{"totalAmount":{"any":true},"paymentLines":[{"paymentMethod":{"directPaymentMethod":null,"giftCardPaymentMethod":null,"ownedGiftCardPaymentMethod":null,"redeemablePaymentMethod":null,"walletPaymentMethod":{"name":"SHOP_PAY","walletContent":{"shopPayWalletContent":{"sessionToken":"spt_S1JySVppZTRiRUJsRzBxeDRVeWtaS0dHTXFXanNXM0RuV01NZlNtY1hwZVo3YmkzQjRZYytGdG1rZmF4dGZzcmFZd05VWUx6Qmx6OG1RcGluRGJlSHc5a3dJRFJCbVZ6MVdxSmZURUt5cldOUWNwMDkrTGZYYzFuclI4akZBRHJPWkEyQm1PWGJrK24yYzArZnI1ZCtoOENtVGF2QlozUTMrZk82T0pXR2ljbTFYSDRiY3pjejRZU0lhdU9INVlHSnJ4d3h4ZzdOSGY2bnUzTWZLcmd2TWs0VWJlRDdmaE5CUzFJUFZzZ3d4dCt0NE9mMkFVSGJDa09GOU8zcHdEUDB6WTgxL3FyU25XRnU5TmFPcm1adEtNK2Q0V25kc25wUzRCb0hsNVNFRHREb2QzMnp3Z1FRR2tKVFVjVG1Nb1lBeXVjRHVrbkRhNHRkclQxTmZhOU9nRExpUm1lYlFWbzVwdzYxRGVFVUVaUGZZWlIxOWM1eEk0WlVIdUl2WDk1QTlxTU4yT09KVldXMjFzbDU5akFHTFF4T3RpUU90QTkrWkZ2UmRpOGU5bGM1a3dDZE5JT3pUaW10QUx6Tkl1ME9lRFNBYjFlWWdZNlNmRlcvNmhMQXo1YmtWcGxwZHhuQW1Dd1pMbHpLdW9LUXFyYkpRN2dWV200eEhqVmJmV2hRdW5VT2M5Sk1LeWlZYWlqS0FqZXRTR05sL1duYnlqR0s2MWRsZ3hGSDRHVWNOSnNveEpzY3ZyS1NhMTlxYUJ6UlBzV0FiVkdnOFVRRmc0UmlLT2p0UFpzSWNFMVJlSng2RTRpVFA0cmRPVC9HMUtzblBrUzdRZDM4NE54TkVqQmNKcjdic3NRV3g2WHg0anpTbTFFQ05EWEx4dU5TaUQxZytOdkhleUR5Qjc2ZEk0TUxZczJOTTZvTTZIbVgzWjNSUWtJazRMMUdCbDZlSCtURTFBMWxkSXJNNXozVVJudGFYS1BkR0lqL1UrM2FBY25mR2VlNEF5YUtlSDN5Uk1heDRkd0doYTZiQUxRRWtSMXY4dFNQbHNqYlhjNnhJRlk4YlpTUDI3emEzRGdoS1VLaGtJeUd1dW1CVkJpNHBKL25jMFZjSmduYnc0cGhzYUV1MFptblZET3BMdCtBLzhyQ3U2U0hCK085bmxqMjladkZzVEhLbU1xeVBJVWwyMjJ4bk9qSkJ3SEhuU1ZpL2o3MU1KQkFBSWMrSGJRN24rTEl6ZVlLaFh5TW9NeWJzWnhlNjJpbWthZ05QOHV0WkFUMHNhRzRKS3dtNDd4bEs4YkwzR0tqK2pkUm1xZEFZbm1KTXZqcFZkSTIzV0FtNTArRFh5b2x1OEdoRXJ1VEplVld5bWFDUVRZcjBid2hLOGlYdDU3VHBaYXFoL25qa1VIenh4QTM1bVJ4VHhtT3cyNDJ0UVdMMFFMMll2MHJmTFJtK2ZGUkc1ZStQNVArMDVMckgyTGZjSW9hTi9zaEFZek9aR3dTSTJOS08raE9FTEt3Y1JnZStJR0NpcE9CVnNVM2psZGJxdWhXcEpGalYzQzdGZDVTUTNwQk0yanFvRWQwaUNpSGhzUnBjWStRbHljVXd1MzdBUnBHSXdTdndvNjZCOGFINHgyZzRqRmJkbjMyRFllUEFtMllTR3JvN0NJQ200Skw0TWNCdjR6eVZnSTNidDJOakV4WnRUeFppUkx0dndmRFFDU1h2WDRBa0dIVExyZEQyQXY2NUxoWDRaQ1pkZGp5eEVFWkN2SFFzNXRzUFF4ZnpEbzZjTmhRemVxYU44c3dhOFNRNDRjTkorZk1FS1lERVVmT2ZwUGhZU0lPR0NyRDN1dTdRM0g3d3VFZHRhV000UHNFdEdEcCtBcEpaK2tSMTBNUmozUFNUTlRId1lNTHNBb2tNMC9rM2FKL0EzODB4VDBEelREb0taUHU3Y3I5elhBeTkzeHdTQ3pieHRobk9vMkJtUnRqaVMrN281b1N6TExwTjZOSlV1UnlJQTdKejBKZnNwZ2pTRlFPSmZ5ditlRHRQVGJoODdOcHdPajdCdUFocmVEdURxTmRxd2hNY0ZubmNKa2FSbG9DeUs4dHptQ2R1SFZHMGJXb2IvV2xxa1k0U0huSy9vTXl1UE5HRnYvNm9LcmhSaEZmQTZpVDZPZ3hzL2IxSnFHY3V2dFErMmdKL2d1bVBZNDhVQ05STFJDSlp4VFpqaG14Smc1Q2tZUHdTRzlPU0JHazFRU01BPT0tLUQzTFB2aVJPaVhPZFU0TE9YMlNwdWc9PQ==--8746169c50ee5bd780c3c614a7a475abd524f9f2","billingAddress":{"streetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533"}},"paymentMethod":"CREDIT_CARD","paymentMethodIdentifier":"12ba72fffce249eb2764c19cac64fb92"}}},"walletsPlatformPaymentMethod":null,"localPaymentMethod":null,"paymentOnDeliveryMethod":null,"paymentOnDeliveryMethod2":null,"manualPaymentMethod":null,"customPaymentMethod":null,"offsitePaymentMethod":null,"customOnsitePaymentMethod":null,"deferredPaymentMethod":null,"customerCreditCardPaymentMethod":null,"paypalBillingAgreementPaymentMethod":null,"remotePaymentInstrument":null},"amount":{"value":{"amount":"5800","currencyCode":"INR"}}}],"billingAddress":{"streetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533"}},"creditCardBin":"40089500","allowStoreCredit":false},"buyerIdentity":{"customer":{"presentmentCurrency":"INR","countryCode":"IN"},"email":"wizardlyaura999@gmail.com","emailChanged":false,"phoneCountryCode":"IN","marketingConsent":[{"email":{"consentState":"DECLINED","value":"wizardlyaura999@gmail.com"}}],"shopPayOptInPhone":{"number":"+917853878533","countryCode":"IN"},"shopUserSecureData":"eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s","prefillSource":"SHOP_PAY","rememberMe":false},"tip":{"tipLines":[]},"taxes":{"proposedAllocations":null,"proposedTotalAmount":{"value":{"amount":"0","currencyCode":"INR"}},"proposedTotalIncludedAmount":null,"proposedMixedStateTotalAmount":null,"proposedExemptions":[]},"note":{"message":null,"customAttributes":[]},"localizationExtension":{"fields":[]},"shopPayArtifact":{"shopUser":{"uuid":"eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s"}},"nonNegotiableTerms":null,"scriptFingerprint":{"signature":null,"signatureUuid":null,"lineItemScriptChanges":[],"paymentScriptChanges":[],"shippingScriptChanges":[]},"optionalDuties":{"buyerRefusesDuties":false},"cartMetafields":[]},"attemptToken":"hWNI32WWbY08l1Arphk2EFho-u9nlpsorwrn","metafields":[],"analytics":{"requestUrl":"https://shop.app/checkout/92554494298/cn/hWNI32WWbY08l1Arphk2EFho/en-in/shoppay?_mcs=3AMP.S&_r=AQABmZF3Ltqhl3wpt0SwuxklVyW0MgVzr1HrqXesuvADkXoltzmB&tracking_unique=c1e69033-8b91-45e6-8e70-d2adaeca3fe5&tracking_visit=9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2&_cs=3S.AMP","pageId":"463db52b-67E3-4F5A-9822-978E79640BDB"}},"operationName":"SubmitForCompletion","id":"f02c160f316aa090cc8d2746ab840109be3265dcac12fef341e51d697ac5b2b8"}'
#response = requests.post(
#    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
#    params=params,
#    cookies=cookies,
#    headers=headers,
#    data=data,
#)



import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': 'id="hWNI32WWbY08l1Arphk2EFho", type="cn"',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-one-session-token': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shop-pay-token': 'eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaWQ6XC9cL3Nob3BpZnlcL1Nob3BcLzkyNTU0NDk0Mjk4IiwibmJmIjoxNzkyMTc5ODAxLCJzZXNzaW9uX3Rva2VuIjoiQUFFQld5Y0M5RnFEU19Lblg0MURKb1gzOF9RcjQwOVZZSnZfMU9fdTlVcURPMm5JSzh6RWpycDNqR0lpUDJzVi1lSy1WSVJPa3V4MmFGeWt2c2R1TndyS3BJQ00xQmxrNXdMVUgtMlVIeUU5UWFiQzJRcEd4dVdVa2x5dkNQRlYteXNOUVg3M29ITkEzNjlhYWVPdTh0by1lYnRMU3dKYzhqelZaSVF2MjROcmoxYU5OcmZrSno3d3VfM0ZMRVFPZF9USkxTMVlZVlB5TkdtRlA4OU94Q25Dc3VJYVJvcm9nMFN6dmV3Iiwic2Vzc2lvbl9jdXN0b21lcl9pZCI6MTA1MDczNjk4NDA5ODYsInNob3BfYWNjb3VudF91dWlkIjoiYTQ2ZWJiODUtNjc0Ny00NzhjLWE3ZmUtOTc5NDBjYzRiMWZmIiwic2hvcF9wYXlfZGF0YSI6IkNBSVNHWGRwZW1GeVpHeDVZWFZ5WVRrNU9VQm5iV0ZwYkM1amIyMGFFaGV3SEtTZEF1YVBZWVVfdkNNM3QwVU9oQ0lRcEc2N2hXZEhSNHluX3BlVURNU3hfempZX01uV0Jrb1NETm9uTXNVV2ZrX19wbHkwUTRDZGwxMEUiLCJjdXN0b21lcl9hdXRoZW50aWNhdGlvbl9hdXRoX3Byb3ZpZGVyIjoibG9naW5fd2l0aF9zaG9wIiwiZXhwIjoxNzkyMTgzNDAxLCJsYW5kaW5nX3BhZ2UiOiJcLyIsIm9yaWdfcmVmZXJyZXIiOiIiLCJtZXJjaGFudF9jb25zZW50IjoiM0FNUC5TIn0.eJ_036fE8fV7VlRQ_VrMQfgnE1KbP_duYqno-fhCrA0',
    'x-shopify-tracking-consent': '3S.AMP',
    'x-shopify-uniquetoken': 'c1e69033-8b91-45e6-8e70-d2adaeca3fe5',
    'x-shopify-visittoken': '9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2',
}

params = {
    'operationName': 'PollForReceipt',
}

json_data = {
    'variables': {
        'receiptId': 'gid://shopify/ProcessedReceipt/779f7d9e2ff7fd9098d1a3e39febd0a0',
        'sessionToken': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    },
    'operationName': 'PollForReceipt',
    'id': '98f65f1b789aa2a58a4da4284e773c8d577787273e650e6823704d3715082c59',
}

response = requests.post(
    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"receiptId":"gid://shopify/ProcessedReceipt/779f7d9e2ff7fd9098d1a3e39febd0a0","sessionToken":"AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew"},"operationName":"PollForReceipt","id":"98f65f1b789aa2a58a4da4284e773c8d577787273e650e6823704d3715082c59"}'
#response = requests.post(
#    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
#    params=params,
#    cookies=cookies,
#    headers=headers,
#    data=data,
#)



import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': 'id="hWNI32WWbY08l1Arphk2EFho", type="cn"',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-one-session-token': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shop-pay-token': 'eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaWQ6XC9cL3Nob3BpZnlcL1Nob3BcLzkyNTU0NDk0Mjk4IiwibmJmIjoxNzkyMTc5ODAxLCJzZXNzaW9uX3Rva2VuIjoiQUFFQld5Y0M5RnFEU19Lblg0MURKb1gzOF9RcjQwOVZZSnZfMU9fdTlVcURPMm5JSzh6RWpycDNqR0lpUDJzVi1lSy1WSVJPa3V4MmFGeWt2c2R1TndyS3BJQ00xQmxrNXdMVUgtMlVIeUU5UWFiQzJRcEd4dVdVa2x5dkNQRlYteXNOUVg3M29ITkEzNjlhYWVPdTh0by1lYnRMU3dKYzhqelZaSVF2MjROcmoxYU5OcmZrSno3d3VfM0ZMRVFPZF9USkxTMVlZVlB5TkdtRlA4OU94Q25Dc3VJYVJvcm9nMFN6dmV3Iiwic2Vzc2lvbl9jdXN0b21lcl9pZCI6MTA1MDczNjk4NDA5ODYsInNob3BfYWNjb3VudF91dWlkIjoiYTQ2ZWJiODUtNjc0Ny00NzhjLWE3ZmUtOTc5NDBjYzRiMWZmIiwic2hvcF9wYXlfZGF0YSI6IkNBSVNHWGRwZW1GeVpHeDVZWFZ5WVRrNU9VQm5iV0ZwYkM1amIyMGFFaGV3SEtTZEF1YVBZWVVfdkNNM3QwVU9oQ0lRcEc2N2hXZEhSNHluX3BlVURNU3hfempZX01uV0Jrb1NETm9uTXNVV2ZrX19wbHkwUTRDZGwxMEUiLCJjdXN0b21lcl9hdXRoZW50aWNhdGlvbl9hdXRoX3Byb3ZpZGVyIjoibG9naW5fd2l0aF9zaG9wIiwiZXhwIjoxNzkyMTgzNDAxLCJsYW5kaW5nX3BhZ2UiOiJcLyIsIm9yaWdfcmVmZXJyZXIiOiIiLCJtZXJjaGFudF9jb25zZW50IjoiM0FNUC5TIn0.eJ_036fE8fV7VlRQ_VrMQfgnE1KbP_duYqno-fhCrA0',
    'x-shopify-tracking-consent': '3S.AMP',
    'x-shopify-uniquetoken': 'c1e69033-8b91-45e6-8e70-d2adaeca3fe5',
    'x-shopify-visittoken': '9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2',
}

params = {
    'operationName': 'Proposal',
}

json_data = {
    'variables': {
        'sessionInput': {
            'sessionToken': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
        },
        'queueToken': 'AxgaZG9f7b6IJjHw38EE3GrbpkKkB3GYMiDi7SHPoAc0tEYZH5c4iSY-U7WQzYJ0NuEaewvQJc_PTj0DYGTLxusIhS8XisE9zEMGTlD3f2v4IuH2lrMj_eM-NGbTP7uRzg==',
        'discounts': {
            'lines': [],
            'acceptUnexpectedDiscounts': True,
        },
        'delivery': {
            'deliveryLines': [
                {
                    'destination': {
                        'partialStreetAddress': {
                            'address1': 'Bijipur Main Road Sundar Nagar',
                            'address2': '',
                            'city': 'Brahmapur',
                            'countryCode': 'IN',
                            'postalCode': '760001',
                            'firstName': 'Subham',
                            'lastName': 'Kumar',
                            'zoneCode': 'OR',
                            'phone': '+917853878533',
                            'oneTimeUse': False,
                        },
                    },
                    'selectedDeliveryStrategy': {
                        'deliveryStrategyByHandle': {
                            'handle': 'daadf5d473ea94fde5b8c3a5893e2c72-1857f5edbd56cb87c7e3af188778f2e4',
                            'customDeliveryRate': False,
                        },
                        'options': {
                            'phone': '+917853878533',
                        },
                    },
                    'targetMerchandiseLines': {
                        'lines': [
                            {
                                'stableId': '9720debd-5883-45ef-bf0d-fdc7d9558d88',
                            },
                        ],
                    },
                    'deliveryMethodTypes': [
                        'SHIPPING',
                    ],
                    'expectedTotalPrice': {
                        'value': {
                            'amount': '1700.00',
                            'currencyCode': 'INR',
                        },
                    },
                    'destinationChanged': False,
                },
            ],
            'noDeliveryRequired': [],
            'useProgressiveRates': False,
            'prefetchShippingRatesStrategy': None,
            'interfaceFlow': 'SHOP_PAY',
            'supportsSplitShipping': True,
        },
        'deliveryExpectations': {
            'deliveryExpectationLines': [
                {
                    'signedHandle': 'JtrIwQhz1zKpMDJcEVzpg4VS8UIp0/2JdzVu1lLNDYIEGik4MAwFBP+ZSBen45iacN/vVuOSTwH4XFzHytdV973s3yL0FgA2cEKgi0ICLASR5lDtAsfTbM+jzmnfzlMHXvE5uNTK3UvLZ3qMcntYG4HCjYgdYwwQIObanTd4VE+bgoJZ8hzQW1uWEZkMsK9wmTpKBWIbEr1ISYg17h+pkoMEdmxfCYWRimBKs28UCn6G4l7zKDGRK48iH9kkeJq7x8pXNurr01RP4YXx3yZlSGn0oqyDVT+VGwdEDlrrT26Fyi6AxxJeVpgyJ33aycCDIogsqjiGvFO295kd1fY+nYlbIWwIyrSKIKuxIB0Flraj/GuFg2mKnoBb9K25LA7xAQ8wiqmerrTrL3FFMgoC8y8Zvf+sGvOOaEWZgR9+H1OcXQ7W72oHKw7brfAMicZB4/NVRgyAIhivnZhGemXTRx9RuPwe4tT/Oh90iAapsADmccl30B0L6Mq+K9cpaVQu1PZlYiL+UVHR6Sea1uyY69cDTqrHmYw3nNlwP5sO6j/jeusgP3Ppi6C2ljgV/+AVcRvGcdWdTo7U9IBivbI+gdbYMdtMTp2Gcjoji+T+USM8HzBuKWcBZHqqgu9gN7bEE8cyA8qWs2iA677liuoWDQB9x/rKHeGnylXUEc2BLyz7S0myhA4KUjsUw0wAk6RWUS3PW4WqwblOQK5iOZJ9EZ2nw0grTZruIskbB5xKTrvw4rtFezSTeCBxMS/NjkUOR06GWWrnY46nIj2gxekYVRQkpWr2WqLcChH7toS0gophzYVG5stW5lnlKaXCPchTWRolADzOjMx0cDtUm+XIW3v59RUjbj+a4l9yw3+CkoZgB0O2ZknVTG5vsdeKQB/2IiOlEohilfs0TM6lsWkYbsUBOoplfYvWBn4yNIyc1Gcxw/99jBqRA5/4FbfYnp2MXEntEvKVAvmX0O4AAyNjISO/kd8/qmRPY9W6UUM61uLRin1D+wLyw7hePlyl4kvg30mKI6DnaxxyuhN01KNXl2wLWgbkSKayJM7ePJcSbWdyiczQMFRaj3lMqHEfBNqntcbk4Mrk5+cjQU9QE/mcrgwu0/o9QD9qjVMCgJJgQO7Rd/BpSbS2Qb7kjwfnnyCJly0g7aLrY+yMyJZo7YQHdMo04thNxtRWOJiRaguIqmLjYFjAWXlV7WdAeYop/ULFn8WjMTPKiK5AaB1QhzowDuWRJVeMhqDwJViOYXT3RENq2ba1xXb9ISDqyZsOjpAK7dHu4qz+r7IPoJILh+Lx88um8TJv8ZX4pNAA4/ltTD6oQ8PoDXeFlpXtlibODkWTqFf3NrTW369ATf0lzZARawuU3fDyHsaGbR8DYz/9P20rfsg0OjyYc0sKz3y6/MG/5FnTD/4nJ+nZgQJWMMb4zsRAneBDS0wAOQ4GyAjsqmRL6M09PVyHCLk2QVSlEc8HWgulPXFjPs5mYRVhYLys31CNfOOllKI0enjR3afK0GWjrdaCAmCCDd4FG2C99AQO--tnPVvH4t8iXFOe5w--VE1ObAnUQ4Eq6Pd19h2Lcw==',
                },
            ],
        },
        'merchandise': {
            'merchandiseLines': [
                {
                    'stableId': '9720debd-5883-45ef-bf0d-fdc7d9558d88',
                    'merchandise': {
                        'productVariantReference': {
                            'id': 'gid://shopify/ProductVariantMerchandise/51732384481626',
                            'variantId': 'gid://shopify/ProductVariant/51732384481626',
                            'properties': [],
                            'sellingPlanId': None,
                            'sellingPlanDigest': None,
                        },
                    },
                    'quantity': {
                        'items': {
                            'value': 1,
                        },
                    },
                    'expectedTotalPrice': {
                        'value': {
                            'amount': '4100.00',
                            'currencyCode': 'INR',
                        },
                    },
                    'lineComponentsSource': None,
                    'lineComponents': [],
                },
            ],
        },
        'memberships': {
            'memberships': [],
        },
        'payment': {
            'totalAmount': {
                'any': True,
            },
            'paymentLines': [
                {
                    'paymentMethod': {
                        'directPaymentMethod': None,
                        'giftCardPaymentMethod': None,
                        'ownedGiftCardPaymentMethod': None,
                        'redeemablePaymentMethod': None,
                        'walletPaymentMethod': {
                            'name': 'SHOP_PAY',
                            'walletContent': {
                                'shopPayWalletContent': {
                                    'sessionToken': 'spt_S1JySVppZTRiRUJsRzBxeDRVeWtaS0dHTXFXanNXM0RuV01NZlNtY1hwZVo3YmkzQjRZYytGdG1rZmF4dGZzcmFZd05VWUx6Qmx6OG1RcGluRGJlSHc5a3dJRFJCbVZ6MVdxSmZURUt5cldOUWNwMDkrTGZYYzFuclI4akZBRHJPWkEyQm1PWGJrK24yYzArZnI1ZCtoOENtVGF2QlozUTMrZk82T0pXR2ljbTFYSDRiY3pjejRZU0lhdU9INVlHSnJ4d3h4ZzdOSGY2bnUzTWZLcmd2TWs0VWJlRDdmaE5CUzFJUFZzZ3d4dCt0NE9mMkFVSGJDa09GOU8zcHdEUDB6WTgxL3FyU25XRnU5TmFPcm1adEtNK2Q0V25kc25wUzRCb0hsNVNFRHREb2QzMnp3Z1FRR2tKVFVjVG1Nb1lBeXVjRHVrbkRhNHRkclQxTmZhOU9nRExpUm1lYlFWbzVwdzYxRGVFVUVaUGZZWlIxOWM1eEk0WlVIdUl2WDk1QTlxTU4yT09KVldXMjFzbDU5akFHTFF4T3RpUU90QTkrWkZ2UmRpOGU5bGM1a3dDZE5JT3pUaW10QUx6Tkl1ME9lRFNBYjFlWWdZNlNmRlcvNmhMQXo1YmtWcGxwZHhuQW1Dd1pMbHpLdW9LUXFyYkpRN2dWV200eEhqVmJmV2hRdW5VT2M5Sk1LeWlZYWlqS0FqZXRTR05sL1duYnlqR0s2MWRsZ3hGSDRHVWNOSnNveEpzY3ZyS1NhMTlxYUJ6UlBzV0FiVkdnOFVRRmc0UmlLT2p0UFpzSWNFMVJlSng2RTRpVFA0cmRPVC9HMUtzblBrUzdRZDM4NE54TkVqQmNKcjdic3NRV3g2WHg0anpTbTFFQ05EWEx4dU5TaUQxZytOdkhleUR5Qjc2ZEk0TUxZczJOTTZvTTZIbVgzWjNSUWtJazRMMUdCbDZlSCtURTFBMWxkSXJNNXozVVJudGFYS1BkR0lqL1UrM2FBY25mR2VlNEF5YUtlSDN5Uk1heDRkd0doYTZiQUxRRWtSMXY4dFNQbHNqYlhjNnhJRlk4YlpTUDI3emEzRGdoS1VLaGtJeUd1dW1CVkJpNHBKL25jMFZjSmduYnc0cGhzYUV1MFptblZET3BMdCtBLzhyQ3U2U0hCK085bmxqMjladkZzVEhLbU1xeVBJVWwyMjJ4bk9qSkJ3SEhuU1ZpL2o3MU1KQkFBSWMrSGJRN24rTEl6ZVlLaFh5TW9NeWJzWnhlNjJpbWthZ05QOHV0WkFUMHNhRzRKS3dtNDd4bEs4YkwzR0tqK2pkUm1xZEFZbm1KTXZqcFZkSTIzV0FtNTArRFh5b2x1OEdoRXJ1VEplVld5bWFDUVRZcjBid2hLOGlYdDU3VHBaYXFoL25qa1VIenh4QTM1bVJ4VHhtT3cyNDJ0UVdMMFFMMll2MHJmTFJtK2ZGUkc1ZStQNVArMDVMckgyTGZjSW9hTi9zaEFZek9aR3dTSTJOS08raE9FTEt3Y1JnZStJR0NpcE9CVnNVM2psZGJxdWhXcEpGalYzQzdGZDVTUTNwQk0yanFvRWQwaUNpSGhzUnBjWStRbHljVXd1MzdBUnBHSXdTdndvNjZCOGFINHgyZzRqRmJkbjMyRFllUEFtMllTR3JvN0NJQ200Skw0TWNCdjR6eVZnSTNidDJOakV4WnRUeFppUkx0dndmRFFDU1h2WDRBa0dIVExyZEQyQXY2NUxoWDRaQ1pkZGp5eEVFWkN2SFFzNXRzUFF4ZnpEbzZjTmhRemVxYU44c3dhOFNRNDRjTkorZk1FS1lERVVmT2ZwUGhZU0lPR0NyRDN1dTdRM0g3d3VFZHRhV000UHNFdEdEcCtBcEpaK2tSMTBNUmozUFNUTlRId1lNTHNBb2tNMC9rM2FKL0EzODB4VDBEelREb0taUHU3Y3I5elhBeTkzeHdTQ3pieHRobk9vMkJtUnRqaVMrN281b1N6TExwTjZOSlV1UnlJQTdKejBKZnNwZ2pTRlFPSmZ5ditlRHRQVGJoODdOcHdPajdCdUFocmVEdURxTmRxd2hNY0ZubmNKa2FSbG9DeUs4dHptQ2R1SFZHMGJXb2IvV2xxa1k0U0huSy9vTXl1UE5HRnYvNm9LcmhSaEZmQTZpVDZPZ3hzL2IxSnFHY3V2dFErMmdKL2d1bVBZNDhVQ05STFJDSlp4VFpqaG14Smc1Q2tZUHdTRzlPU0JHazFRU01BPT0tLUQzTFB2aVJPaVhPZFU0TE9YMlNwdWc9PQ==--8746169c50ee5bd780c3c614a7a475abd524f9f2',
                                    'billingAddress': {
                                        'streetAddress': {
                                            'address1': 'Bijipur Main Road Sundar Nagar',
                                            'address2': '',
                                            'city': 'Brahmapur',
                                            'countryCode': 'IN',
                                            'postalCode': '760001',
                                            'firstName': 'Subham',
                                            'lastName': 'Kumar',
                                            'zoneCode': 'OR',
                                            'phone': '+917853878533',
                                        },
                                    },
                                    'paymentMethod': 'CREDIT_CARD',
                                    'paymentMethodIdentifier': '12ba72fffce249eb2764c19cac64fb92',
                                },
                            },
                        },
                        'walletsPlatformPaymentMethod': None,
                        'localPaymentMethod': None,
                        'paymentOnDeliveryMethod': None,
                        'paymentOnDeliveryMethod2': None,
                        'manualPaymentMethod': None,
                        'customPaymentMethod': None,
                        'offsitePaymentMethod': None,
                        'customOnsitePaymentMethod': None,
                        'deferredPaymentMethod': None,
                        'customerCreditCardPaymentMethod': None,
                        'paypalBillingAgreementPaymentMethod': None,
                        'remotePaymentInstrument': None,
                    },
                    'amount': {
                        'any': True,
                    },
                },
            ],
            'billingAddress': {
                'streetAddress': {
                    'address1': 'Bijipur Main Road Sundar Nagar',
                    'address2': '',
                    'city': 'Brahmapur',
                    'countryCode': 'IN',
                    'postalCode': '760001',
                    'firstName': 'Subham',
                    'lastName': 'Kumar',
                    'zoneCode': 'OR',
                    'phone': '+917853878533',
                },
            },
            'creditCardBin': '40089500',
            'allowStoreCredit': False,
        },
        'buyerIdentity': {
            'customer': {
                'presentmentCurrency': 'INR',
                'countryCode': 'IN',
            },
            'email': 'wizardlyaura999@gmail.com',
            'emailChanged': False,
            'phoneCountryCode': 'IN',
            'marketingConsent': [
                {
                    'email': {
                        'consentState': 'DECLINED',
                        'value': 'wizardlyaura999@gmail.com',
                    },
                },
            ],
            'shopPayOptInPhone': {
                'number': '+917853878533',
                'countryCode': 'IN',
            },
            'shopUserSecureData': 'eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s',
            'prefillSource': 'SHOP_PAY',
            'rememberMe': False,
        },
        'tip': {
            'tipLines': [],
        },
        'taxes': {
            'proposedAllocations': None,
            'proposedTotalAmount': {
                'value': {
                    'amount': '0',
                    'currencyCode': 'INR',
                },
            },
            'proposedTotalIncludedAmount': None,
            'proposedMixedStateTotalAmount': None,
            'proposedExemptions': [],
        },
        'note': {
            'message': None,
            'customAttributes': [],
        },
        'localizationExtension': {
            'fields': [],
        },
        'shopPayArtifact': {
            'shopUser': {
                'uuid': 'eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s',
            },
        },
        'nonNegotiableTerms': None,
        'scriptFingerprint': {
            'signature': None,
            'signatureUuid': None,
            'lineItemScriptChanges': [],
            'paymentScriptChanges': [],
            'shippingScriptChanges': [],
        },
        'optionalDuties': {
            'buyerRefusesDuties': False,
        },
        'cartMetafields': [],
    },
    'operationName': 'Proposal',
    'id': '218ca3f4634df050ead785d9692d50bc444d93ef926a6c0d820c1c01a02d474f',
}

response = requests.post(
    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"sessionInput":{"sessionToken":"AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew"},"queueToken":"AxgaZG9f7b6IJjHw38EE3GrbpkKkB3GYMiDi7SHPoAc0tEYZH5c4iSY-U7WQzYJ0NuEaewvQJc_PTj0DYGTLxusIhS8XisE9zEMGTlD3f2v4IuH2lrMj_eM-NGbTP7uRzg==","discounts":{"lines":[],"acceptUnexpectedDiscounts":true},"delivery":{"deliveryLines":[{"destination":{"partialStreetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533","oneTimeUse":false}},"selectedDeliveryStrategy":{"deliveryStrategyByHandle":{"handle":"daadf5d473ea94fde5b8c3a5893e2c72-1857f5edbd56cb87c7e3af188778f2e4","customDeliveryRate":false},"options":{"phone":"+917853878533"}},"targetMerchandiseLines":{"lines":[{"stableId":"9720debd-5883-45ef-bf0d-fdc7d9558d88"}]},"deliveryMethodTypes":["SHIPPING"],"expectedTotalPrice":{"value":{"amount":"1700.00","currencyCode":"INR"}},"destinationChanged":false}],"noDeliveryRequired":[],"useProgressiveRates":false,"prefetchShippingRatesStrategy":null,"interfaceFlow":"SHOP_PAY","supportsSplitShipping":true},"deliveryExpectations":{"deliveryExpectationLines":[{"signedHandle":"JtrIwQhz1zKpMDJcEVzpg4VS8UIp0/2JdzVu1lLNDYIEGik4MAwFBP+ZSBen45iacN/vVuOSTwH4XFzHytdV973s3yL0FgA2cEKgi0ICLASR5lDtAsfTbM+jzmnfzlMHXvE5uNTK3UvLZ3qMcntYG4HCjYgdYwwQIObanTd4VE+bgoJZ8hzQW1uWEZkMsK9wmTpKBWIbEr1ISYg17h+pkoMEdmxfCYWRimBKs28UCn6G4l7zKDGRK48iH9kkeJq7x8pXNurr01RP4YXx3yZlSGn0oqyDVT+VGwdEDlrrT26Fyi6AxxJeVpgyJ33aycCDIogsqjiGvFO295kd1fY+nYlbIWwIyrSKIKuxIB0Flraj/GuFg2mKnoBb9K25LA7xAQ8wiqmerrTrL3FFMgoC8y8Zvf+sGvOOaEWZgR9+H1OcXQ7W72oHKw7brfAMicZB4/NVRgyAIhivnZhGemXTRx9RuPwe4tT/Oh90iAapsADmccl30B0L6Mq+K9cpaVQu1PZlYiL+UVHR6Sea1uyY69cDTqrHmYw3nNlwP5sO6j/jeusgP3Ppi6C2ljgV/+AVcRvGcdWdTo7U9IBivbI+gdbYMdtMTp2Gcjoji+T+USM8HzBuKWcBZHqqgu9gN7bEE8cyA8qWs2iA677liuoWDQB9x/rKHeGnylXUEc2BLyz7S0myhA4KUjsUw0wAk6RWUS3PW4WqwblOQK5iOZJ9EZ2nw0grTZruIskbB5xKTrvw4rtFezSTeCBxMS/NjkUOR06GWWrnY46nIj2gxekYVRQkpWr2WqLcChH7toS0gophzYVG5stW5lnlKaXCPchTWRolADzOjMx0cDtUm+XIW3v59RUjbj+a4l9yw3+CkoZgB0O2ZknVTG5vsdeKQB/2IiOlEohilfs0TM6lsWkYbsUBOoplfYvWBn4yNIyc1Gcxw/99jBqRA5/4FbfYnp2MXEntEvKVAvmX0O4AAyNjISO/kd8/qmRPY9W6UUM61uLRin1D+wLyw7hePlyl4kvg30mKI6DnaxxyuhN01KNXl2wLWgbkSKayJM7ePJcSbWdyiczQMFRaj3lMqHEfBNqntcbk4Mrk5+cjQU9QE/mcrgwu0/o9QD9qjVMCgJJgQO7Rd/BpSbS2Qb7kjwfnnyCJly0g7aLrY+yMyJZo7YQHdMo04thNxtRWOJiRaguIqmLjYFjAWXlV7WdAeYop/ULFn8WjMTPKiK5AaB1QhzowDuWRJVeMhqDwJViOYXT3RENq2ba1xXb9ISDqyZsOjpAK7dHu4qz+r7IPoJILh+Lx88um8TJv8ZX4pNAA4/ltTD6oQ8PoDXeFlpXtlibODkWTqFf3NrTW369ATf0lzZARawuU3fDyHsaGbR8DYz/9P20rfsg0OjyYc0sKz3y6/MG/5FnTD/4nJ+nZgQJWMMb4zsRAneBDS0wAOQ4GyAjsqmRL6M09PVyHCLk2QVSlEc8HWgulPXFjPs5mYRVhYLys31CNfOOllKI0enjR3afK0GWjrdaCAmCCDd4FG2C99AQO--tnPVvH4t8iXFOe5w--VE1ObAnUQ4Eq6Pd19h2Lcw=="}]},"merchandise":{"merchandiseLines":[{"stableId":"9720debd-5883-45ef-bf0d-fdc7d9558d88","merchandise":{"productVariantReference":{"id":"gid://shopify/ProductVariantMerchandise/51732384481626","variantId":"gid://shopify/ProductVariant/51732384481626","properties":[],"sellingPlanId":null,"sellingPlanDigest":null}},"quantity":{"items":{"value":1}},"expectedTotalPrice":{"value":{"amount":"4100.00","currencyCode":"INR"}},"lineComponentsSource":null,"lineComponents":[]}]},"memberships":{"memberships":[]},"payment":{"totalAmount":{"any":true},"paymentLines":[{"paymentMethod":{"directPaymentMethod":null,"giftCardPaymentMethod":null,"ownedGiftCardPaymentMethod":null,"redeemablePaymentMethod":null,"walletPaymentMethod":{"name":"SHOP_PAY","walletContent":{"shopPayWalletContent":{"sessionToken":"spt_S1JySVppZTRiRUJsRzBxeDRVeWtaS0dHTXFXanNXM0RuV01NZlNtY1hwZVo3YmkzQjRZYytGdG1rZmF4dGZzcmFZd05VWUx6Qmx6OG1RcGluRGJlSHc5a3dJRFJCbVZ6MVdxSmZURUt5cldOUWNwMDkrTGZYYzFuclI4akZBRHJPWkEyQm1PWGJrK24yYzArZnI1ZCtoOENtVGF2QlozUTMrZk82T0pXR2ljbTFYSDRiY3pjejRZU0lhdU9INVlHSnJ4d3h4ZzdOSGY2bnUzTWZLcmd2TWs0VWJlRDdmaE5CUzFJUFZzZ3d4dCt0NE9mMkFVSGJDa09GOU8zcHdEUDB6WTgxL3FyU25XRnU5TmFPcm1adEtNK2Q0V25kc25wUzRCb0hsNVNFRHREb2QzMnp3Z1FRR2tKVFVjVG1Nb1lBeXVjRHVrbkRhNHRkclQxTmZhOU9nRExpUm1lYlFWbzVwdzYxRGVFVUVaUGZZWlIxOWM1eEk0WlVIdUl2WDk1QTlxTU4yT09KVldXMjFzbDU5akFHTFF4T3RpUU90QTkrWkZ2UmRpOGU5bGM1a3dDZE5JT3pUaW10QUx6Tkl1ME9lRFNBYjFlWWdZNlNmRlcvNmhMQXo1YmtWcGxwZHhuQW1Dd1pMbHpLdW9LUXFyYkpRN2dWV200eEhqVmJmV2hRdW5VT2M5Sk1LeWlZYWlqS0FqZXRTR05sL1duYnlqR0s2MWRsZ3hGSDRHVWNOSnNveEpzY3ZyS1NhMTlxYUJ6UlBzV0FiVkdnOFVRRmc0UmlLT2p0UFpzSWNFMVJlSng2RTRpVFA0cmRPVC9HMUtzblBrUzdRZDM4NE54TkVqQmNKcjdic3NRV3g2WHg0anpTbTFFQ05EWEx4dU5TaUQxZytOdkhleUR5Qjc2ZEk0TUxZczJOTTZvTTZIbVgzWjNSUWtJazRMMUdCbDZlSCtURTFBMWxkSXJNNXozVVJudGFYS1BkR0lqL1UrM2FBY25mR2VlNEF5YUtlSDN5Uk1heDRkd0doYTZiQUxRRWtSMXY4dFNQbHNqYlhjNnhJRlk4YlpTUDI3emEzRGdoS1VLaGtJeUd1dW1CVkJpNHBKL25jMFZjSmduYnc0cGhzYUV1MFptblZET3BMdCtBLzhyQ3U2U0hCK085bmxqMjladkZzVEhLbU1xeVBJVWwyMjJ4bk9qSkJ3SEhuU1ZpL2o3MU1KQkFBSWMrSGJRN24rTEl6ZVlLaFh5TW9NeWJzWnhlNjJpbWthZ05QOHV0WkFUMHNhRzRKS3dtNDd4bEs4YkwzR0tqK2pkUm1xZEFZbm1KTXZqcFZkSTIzV0FtNTArRFh5b2x1OEdoRXJ1VEplVld5bWFDUVRZcjBid2hLOGlYdDU3VHBaYXFoL25qa1VIenh4QTM1bVJ4VHhtT3cyNDJ0UVdMMFFMMll2MHJmTFJtK2ZGUkc1ZStQNVArMDVMckgyTGZjSW9hTi9zaEFZek9aR3dTSTJOS08raE9FTEt3Y1JnZStJR0NpcE9CVnNVM2psZGJxdWhXcEpGalYzQzdGZDVTUTNwQk0yanFvRWQwaUNpSGhzUnBjWStRbHljVXd1MzdBUnBHSXdTdndvNjZCOGFINHgyZzRqRmJkbjMyRFllUEFtMllTR3JvN0NJQ200Skw0TWNCdjR6eVZnSTNidDJOakV4WnRUeFppUkx0dndmRFFDU1h2WDRBa0dIVExyZEQyQXY2NUxoWDRaQ1pkZGp5eEVFWkN2SFFzNXRzUFF4ZnpEbzZjTmhRemVxYU44c3dhOFNRNDRjTkorZk1FS1lERVVmT2ZwUGhZU0lPR0NyRDN1dTdRM0g3d3VFZHRhV000UHNFdEdEcCtBcEpaK2tSMTBNUmozUFNUTlRId1lNTHNBb2tNMC9rM2FKL0EzODB4VDBEelREb0taUHU3Y3I5elhBeTkzeHdTQ3pieHRobk9vMkJtUnRqaVMrN281b1N6TExwTjZOSlV1UnlJQTdKejBKZnNwZ2pTRlFPSmZ5ditlRHRQVGJoODdOcHdPajdCdUFocmVEdURxTmRxd2hNY0ZubmNKa2FSbG9DeUs4dHptQ2R1SFZHMGJXb2IvV2xxa1k0U0huSy9vTXl1UE5HRnYvNm9LcmhSaEZmQTZpVDZPZ3hzL2IxSnFHY3V2dFErMmdKL2d1bVBZNDhVQ05STFJDSlp4VFpqaG14Smc1Q2tZUHdTRzlPU0JHazFRU01BPT0tLUQzTFB2aVJPaVhPZFU0TE9YMlNwdWc9PQ==--8746169c50ee5bd780c3c614a7a475abd524f9f2","billingAddress":{"streetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533"}},"paymentMethod":"CREDIT_CARD","paymentMethodIdentifier":"12ba72fffce249eb2764c19cac64fb92"}}},"walletsPlatformPaymentMethod":null,"localPaymentMethod":null,"paymentOnDeliveryMethod":null,"paymentOnDeliveryMethod2":null,"manualPaymentMethod":null,"customPaymentMethod":null,"offsitePaymentMethod":null,"customOnsitePaymentMethod":null,"deferredPaymentMethod":null,"customerCreditCardPaymentMethod":null,"paypalBillingAgreementPaymentMethod":null,"remotePaymentInstrument":null},"amount":{"any":true}}],"billingAddress":{"streetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533"}},"creditCardBin":"40089500","allowStoreCredit":false},"buyerIdentity":{"customer":{"presentmentCurrency":"INR","countryCode":"IN"},"email":"wizardlyaura999@gmail.com","emailChanged":false,"phoneCountryCode":"IN","marketingConsent":[{"email":{"consentState":"DECLINED","value":"wizardlyaura999@gmail.com"}}],"shopPayOptInPhone":{"number":"+917853878533","countryCode":"IN"},"shopUserSecureData":"eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s","prefillSource":"SHOP_PAY","rememberMe":false},"tip":{"tipLines":[]},"taxes":{"proposedAllocations":null,"proposedTotalAmount":{"value":{"amount":"0","currencyCode":"INR"}},"proposedTotalIncludedAmount":null,"proposedMixedStateTotalAmount":null,"proposedExemptions":[]},"note":{"message":null,"customAttributes":[]},"localizationExtension":{"fields":[]},"shopPayArtifact":{"shopUser":{"uuid":"eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s"}},"nonNegotiableTerms":null,"scriptFingerprint":{"signature":null,"signatureUuid":null,"lineItemScriptChanges":[],"paymentScriptChanges":[],"shippingScriptChanges":[]},"optionalDuties":{"buyerRefusesDuties":false},"cartMetafields":[]},"operationName":"Proposal","id":"218ca3f4634df050ead785d9692d50bc444d93ef926a6c0d820c1c01a02d474f"}'
#response = requests.post(
#    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
#    params=params,
#    cookies=cookies,
#    headers=headers,
#    data=data,
#)




import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': 'id="hWNI32WWbY08l1Arphk2EFho", type="cn"',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-one-session-token': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shop-pay-token': 'eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaWQ6XC9cL3Nob3BpZnlcL1Nob3BcLzkyNTU0NDk0Mjk4IiwibmJmIjoxNzkyMTc5ODAxLCJzZXNzaW9uX3Rva2VuIjoiQUFFQld5Y0M5RnFEU19Lblg0MURKb1gzOF9RcjQwOVZZSnZfMU9fdTlVcURPMm5JSzh6RWpycDNqR0lpUDJzVi1lSy1WSVJPa3V4MmFGeWt2c2R1TndyS3BJQ00xQmxrNXdMVUgtMlVIeUU5UWFiQzJRcEd4dVdVa2x5dkNQRlYteXNOUVg3M29ITkEzNjlhYWVPdTh0by1lYnRMU3dKYzhqelZaSVF2MjROcmoxYU5OcmZrSno3d3VfM0ZMRVFPZF9USkxTMVlZVlB5TkdtRlA4OU94Q25Dc3VJYVJvcm9nMFN6dmV3Iiwic2Vzc2lvbl9jdXN0b21lcl9pZCI6MTA1MDczNjk4NDA5ODYsInNob3BfYWNjb3VudF91dWlkIjoiYTQ2ZWJiODUtNjc0Ny00NzhjLWE3ZmUtOTc5NDBjYzRiMWZmIiwic2hvcF9wYXlfZGF0YSI6IkNBSVNHWGRwZW1GeVpHeDVZWFZ5WVRrNU9VQm5iV0ZwYkM1amIyMGFFaGV3SEtTZEF1YVBZWVVfdkNNM3QwVU9oQ0lRcEc2N2hXZEhSNHluX3BlVURNU3hfempZX01uV0Jrb1NETm9uTXNVV2ZrX19wbHkwUTRDZGwxMEUiLCJjdXN0b21lcl9hdXRoZW50aWNhdGlvbl9hdXRoX3Byb3ZpZGVyIjoibG9naW5fd2l0aF9zaG9wIiwiZXhwIjoxNzkyMTgzNDAxLCJsYW5kaW5nX3BhZ2UiOiJcLyIsIm9yaWdfcmVmZXJyZXIiOiIiLCJtZXJjaGFudF9jb25zZW50IjoiM0FNUC5TIn0.eJ_036fE8fV7VlRQ_VrMQfgnE1KbP_duYqno-fhCrA0',
    'x-shopify-tracking-consent': '3S.AMP',
    'x-shopify-uniquetoken': 'c1e69033-8b91-45e6-8e70-d2adaeca3fe5',
    'x-shopify-visittoken': '9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2',
}

params = {
    'operationName': 'Proposal',
}

json_data = {
    'variables': {
        'sessionInput': {
            'sessionToken': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
        },
        'queueToken': 'A6rkplwGnj-KM9CneC7x9OU8NYuS7png6LtK1GcgmR0yjPOb9iaNjQSwM4uYejg9HQiACpUoc_ffTNMMTmY3AB238TICWNvsbBKnSVGqvv_0OgPx_J8uA--bLCgzQ-Tnng==',
        'discounts': {
            'lines': [],
            'acceptUnexpectedDiscounts': True,
        },
        'delivery': {
            'deliveryLines': [
                {
                    'destination': {
                        'partialStreetAddress': {
                            'address1': 'Bijipur Main Road Sundar Nagar',
                            'address2': '',
                            'city': 'Brahmapur',
                            'countryCode': 'IN',
                            'postalCode': '760001',
                            'firstName': 'Subham',
                            'lastName': 'Kumar',
                            'zoneCode': 'OR',
                            'phone': '+917853878533',
                            'oneTimeUse': False,
                        },
                    },
                    'selectedDeliveryStrategy': {
                        'deliveryStrategyByHandle': {
                            'handle': 'daadf5d473ea94fde5b8c3a5893e2c72-1857f5edbd56cb87c7e3af188778f2e4',
                            'customDeliveryRate': False,
                        },
                        'options': {
                            'phone': '+917853878533',
                        },
                    },
                    'targetMerchandiseLines': {
                        'lines': [
                            {
                                'stableId': '9720debd-5883-45ef-bf0d-fdc7d9558d88',
                            },
                        ],
                    },
                    'deliveryMethodTypes': [
                        'SHIPPING',
                    ],
                    'expectedTotalPrice': {
                        'value': {
                            'amount': '1700.00',
                            'currencyCode': 'INR',
                        },
                    },
                    'destinationChanged': False,
                },
            ],
            'noDeliveryRequired': [],
            'useProgressiveRates': False,
            'prefetchShippingRatesStrategy': None,
            'interfaceFlow': 'SHOP_PAY',
            'supportsSplitShipping': True,
        },
        'deliveryExpectations': {
            'deliveryExpectationLines': [
                {
                    'signedHandle': 'D5DqiQGpuZ58m58WZ9e8B9cyr5mHF6aF5gFM4fssy4g35yLVYZv6lwiHWwQJ0BSdpGSfulS1beFK+aXmq+Z01N5I/o6aSlH3f7LtTqzQs+7xPvg8LzfyS6rSXEBfRnpF9hlw8JCQW4Ui52f2wkANeqMI62+Mzn/j1qnNE6s3j3eWoXR7ny6FrGK0c/wItVv8SShA95aY3XBOOVtsHNqoIPOM7Sjtvj+fErgIxCEYZtYBUqkw8OHB+ffAth7rezNFim9Vq8mRRtyr5hQH1YfgEnylJm/WBeqoyjiahrNDhwXicOdYN7jbMiQYznN0kSIsVVDEzOrlAbhOVUbtOAU5zQMQXv8gC3AxBsS7Td4xd1gN91LthZgRuqo3vLqSzHKwGQFaeUUdrZk1rSX4hxmiC2qFdIQ5DuRx+fQD6KT9BYEdubtQ7IobwjhH/K0S6QGVtCtEwQW0SMUdVaUHO6M8ZE4u1PhacTp7VVAlP5QBSrP+NBvslqIDSFObzDvwUUFe/veuP3GEqKeoAaz51FLQnDT+uPNNWvKmeBir2+EHQD/IbqpT0GiG7MulgCbc4PATMizTkit5XDNUo1Jp/3uj9b2oQlj6aREGGYIP6B/aawn2QHapaFNBV4qejw4u+NtuCKTpmXG0JTm8uDq4+Zi4hEeUg1M6TtSuMxJWnjFA1fBzM8Au6y3DR83KVxNADhkAvjpjmoUv0//WfuelxkvxEng4vWuSH//lkSWFSgQ5NkGL8/YGX2aPyzTuSSO26luMVyKoa0poK4MlAYMix+fK9+gRJVxnzl52rgf4h5qE9plhzPeNXUyZ5I63U72txY/ouM0SP7f+QzR2mCxO9vYJHKKPnkWIVGL8guDpfL0pKd2xnKl+dFEjLeNVq9ZRJoY6rbS//J7RfKCqed+t8AS1/sjQdKt2fMnBJeHHSz5HffTuSqiXYrmq1HgNFml46IRFjeNpPWODBXwBmGBhzqG4lhCa15p6SNtr2rnUCX/b2bV0gvNHXbxiTAiz7NBnbp6qwy5Fk5IDLcJghqsLMuRRke2PD8khhhndvMiy0nhHi+d6Y8sb45TRDVtRhUpuzEpxq/Tj+564VfGaVnZbf5slfpH0k0qUe98MsEJUaTTTkTx/IdvBESzWZR4phlk2nPUnnu/bsaBr12WWg3RxWpGpQNVAvHMLySy4LkymNbBY8rCBw1dHGOlgWuTNjLVKQrjylc7n0H7D90yo7/j1/CrrXPaGfEVBNCIghbElb97+Z3wfFnxDZ0dRCYPgh9Z+rLVYA9sgHv7GyLgbyM5JXmcV7PeAk5rN6Rgsq9dNz4YzXHz30K37VEbi5lbC4R9342uk0vG6vp/CZTWuYKnkphFy4qSMP+t4bYzMTEyTCMeDQsXKrpnI1z71k0oIYF3nGgZ5BWmFGtGQSiX6W1MWPktuAxie4OenQT5woDj4hIzDt5vWUx6yLqRATL1zE550fjTgeezHAk4gLttGiuwdsliItoqPC3ljr3z+CBpkgFvXXVGiK6raceEgqSMcbdR4NZF2--deCcoSZR6Rp7QwDA--hUcZEd7/bw9BWVBrdcUeiA==',
                },
            ],
        },
        'merchandise': {
            'merchandiseLines': [
                {
                    'stableId': '9720debd-5883-45ef-bf0d-fdc7d9558d88',
                    'merchandise': {
                        'productVariantReference': {
                            'id': 'gid://shopify/ProductVariantMerchandise/51732384481626',
                            'variantId': 'gid://shopify/ProductVariant/51732384481626',
                            'properties': [],
                            'sellingPlanId': None,
                            'sellingPlanDigest': None,
                        },
                    },
                    'quantity': {
                        'items': {
                            'value': 1,
                        },
                    },
                    'expectedTotalPrice': {
                        'value': {
                            'amount': '4100.00',
                            'currencyCode': 'INR',
                        },
                    },
                    'lineComponentsSource': None,
                    'lineComponents': [],
                },
            ],
        },
        'memberships': {
            'memberships': [],
        },
        'payment': {
            'totalAmount': {
                'any': True,
            },
            'paymentLines': [
                {
                    'paymentMethod': {
                        'directPaymentMethod': None,
                        'giftCardPaymentMethod': None,
                        'ownedGiftCardPaymentMethod': None,
                        'redeemablePaymentMethod': None,
                        'walletPaymentMethod': {
                            'name': 'SHOP_PAY',
                            'walletContent': {
                                'shopPayWalletContent': {
                                    'sessionToken': 'spt_S1JySVppZTRiRUJsRzBxeDRVeWtaS0dHTXFXanNXM0RuV01NZlNtY1hwZVo3YmkzQjRZYytGdG1rZmF4dGZzcmFZd05VWUx6Qmx6OG1RcGluRGJlSHc5a3dJRFJCbVZ6MVdxSmZURUt5cldOUWNwMDkrTGZYYzFuclI4akZBRHJPWkEyQm1PWGJrK24yYzArZnI1ZCtoOENtVGF2QlozUTMrZk82T0pXR2ljbTFYSDRiY3pjejRZU0lhdU9INVlHSnJ4d3h4ZzdOSGY2bnUzTWZLcmd2TWs0VWJlRDdmaE5CUzFJUFZzZ3d4dCt0NE9mMkFVSGJDa09GOU8zcHdEUDB6WTgxL3FyU25XRnU5TmFPcm1adEtNK2Q0V25kc25wUzRCb0hsNVNFRHREb2QzMnp3Z1FRR2tKVFVjVG1Nb1lBeXVjRHVrbkRhNHRkclQxTmZhOU9nRExpUm1lYlFWbzVwdzYxRGVFVUVaUGZZWlIxOWM1eEk0WlVIdUl2WDk1QTlxTU4yT09KVldXMjFzbDU5akFHTFF4T3RpUU90QTkrWkZ2UmRpOGU5bGM1a3dDZE5JT3pUaW10QUx6Tkl1ME9lRFNBYjFlWWdZNlNmRlcvNmhMQXo1YmtWcGxwZHhuQW1Dd1pMbHpLdW9LUXFyYkpRN2dWV200eEhqVmJmV2hRdW5VT2M5Sk1LeWlZYWlqS0FqZXRTR05sL1duYnlqR0s2MWRsZ3hGSDRHVWNOSnNveEpzY3ZyS1NhMTlxYUJ6UlBzV0FiVkdnOFVRRmc0UmlLT2p0UFpzSWNFMVJlSng2RTRpVFA0cmRPVC9HMUtzblBrUzdRZDM4NE54TkVqQmNKcjdic3NRV3g2WHg0anpTbTFFQ05EWEx4dU5TaUQxZytOdkhleUR5Qjc2ZEk0TUxZczJOTTZvTTZIbVgzWjNSUWtJazRMMUdCbDZlSCtURTFBMWxkSXJNNXozVVJudGFYS1BkR0lqL1UrM2FBY25mR2VlNEF5YUtlSDN5Uk1heDRkd0doYTZiQUxRRWtSMXY4dFNQbHNqYlhjNnhJRlk4YlpTUDI3emEzRGdoS1VLaGtJeUd1dW1CVkJpNHBKL25jMFZjSmduYnc0cGhzYUV1MFptblZET3BMdCtBLzhyQ3U2U0hCK085bmxqMjladkZzVEhLbU1xeVBJVWwyMjJ4bk9qSkJ3SEhuU1ZpL2o3MU1KQkFBSWMrSGJRN24rTEl6ZVlLaFh5TW9NeWJzWnhlNjJpbWthZ05QOHV0WkFUMHNhRzRKS3dtNDd4bEs4YkwzR0tqK2pkUm1xZEFZbm1KTXZqcFZkSTIzV0FtNTArRFh5b2x1OEdoRXJ1VEplVld5bWFDUVRZcjBid2hLOGlYdDU3VHBaYXFoL25qa1VIenh4QTM1bVJ4VHhtT3cyNDJ0UVdMMFFMMll2MHJmTFJtK2ZGUkc1ZStQNVArMDVMckgyTGZjSW9hTi9zaEFZek9aR3dTSTJOS08raE9FTEt3Y1JnZStJR0NpcE9CVnNVM2psZGJxdWhXcEpGalYzQzdGZDVTUTNwQk0yanFvRWQwaUNpSGhzUnBjWStRbHljVXd1MzdBUnBHSXdTdndvNjZCOGFINHgyZzRqRmJkbjMyRFllUEFtMllTR3JvN0NJQ200Skw0TWNCdjR6eVZnSTNidDJOakV4WnRUeFppUkx0dndmRFFDU1h2WDRBa0dIVExyZEQyQXY2NUxoWDRaQ1pkZGp5eEVFWkN2SFFzNXRzUFF4ZnpEbzZjTmhRemVxYU44c3dhOFNRNDRjTkorZk1FS1lERVVmT2ZwUGhZU0lPR0NyRDN1dTdRM0g3d3VFZHRhV000UHNFdEdEcCtBcEpaK2tSMTBNUmozUFNUTlRId1lNTHNBb2tNMC9rM2FKL0EzODB4VDBEelREb0taUHU3Y3I5elhBeTkzeHdTQ3pieHRobk9vMkJtUnRqaVMrN281b1N6TExwTjZOSlV1UnlJQTdKejBKZnNwZ2pTRlFPSmZ5ditlRHRQVGJoODdOcHdPajdCdUFocmVEdURxTmRxd2hNY0ZubmNKa2FSbG9DeUs4dHptQ2R1SFZHMGJXb2IvV2xxa1k0U0huSy9vTXl1UE5HRnYvNm9LcmhSaEZmQTZpVDZPZ3hzL2IxSnFHY3V2dFErMmdKL2d1bVBZNDhVQ05STFJDSlp4VFpqaG14Smc1Q2tZUHdTRzlPU0JHazFRU01BPT0tLUQzTFB2aVJPaVhPZFU0TE9YMlNwdWc9PQ==--8746169c50ee5bd780c3c614a7a475abd524f9f2',
                                    'billingAddress': {
                                        'streetAddress': {
                                            'address1': 'Bijipur Main Road Sundar Nagar',
                                            'city': 'Brahmapur',
                                            'countryCode': 'IN',
                                            'postalCode': '760001',
                                            'firstName': 'Subham',
                                            'lastName': 'Kumar',
                                            'zoneCode': 'OR',
                                            'phone': '+917853878533',
                                        },
                                    },
                                    'paymentMethod': 'CREDIT_CARD',
                                    'paymentMethodIdentifier': '12ba72fffce249eb2764c19cac64fb92',
                                    'hsaRequested': False,
                                },
                            },
                        },
                        'walletsPlatformPaymentMethod': None,
                        'localPaymentMethod': None,
                        'paymentOnDeliveryMethod': None,
                        'paymentOnDeliveryMethod2': None,
                        'manualPaymentMethod': None,
                        'customPaymentMethod': None,
                        'offsitePaymentMethod': None,
                        'customOnsitePaymentMethod': None,
                        'deferredPaymentMethod': None,
                        'customerCreditCardPaymentMethod': None,
                        'paypalBillingAgreementPaymentMethod': None,
                        'remotePaymentInstrument': None,
                    },
                    'amount': {
                        'any': True,
                    },
                },
            ],
            'billingAddress': {
                'streetAddress': {
                    'address1': 'Bijipur Main Road Sundar Nagar',
                    'address2': '',
                    'city': 'Brahmapur',
                    'countryCode': 'IN',
                    'postalCode': '760001',
                    'firstName': 'Subham',
                    'lastName': 'Kumar',
                    'zoneCode': 'OR',
                    'phone': '+917853878533',
                },
            },
            'creditCardBin': '40089500',
            'allowStoreCredit': False,
        },
        'buyerIdentity': {
            'customer': {
                'presentmentCurrency': 'INR',
                'countryCode': 'IN',
            },
            'email': 'wizardlyaura999@gmail.com',
            'emailChanged': False,
            'phoneCountryCode': 'IN',
            'marketingConsent': [
                {
                    'email': {
                        'consentState': 'DECLINED',
                        'value': 'wizardlyaura999@gmail.com',
                    },
                },
            ],
            'shopPayOptInPhone': {
                'number': '+917853878533',
                'countryCode': 'IN',
            },
            'shopUserSecureData': 'eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s',
            'prefillSource': 'SHOP_PAY',
            'rememberMe': False,
        },
        'tip': {
            'tipLines': [],
        },
        'taxes': {
            'proposedAllocations': None,
            'proposedTotalAmount': {
                'value': {
                    'amount': '0',
                    'currencyCode': 'INR',
                },
            },
            'proposedTotalIncludedAmount': None,
            'proposedMixedStateTotalAmount': None,
            'proposedExemptions': [],
        },
        'note': {
            'message': None,
            'customAttributes': [],
        },
        'localizationExtension': {
            'fields': [],
        },
        'shopPayArtifact': {
            'shopUser': {
                'uuid': 'eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s',
            },
        },
        'nonNegotiableTerms': None,
        'scriptFingerprint': {
            'signature': None,
            'signatureUuid': None,
            'lineItemScriptChanges': [],
            'paymentScriptChanges': [],
            'shippingScriptChanges': [],
        },
        'optionalDuties': {
            'buyerRefusesDuties': False,
        },
        'captcha': {
            'provider': 'hcaptcha',
            'challenge': 'comparison_challenge_type',
            'token': 'P1_eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.3gAHp3Bhc3NrZXnFBHR8Nu7dGvRjHJZWFQ5ftoV87npezg1Of8eb3el70cTYlkQyU9D-A1L0NP4tG0CAjXGnhUE7yp7CHEiQ6SB4bvxrb97mbRcgYkwQ1UVBlesg8zxjgWEa7JHzZYovuDl1oSs4syrJp6A_pVyFw2iKafJcgBjQ9862V1mkIioYjJp3cU1exp4hrUU5cqNM7ZO4f9424I1WSIZMullCsXR4CI2WxK6TO05Xe_RHORal0w1Jz5YHzBMr7O0Q4ijsuOgLA5u3a0mvG8nhz88pR9LzF8s--LQkyoQs2whEvhZFEU7cCzmBHA_kjzr6uEyn-Jfes-t-WAd-1tHco-dCXrJeZhC_VhjXmNUHoSFwx7Uvn0x_o2dgzLKpUKCTD82VcjrwVUggHRZheSGkzF1HIdsE4-cqpeDgKQIIufoHySFC1HsBcexgEE7MmPcR-K1AswC5GrMmbEMFvZ1sPIlfBiIeO3M_jMRAcYgNLFdb0Wpg5QIktwpME1agAavpK_2JZz_32VmxlJCCKe61Trj9yzkHLhwvQhl8fHjh3tBDlTufveuRw00VyBO-gPKKzAWEk1cDBhcxlE3RrG3HlHrwjQSLB1TR5Nj-yPWVEb-MD8l62czV0gI_rh0Rs4M96Iv4OX4I5zf2h1T_69tuo5FDujvyM4_hIyNmagn6Kg65e7zF4MsfWbMHZDTs0yuDr5CRC3zZmsTRQM5SpIv3rHs-LAJU-tDAV8U7MvXYT1RVlkVcYPB0FVtWmaaKeBVV7X3RpsXZ_QZruPBam4txZR837_vy6w-YHn-2AhYDTjOdH0s7gNM7pcK5qrzabNtmIOrRuEEPLei8jdagG7sTEEEoc9hFNmsnPWkwxymHxExPL-CfDqUQHb1hCqSAriUin1OyjNq3BhdHFGEMjR03nui3MDssCwrRmH3Lr6dzMLGvX777Nvyb5-LG5skt8jPR48CvceG30WScw1rN92sQmgY1Ac-tqg48yuDTewBrXGo-oXttCsYLd6Gp_sqNFjgaFCPt9pxHwP196DNPIBk9zT3E2i__RiGE5NnJ517DbbLhBXXk7ZyBqi9EzggnrGc8A-f38a67VLd_3xL8ZiAvH-zVeOKSOAG5CoJgXQy90qEl6s0Tllo_PUJgcqVgHMZMweLxLmcPVSaxlpfc07p1cEFA4j1X6JLhv045diod5fNR6OFIZouPp9js8Vp6HlBTXz9HV5Uk8C0c_jZfixC-PyXGrkbnYeZh-mtNq6Z6cIcNUFY76sVhKo7QNPa3wFLn6eu-Dzz6IHI969ybTtL6Wq6xiA-wzceDbHVIyt2Fu0RTzAv0FkWrMR2Z1IkfGQb5gCfkGODE7ibKbRWrSsbpeoFdIr107Gyja4URRzf5KHOLboqgce9lP9FKyFHrAgzso6q7LsCWGlEjNcJBVzqfcs46aJw6WA6ZRigeb4ICzvAA3KluwQPxrqOWaEnM2D_th17kXnYXgeR9NSkRhqgHwlKyKSaMxdpMZv7ExwBaCD4u50-c6ZVFyjdrfq-nc2l0ZWtledkkMWYyNjIzYjEtZWIxOS00OTE2LThiNDMtMDg0YThhNzg1YjIzo2V4cM5q0n9jonBkAKVjZGF0YdQAAKZjZGF0YTLUAACia3KoM2E1YWFiNmU.MF_TS7zYc2wPr3_WzUBV1x0sOyZaDNRM5PSg0nrKHHU',
        },
        'cartMetafields': [],
    },
    'operationName': 'Proposal',
    'id': '218ca3f4634df050ead785d9692d50bc444d93ef926a6c0d820c1c01a02d474f',
}

response = requests.post(
    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"sessionInput":{"sessionToken":"AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew"},"queueToken":"A6rkplwGnj-KM9CneC7x9OU8NYuS7png6LtK1GcgmR0yjPOb9iaNjQSwM4uYejg9HQiACpUoc_ffTNMMTmY3AB238TICWNvsbBKnSVGqvv_0OgPx_J8uA--bLCgzQ-Tnng==","discounts":{"lines":[],"acceptUnexpectedDiscounts":true},"delivery":{"deliveryLines":[{"destination":{"partialStreetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533","oneTimeUse":false}},"selectedDeliveryStrategy":{"deliveryStrategyByHandle":{"handle":"daadf5d473ea94fde5b8c3a5893e2c72-1857f5edbd56cb87c7e3af188778f2e4","customDeliveryRate":false},"options":{"phone":"+917853878533"}},"targetMerchandiseLines":{"lines":[{"stableId":"9720debd-5883-45ef-bf0d-fdc7d9558d88"}]},"deliveryMethodTypes":["SHIPPING"],"expectedTotalPrice":{"value":{"amount":"1700.00","currencyCode":"INR"}},"destinationChanged":false}],"noDeliveryRequired":[],"useProgressiveRates":false,"prefetchShippingRatesStrategy":null,"interfaceFlow":"SHOP_PAY","supportsSplitShipping":true},"deliveryExpectations":{"deliveryExpectationLines":[{"signedHandle":"D5DqiQGpuZ58m58WZ9e8B9cyr5mHF6aF5gFM4fssy4g35yLVYZv6lwiHWwQJ0BSdpGSfulS1beFK+aXmq+Z01N5I/o6aSlH3f7LtTqzQs+7xPvg8LzfyS6rSXEBfRnpF9hlw8JCQW4Ui52f2wkANeqMI62+Mzn/j1qnNE6s3j3eWoXR7ny6FrGK0c/wItVv8SShA95aY3XBOOVtsHNqoIPOM7Sjtvj+fErgIxCEYZtYBUqkw8OHB+ffAth7rezNFim9Vq8mRRtyr5hQH1YfgEnylJm/WBeqoyjiahrNDhwXicOdYN7jbMiQYznN0kSIsVVDEzOrlAbhOVUbtOAU5zQMQXv8gC3AxBsS7Td4xd1gN91LthZgRuqo3vLqSzHKwGQFaeUUdrZk1rSX4hxmiC2qFdIQ5DuRx+fQD6KT9BYEdubtQ7IobwjhH/K0S6QGVtCtEwQW0SMUdVaUHO6M8ZE4u1PhacTp7VVAlP5QBSrP+NBvslqIDSFObzDvwUUFe/veuP3GEqKeoAaz51FLQnDT+uPNNWvKmeBir2+EHQD/IbqpT0GiG7MulgCbc4PATMizTkit5XDNUo1Jp/3uj9b2oQlj6aREGGYIP6B/aawn2QHapaFNBV4qejw4u+NtuCKTpmXG0JTm8uDq4+Zi4hEeUg1M6TtSuMxJWnjFA1fBzM8Au6y3DR83KVxNADhkAvjpjmoUv0//WfuelxkvxEng4vWuSH//lkSWFSgQ5NkGL8/YGX2aPyzTuSSO26luMVyKoa0poK4MlAYMix+fK9+gRJVxnzl52rgf4h5qE9plhzPeNXUyZ5I63U72txY/ouM0SP7f+QzR2mCxO9vYJHKKPnkWIVGL8guDpfL0pKd2xnKl+dFEjLeNVq9ZRJoY6rbS//J7RfKCqed+t8AS1/sjQdKt2fMnBJeHHSz5HffTuSqiXYrmq1HgNFml46IRFjeNpPWODBXwBmGBhzqG4lhCa15p6SNtr2rnUCX/b2bV0gvNHXbxiTAiz7NBnbp6qwy5Fk5IDLcJghqsLMuRRke2PD8khhhndvMiy0nhHi+d6Y8sb45TRDVtRhUpuzEpxq/Tj+564VfGaVnZbf5slfpH0k0qUe98MsEJUaTTTkTx/IdvBESzWZR4phlk2nPUnnu/bsaBr12WWg3RxWpGpQNVAvHMLySy4LkymNbBY8rCBw1dHGOlgWuTNjLVKQrjylc7n0H7D90yo7/j1/CrrXPaGfEVBNCIghbElb97+Z3wfFnxDZ0dRCYPgh9Z+rLVYA9sgHv7GyLgbyM5JXmcV7PeAk5rN6Rgsq9dNz4YzXHz30K37VEbi5lbC4R9342uk0vG6vp/CZTWuYKnkphFy4qSMP+t4bYzMTEyTCMeDQsXKrpnI1z71k0oIYF3nGgZ5BWmFGtGQSiX6W1MWPktuAxie4OenQT5woDj4hIzDt5vWUx6yLqRATL1zE550fjTgeezHAk4gLttGiuwdsliItoqPC3ljr3z+CBpkgFvXXVGiK6raceEgqSMcbdR4NZF2--deCcoSZR6Rp7QwDA--hUcZEd7/bw9BWVBrdcUeiA=="}]},"merchandise":{"merchandiseLines":[{"stableId":"9720debd-5883-45ef-bf0d-fdc7d9558d88","merchandise":{"productVariantReference":{"id":"gid://shopify/ProductVariantMerchandise/51732384481626","variantId":"gid://shopify/ProductVariant/51732384481626","properties":[],"sellingPlanId":null,"sellingPlanDigest":null}},"quantity":{"items":{"value":1}},"expectedTotalPrice":{"value":{"amount":"4100.00","currencyCode":"INR"}},"lineComponentsSource":null,"lineComponents":[]}]},"memberships":{"memberships":[]},"payment":{"totalAmount":{"any":true},"paymentLines":[{"paymentMethod":{"directPaymentMethod":null,"giftCardPaymentMethod":null,"ownedGiftCardPaymentMethod":null,"redeemablePaymentMethod":null,"walletPaymentMethod":{"name":"SHOP_PAY","walletContent":{"shopPayWalletContent":{"sessionToken":"spt_S1JySVppZTRiRUJsRzBxeDRVeWtaS0dHTXFXanNXM0RuV01NZlNtY1hwZVo3YmkzQjRZYytGdG1rZmF4dGZzcmFZd05VWUx6Qmx6OG1RcGluRGJlSHc5a3dJRFJCbVZ6MVdxSmZURUt5cldOUWNwMDkrTGZYYzFuclI4akZBRHJPWkEyQm1PWGJrK24yYzArZnI1ZCtoOENtVGF2QlozUTMrZk82T0pXR2ljbTFYSDRiY3pjejRZU0lhdU9INVlHSnJ4d3h4ZzdOSGY2bnUzTWZLcmd2TWs0VWJlRDdmaE5CUzFJUFZzZ3d4dCt0NE9mMkFVSGJDa09GOU8zcHdEUDB6WTgxL3FyU25XRnU5TmFPcm1adEtNK2Q0V25kc25wUzRCb0hsNVNFRHREb2QzMnp3Z1FRR2tKVFVjVG1Nb1lBeXVjRHVrbkRhNHRkclQxTmZhOU9nRExpUm1lYlFWbzVwdzYxRGVFVUVaUGZZWlIxOWM1eEk0WlVIdUl2WDk1QTlxTU4yT09KVldXMjFzbDU5akFHTFF4T3RpUU90QTkrWkZ2UmRpOGU5bGM1a3dDZE5JT3pUaW10QUx6Tkl1ME9lRFNBYjFlWWdZNlNmRlcvNmhMQXo1YmtWcGxwZHhuQW1Dd1pMbHpLdW9LUXFyYkpRN2dWV200eEhqVmJmV2hRdW5VT2M5Sk1LeWlZYWlqS0FqZXRTR05sL1duYnlqR0s2MWRsZ3hGSDRHVWNOSnNveEpzY3ZyS1NhMTlxYUJ6UlBzV0FiVkdnOFVRRmc0UmlLT2p0UFpzSWNFMVJlSng2RTRpVFA0cmRPVC9HMUtzblBrUzdRZDM4NE54TkVqQmNKcjdic3NRV3g2WHg0anpTbTFFQ05EWEx4dU5TaUQxZytOdkhleUR5Qjc2ZEk0TUxZczJOTTZvTTZIbVgzWjNSUWtJazRMMUdCbDZlSCtURTFBMWxkSXJNNXozVVJudGFYS1BkR0lqL1UrM2FBY25mR2VlNEF5YUtlSDN5Uk1heDRkd0doYTZiQUxRRWtSMXY4dFNQbHNqYlhjNnhJRlk4YlpTUDI3emEzRGdoS1VLaGtJeUd1dW1CVkJpNHBKL25jMFZjSmduYnc0cGhzYUV1MFptblZET3BMdCtBLzhyQ3U2U0hCK085bmxqMjladkZzVEhLbU1xeVBJVWwyMjJ4bk9qSkJ3SEhuU1ZpL2o3MU1KQkFBSWMrSGJRN24rTEl6ZVlLaFh5TW9NeWJzWnhlNjJpbWthZ05QOHV0WkFUMHNhRzRKS3dtNDd4bEs4YkwzR0tqK2pkUm1xZEFZbm1KTXZqcFZkSTIzV0FtNTArRFh5b2x1OEdoRXJ1VEplVld5bWFDUVRZcjBid2hLOGlYdDU3VHBaYXFoL25qa1VIenh4QTM1bVJ4VHhtT3cyNDJ0UVdMMFFMMll2MHJmTFJtK2ZGUkc1ZStQNVArMDVMckgyTGZjSW9hTi9zaEFZek9aR3dTSTJOS08raE9FTEt3Y1JnZStJR0NpcE9CVnNVM2psZGJxdWhXcEpGalYzQzdGZDVTUTNwQk0yanFvRWQwaUNpSGhzUnBjWStRbHljVXd1MzdBUnBHSXdTdndvNjZCOGFINHgyZzRqRmJkbjMyRFllUEFtMllTR3JvN0NJQ200Skw0TWNCdjR6eVZnSTNidDJOakV4WnRUeFppUkx0dndmRFFDU1h2WDRBa0dIVExyZEQyQXY2NUxoWDRaQ1pkZGp5eEVFWkN2SFFzNXRzUFF4ZnpEbzZjTmhRemVxYU44c3dhOFNRNDRjTkorZk1FS1lERVVmT2ZwUGhZU0lPR0NyRDN1dTdRM0g3d3VFZHRhV000UHNFdEdEcCtBcEpaK2tSMTBNUmozUFNUTlRId1lNTHNBb2tNMC9rM2FKL0EzODB4VDBEelREb0taUHU3Y3I5elhBeTkzeHdTQ3pieHRobk9vMkJtUnRqaVMrN281b1N6TExwTjZOSlV1UnlJQTdKejBKZnNwZ2pTRlFPSmZ5ditlRHRQVGJoODdOcHdPajdCdUFocmVEdURxTmRxd2hNY0ZubmNKa2FSbG9DeUs4dHptQ2R1SFZHMGJXb2IvV2xxa1k0U0huSy9vTXl1UE5HRnYvNm9LcmhSaEZmQTZpVDZPZ3hzL2IxSnFHY3V2dFErMmdKL2d1bVBZNDhVQ05STFJDSlp4VFpqaG14Smc1Q2tZUHdTRzlPU0JHazFRU01BPT0tLUQzTFB2aVJPaVhPZFU0TE9YMlNwdWc9PQ==--8746169c50ee5bd780c3c614a7a475abd524f9f2","billingAddress":{"streetAddress":{"address1":"Bijipur Main Road Sundar Nagar","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533"}},"paymentMethod":"CREDIT_CARD","paymentMethodIdentifier":"12ba72fffce249eb2764c19cac64fb92","hsaRequested":false}}},"walletsPlatformPaymentMethod":null,"localPaymentMethod":null,"paymentOnDeliveryMethod":null,"paymentOnDeliveryMethod2":null,"manualPaymentMethod":null,"customPaymentMethod":null,"offsitePaymentMethod":null,"customOnsitePaymentMethod":null,"deferredPaymentMethod":null,"customerCreditCardPaymentMethod":null,"paypalBillingAgreementPaymentMethod":null,"remotePaymentInstrument":null},"amount":{"any":true}}],"billingAddress":{"streetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533"}},"creditCardBin":"40089500","allowStoreCredit":false},"buyerIdentity":{"customer":{"presentmentCurrency":"INR","countryCode":"IN"},"email":"wizardlyaura999@gmail.com","emailChanged":false,"phoneCountryCode":"IN","marketingConsent":[{"email":{"consentState":"DECLINED","value":"wizardlyaura999@gmail.com"}}],"shopPayOptInPhone":{"number":"+917853878533","countryCode":"IN"},"shopUserSecureData":"eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s","prefillSource":"SHOP_PAY","rememberMe":false},"tip":{"tipLines":[]},"taxes":{"proposedAllocations":null,"proposedTotalAmount":{"value":{"amount":"0","currencyCode":"INR"}},"proposedTotalIncludedAmount":null,"proposedMixedStateTotalAmount":null,"proposedExemptions":[]},"note":{"message":null,"customAttributes":[]},"localizationExtension":{"fields":[]},"shopPayArtifact":{"shopUser":{"uuid":"eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s"}},"nonNegotiableTerms":null,"scriptFingerprint":{"signature":null,"signatureUuid":null,"lineItemScriptChanges":[],"paymentScriptChanges":[],"shippingScriptChanges":[]},"optionalDuties":{"buyerRefusesDuties":false},"captcha":{"provider":"hcaptcha","challenge":"comparison_challenge_type","token":"P1_eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.3gAHp3Bhc3NrZXnFBHR8Nu7dGvRjHJZWFQ5ftoV87npezg1Of8eb3el70cTYlkQyU9D-A1L0NP4tG0CAjXGnhUE7yp7CHEiQ6SB4bvxrb97mbRcgYkwQ1UVBlesg8zxjgWEa7JHzZYovuDl1oSs4syrJp6A_pVyFw2iKafJcgBjQ9862V1mkIioYjJp3cU1exp4hrUU5cqNM7ZO4f9424I1WSIZMullCsXR4CI2WxK6TO05Xe_RHORal0w1Jz5YHzBMr7O0Q4ijsuOgLA5u3a0mvG8nhz88pR9LzF8s--LQkyoQs2whEvhZFEU7cCzmBHA_kjzr6uEyn-Jfes-t-WAd-1tHco-dCXrJeZhC_VhjXmNUHoSFwx7Uvn0x_o2dgzLKpUKCTD82VcjrwVUggHRZheSGkzF1HIdsE4-cqpeDgKQIIufoHySFC1HsBcexgEE7MmPcR-K1AswC5GrMmbEMFvZ1sPIlfBiIeO3M_jMRAcYgNLFdb0Wpg5QIktwpME1agAavpK_2JZz_32VmxlJCCKe61Trj9yzkHLhwvQhl8fHjh3tBDlTufveuRw00VyBO-gPKKzAWEk1cDBhcxlE3RrG3HlHrwjQSLB1TR5Nj-yPWVEb-MD8l62czV0gI_rh0Rs4M96Iv4OX4I5zf2h1T_69tuo5FDujvyM4_hIyNmagn6Kg65e7zF4MsfWbMHZDTs0yuDr5CRC3zZmsTRQM5SpIv3rHs-LAJU-tDAV8U7MvXYT1RVlkVcYPB0FVtWmaaKeBVV7X3RpsXZ_QZruPBam4txZR837_vy6w-YHn-2AhYDTjOdH0s7gNM7pcK5qrzabNtmIOrRuEEPLei8jdagG7sTEEEoc9hFNmsnPWkwxymHxExPL-CfDqUQHb1hCqSAriUin1OyjNq3BhdHFGEMjR03nui3MDssCwrRmH3Lr6dzMLGvX777Nvyb5-LG5skt8jPR48CvceG30WScw1rN92sQmgY1Ac-tqg48yuDTewBrXGo-oXttCsYLd6Gp_sqNFjgaFCPt9pxHwP196DNPIBk9zT3E2i__RiGE5NnJ517DbbLhBXXk7ZyBqi9EzggnrGc8A-f38a67VLd_3xL8ZiAvH-zVeOKSOAG5CoJgXQy90qEl6s0Tllo_PUJgcqVgHMZMweLxLmcPVSaxlpfc07p1cEFA4j1X6JLhv045diod5fNR6OFIZouPp9js8Vp6HlBTXz9HV5Uk8C0c_jZfixC-PyXGrkbnYeZh-mtNq6Z6cIcNUFY76sVhKo7QNPa3wFLn6eu-Dzz6IHI969ybTtL6Wq6xiA-wzceDbHVIyt2Fu0RTzAv0FkWrMR2Z1IkfGQb5gCfkGODE7ibKbRWrSsbpeoFdIr107Gyja4URRzf5KHOLboqgce9lP9FKyFHrAgzso6q7LsCWGlEjNcJBVzqfcs46aJw6WA6ZRigeb4ICzvAA3KluwQPxrqOWaEnM2D_th17kXnYXgeR9NSkRhqgHwlKyKSaMxdpMZv7ExwBaCD4u50-c6ZVFyjdrfq-nc2l0ZWtledkkMWYyNjIzYjEtZWIxOS00OTE2LThiNDMtMDg0YThhNzg1YjIzo2V4cM5q0n9jonBkAKVjZGF0YdQAAKZjZGF0YTLUAACia3KoM2E1YWFiNmU.MF_TS7zYc2wPr3_WzUBV1x0sOyZaDNRM5PSg0nrKHHU"},"cartMetafields":[]},"operationName":"Proposal","id":"218ca3f4634df050ead785d9692d50bc444d93ef926a6c0d820c1c01a02d474f"}'
#response = requests.post(
#    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
#    params=params,
#    cookies=cookies,
#    headers=headers,
#    data=data,
#)





import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shopify-tracking-consent': '3S.AMP',
}

params = {
    'operationName': 'PaymentSession',
}

json_data = {
    'variables': {
        'checkoutSessionIdentifier': 'daadf5d473ea94fde5b8c3a5893e2c72',
        'shopifyDomain': '4s0wfh-i6.myshopify.com',
        'addressId': 'c3a95b5f-5dab-4b52-bce2-12cf78d1577a',
        'checkoutClientSource': 'shop_pay',
        'creditCardId': '21c88226-4b75-4ad5-b7d4-94f3bae12d55',
        'batchCheckouts': [],
        'batchOnly': False,
        'stepUpChallengeSupported': True,
    },
    'operationName': 'PaymentSession',
    'query': 'mutation PaymentSession($addressId:ID,$creditCardId:ID!,$checkoutSessionIdentifier:String!,$shopifyDomain:String!,$installmentsAgreements:InstallmentsAgreementsInput,$unvaultedShippingAddress:AddressInput,$checkoutClientSource:CheckoutClientSourceEnum,$batchCheckouts:[BatchCheckoutsInput!],$batchOnly:Boolean,$publicCvvSessionId:String,$stepUpChallengeSupported:Boolean){paymentSessionGenerate(addressId:$addressId creditCardId:$creditCardId checkoutIdentifier:$checkoutSessionIdentifier shopifyDomain:$shopifyDomain installmentsAgreements:$installmentsAgreements unvaultedShippingAddress:$unvaultedShippingAddress checkoutClientSource:$checkoutClientSource batchCheckouts:$batchCheckouts batchOnly:$batchOnly publicCvvSessionId:$publicCvvSessionId stepUpChallengeSupported:$stepUpChallengeSupported){userErrors{message field __typename}sessionId batchCheckoutSessionIds{sessionId shopId __typename}__typename}}',
}

response = requests.post('https://shop.app/pay/users/graphql', params=params, cookies=cookies, headers=headers, json=json_data)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"checkoutSessionIdentifier":"daadf5d473ea94fde5b8c3a5893e2c72","shopifyDomain":"4s0wfh-i6.myshopify.com","addressId":"c3a95b5f-5dab-4b52-bce2-12cf78d1577a","checkoutClientSource":"shop_pay","creditCardId":"21c88226-4b75-4ad5-b7d4-94f3bae12d55","batchCheckouts":[],"batchOnly":false,"stepUpChallengeSupported":true},"operationName":"PaymentSession","query":"mutation PaymentSession($addressId:ID,$creditCardId:ID!,$checkoutSessionIdentifier:String!,$shopifyDomain:String!,$installmentsAgreements:InstallmentsAgreementsInput,$unvaultedShippingAddress:AddressInput,$checkoutClientSource:CheckoutClientSourceEnum,$batchCheckouts:[BatchCheckoutsInput!],$batchOnly:Boolean,$publicCvvSessionId:String,$stepUpChallengeSupported:Boolean){paymentSessionGenerate(addressId:$addressId creditCardId:$creditCardId checkoutIdentifier:$checkoutSessionIdentifier shopifyDomain:$shopifyDomain installmentsAgreements:$installmentsAgreements unvaultedShippingAddress:$unvaultedShippingAddress checkoutClientSource:$checkoutClientSource batchCheckouts:$batchCheckouts batchOnly:$batchOnly publicCvvSessionId:$publicCvvSessionId stepUpChallengeSupported:$stepUpChallengeSupported){userErrors{message field __typename}sessionId batchCheckoutSessionIds{sessionId shopId __typename}__typename}}"}'
#response = requests.post('https://shop.app/pay/users/graphql', params=params, cookies=cookies, headers=headers, data=data)


import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': 'id="hWNI32WWbY08l1Arphk2EFho", type="cn"',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-one-session-token': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shop-pay-token': 'eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaWQ6XC9cL3Nob3BpZnlcL1Nob3BcLzkyNTU0NDk0Mjk4IiwibmJmIjoxNzkyMTc5ODAxLCJzZXNzaW9uX3Rva2VuIjoiQUFFQld5Y0M5RnFEU19Lblg0MURKb1gzOF9RcjQwOVZZSnZfMU9fdTlVcURPMm5JSzh6RWpycDNqR0lpUDJzVi1lSy1WSVJPa3V4MmFGeWt2c2R1TndyS3BJQ00xQmxrNXdMVUgtMlVIeUU5UWFiQzJRcEd4dVdVa2x5dkNQRlYteXNOUVg3M29ITkEzNjlhYWVPdTh0by1lYnRMU3dKYzhqelZaSVF2MjROcmoxYU5OcmZrSno3d3VfM0ZMRVFPZF9USkxTMVlZVlB5TkdtRlA4OU94Q25Dc3VJYVJvcm9nMFN6dmV3Iiwic2Vzc2lvbl9jdXN0b21lcl9pZCI6MTA1MDczNjk4NDA5ODYsInNob3BfYWNjb3VudF91dWlkIjoiYTQ2ZWJiODUtNjc0Ny00NzhjLWE3ZmUtOTc5NDBjYzRiMWZmIiwic2hvcF9wYXlfZGF0YSI6IkNBSVNHWGRwZW1GeVpHeDVZWFZ5WVRrNU9VQm5iV0ZwYkM1amIyMGFFaGV3SEtTZEF1YVBZWVVfdkNNM3QwVU9oQ0lRcEc2N2hXZEhSNHluX3BlVURNU3hfempZX01uV0Jrb1NETm9uTXNVV2ZrX19wbHkwUTRDZGwxMEUiLCJjdXN0b21lcl9hdXRoZW50aWNhdGlvbl9hdXRoX3Byb3ZpZGVyIjoibG9naW5fd2l0aF9zaG9wIiwiZXhwIjoxNzkyMTgzNDAxLCJsYW5kaW5nX3BhZ2UiOiJcLyIsIm9yaWdfcmVmZXJyZXIiOiIiLCJtZXJjaGFudF9jb25zZW50IjoiM0FNUC5TIn0.eJ_036fE8fV7VlRQ_VrMQfgnE1KbP_duYqno-fhCrA0',
    'x-shopify-tracking-consent': '3S.AMP',
    'x-shopify-uniquetoken': 'c1e69033-8b91-45e6-8e70-d2adaeca3fe5',
    'x-shopify-visittoken': '9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2',
}

params = {
    'operationName': 'SubmitForCompletion',
}

json_data = {
    'variables': {
        'input': {
            'sessionInput': {
                'sessionToken': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
            },
            'queueToken': 'A0HvoL68GXwj8y5jBoheY-10kRyWFB6pU2fDJ7g8Tm-79byPjLF0A5Zwi-KOb6rtJml68-hhL_RwnvUNX3G8M8cAEmovDIeVN0yo42UW3AC59Y5RxFet-GF2-wUTEM0WYg==',
            'discounts': {
                'lines': [],
                'acceptUnexpectedDiscounts': True,
            },
            'delivery': {
                'deliveryLines': [
                    {
                        'destination': {
                            'streetAddress': {
                                'address1': 'Bijipur Main Road Sundar Nagar',
                                'address2': '',
                                'city': 'Brahmapur',
                                'countryCode': 'IN',
                                'postalCode': '760001',
                                'firstName': 'Subham',
                                'lastName': 'Kumar',
                                'zoneCode': 'OR',
                                'phone': '+917853878533',
                                'oneTimeUse': False,
                            },
                        },
                        'selectedDeliveryStrategy': {
                            'deliveryStrategyByHandle': {
                                'handle': 'daadf5d473ea94fde5b8c3a5893e2c72-1857f5edbd56cb87c7e3af188778f2e4',
                                'customDeliveryRate': False,
                            },
                            'options': {
                                'phone': '+917853878533',
                            },
                        },
                        'targetMerchandiseLines': {
                            'lines': [
                                {
                                    'stableId': '9720debd-5883-45ef-bf0d-fdc7d9558d88',
                                },
                            ],
                        },
                        'deliveryMethodTypes': [
                            'SHIPPING',
                        ],
                        'expectedTotalPrice': {
                            'value': {
                                'amount': '1700.00',
                                'currencyCode': 'INR',
                            },
                        },
                        'destinationChanged': False,
                    },
                ],
                'noDeliveryRequired': [],
                'useProgressiveRates': False,
                'prefetchShippingRatesStrategy': None,
                'interfaceFlow': 'SHOP_PAY',
                'supportsSplitShipping': True,
            },
            'deliveryExpectations': {
                'deliveryExpectationLines': [
                    {
                        'signedHandle': 'glX4nh3EzMFGOJkMsrZNqFZ31obSW5y+WzHSh/DFysUU3ul7ixJNdSL07QjVQrNzRs8Dny1JOFl0SQ7KZXs/L9fpBQ9fcizTsPxZy3IjDZR/KGSP4Kse/BZHmg911lhNuKIryLDrKd+GsNLj0rSyGU//YaJOcgxyFHPcUbRGDkIUAbkgM/KtPfMBVaT++Wf39ldI08yu9fGrp6i38RGTIgzm0F8Hre9pQzpjW/nvRZNA6hqCXleaYlc9BVBh+UQEzpXBkK15WeVYlPNCYn6v1C1PiawyNma/7SDPIc32xbAj4XA8Zkn0mOoUTlqYU/V/r5Uipc6OfLr16YL5k0ekeZcIsCq3jWh3G4LX3Acb3RLqdD1a+JCBaFgsuxsxI1NvmSveu7vfXe5d629IJ95UAcNKZubfvf9OQuzZf2WE7ehM0FnsOrsQQza2llCeUhwfWAzJfjxu3QBUV2lcCYyvVrHL7hwIQ0GAm8X6TTiaR4wqhNLiZNPJdJvJlboDa2iLc1x8HkO5UJSdWx9ddl6SrUzy930s125Iqm8U46DNewTRLyFQi3jZPm6hGXRoTZdlJi2EiZnL6t3J9DLcHasS5RFTt67aw9D3cZwlp9yTF6O1n9mzdIzPhmjgSCYL2/9L0WVNoi/hYAMgpam79gZWqFdBn0IMuV7F6Lve/Jk+tSPJ762z3wSDyJ8K6WFzVbpKo6UlkpNyk6mHkfEyynu4MuFLUr9lj4A1tyggs0VuJXHcDeDDOYsKM0zeCjUw4OK2NC8rqZ5bUZI7zV8y17NKeJKeEOq+aFnBykWHbSMbr3c7Cw56dPMMc6oX2z2p07BTNufvTmyMBpHUIPBD8v213F7Rhg6xx10VJqolRYDGDk8RzWdgXfJ+X0LVQKJcyQ4TXdKXSlFCvSazfASaFDUcE5llwac26sE9eplmD4HyI2WiionPbItY+oL3sdy1pkOY/UyLWrAUD+pR10kQfW9DBTmaegvKdVfA9DUW1FQErm1SNy6RxSdTR9wreLZmzL8YcihZHlEx4hkI3Gd3MKDDWmobI9XNgzr6DJH/x2P7vTmWiVEZakVPatAMfLfyvm69r+ToCNrsMeM+NmnQ6WuA9SFaR2w6hCmoQN3pBGopsZRYLYXokPbfqmlrmcHxWaCiU8FQMrRZbY65vcszwaDI/RTkOuZVIeLfErMXVvob5Wj5dRB7fWbvpUi2xRGu6C6C5/RilrVe0Tpm/GDDxsiaTDT11nfDNOUyIuWqBO8Hryq2Oz4YWfcB/0nDOFMLKsHCGZLDFhkWD2k+lFc9xQW65beDBL0oGOickR/HO/Ig9ODNFTGT//b8qnhSRPOVPk7cEKyllNT+1Gky1N/xAWEOH+TM3YY510EITpMvNvhxZIWF1MR5tWQ6d9O1Rld9PVpS7/7yN/tpnKexREcda/otSMd20r9zklrGYOotmTqQaQxCLoYxVBVfAlg2Tbc3cUQlS68EZwxgT9slFJz/pee1cNEJb4uyuDlZY5rql+1VHOJgX+lm05ximcgRiGxh/2m2--BGaxSqjwpAMQc7Gc--dQF0+7FrX/iBBIwc/wmIvA==',
                    },
                ],
            },
            'merchandise': {
                'merchandiseLines': [
                    {
                        'stableId': '9720debd-5883-45ef-bf0d-fdc7d9558d88',
                        'merchandise': {
                            'productVariantReference': {
                                'id': 'gid://shopify/ProductVariantMerchandise/51732384481626',
                                'variantId': 'gid://shopify/ProductVariant/51732384481626',
                                'properties': [],
                                'sellingPlanId': None,
                                'sellingPlanDigest': None,
                            },
                        },
                        'quantity': {
                            'items': {
                                'value': 1,
                            },
                        },
                        'expectedTotalPrice': {
                            'value': {
                                'amount': '4100.00',
                                'currencyCode': 'INR',
                            },
                        },
                        'lineComponentsSource': None,
                        'lineComponents': [],
                    },
                ],
            },
            'memberships': {
                'memberships': [],
            },
            'payment': {
                'totalAmount': {
                    'any': True,
                },
                'paymentLines': [
                    {
                        'paymentMethod': {
                            'directPaymentMethod': None,
                            'giftCardPaymentMethod': None,
                            'ownedGiftCardPaymentMethod': None,
                            'redeemablePaymentMethod': None,
                            'walletPaymentMethod': {
                                'name': 'SHOP_PAY',
                                'walletContent': {
                                    'shopPayWalletContent': {
                                        'sessionToken': 'spt_eThlTWZBUTEvRGM3VEd6VUFMeCt6YWlyTlZkcldxbkxqZVBlSDV6K2RrZFZla1k1UE0zVVZHUm1jL0F1VWNsT1dNNUg1OE45TUxLdmNQMDlQMzZFa0N4MmZDaVltZ2NMMElyR3I4RXZFRTV0bUtOVnRBaWFhbGtIWUxCcFpTVi9uSnp6SUdYN2d6NXAxcUpVejE0T2xlNHRTK2dJVG5tRGVMeXJxaG5PQk1XNzluSytGTk1jK2pMQzZ6SXFoNzYwMUV5dUNnajh5TmI2SFhKRm5VQmFzd2hSMHljR2E2NVM0OEwyeXI5c1JKZ0ZaVW9XclVMSFNZNmhLNjR0QTJ3NmVQRU9RNTBwdnpWTFdOaWtUWExCK2dRVmw2MnRiZ3JhU1Z0ejN0N3lpWmtBQy9tL2YzMlM1bVp0NDVBVmZwc25Pd2xyS2lLMFVDU2RxNXVhNUhRQTBPWkI2L2paTzYyMjZVVE4vcHVLbjlOZjFzN3hRU24xSzlwY1UveWdtdWgzV1hGamptSFFxbktUYVhVeGsvVTVUYmlQaXo5dFk1THlNeXRiZHIxbVZCTHVrSG5XVUkvSHB3b3laUGJGamxpeWpSdnhnaC9tQWVkaVZRcldKQTFjelN6a1ozRHFISEh5eE92cUhvN2pxU3grZ0lCbEdIa2YxY2ptTWdlYk5hQVd0aFRsY2ZDakhzVHU5UjN2NUVhbVBLZXNSV0FrYkdDRGRwQ1h4T2pyZHVCU1RjYVZ5N0lXdHo2RzBMUTZrMWpMb2U3WGJodUdtT1pxVXd2RjBJRzB3ZDFwWGFlQVZBQlhmV3NRMlc4NENWU0tRK0tTV0ZRVUQvT0pSZ2dVT1pORUtGcmh6MmJoSXAwZUdsVXU3Q1lHK1QzSzg1Mk9yR21YQnlLaTNKQU5jNEs4aUFBMlhpQzJvQXc0ZDkwMXdJYmJQZVk1dmFrdEVXVCtvdUtFUVZJQWZLcks5T1o1QUxBc2owVmdyODMvNVVPZGNxOFdNUkRpYjhUWk1LNXRrbHJqeGRyL2ZxSUN0clV5ak5MV0krSXpnUGVtK3dQMU1scEl1UTllQTA2b1RKVnhLYml2MWJZczRtR0VXYTlOOVI1QWtUaGE0SFRjWHhGUkJXR0t6RVB2NHpZWHdyUWhDRTNKbDl0MGE1NHpDQzBheThsckx4MGFEUWcxK1RtLzZONldOK2Q3QWJoVjIxTVF0a1NSZlNVcExENmZCeUkxbFR1bVRKc2N1UzZhdVJ3NFgvSkIwRXJva0trUi85UTIrTjZoZnZuL1JUZkd1M1ZvVGdveTBKWHVvUTMzUzBLWURGMlc1TDZpd1JESHJWMGhMbFhxTzVabmZTeEhKaW5NVVVsUmJRQTVHdHNJbG5ZUGUwbU1ibmVWVDhVbDloYktkb1VlbmwrQktwMVhQTmNkMkhOOVRTNmhOd1owZ1kwZEtyYldvT21vVnM2clA5WEpaQVVmSXZlUDEvT0xVTjF1UGlPMHRLMk5RQW1yOGNOTDhIMzJPVmpBbzMxbE1SZFFtalYrM24rMEpXUGgwbU5ZeEphSnZCMGpRcmttM0YyaWRMYkowcFpsVVowdHY4WTRvb0hHdmgrM04zbEFYNDdpcjR5Mjd1dHdpd2JMNnRLbmhhaWQ0bncrbFlyVXZnbzk5bjJKL3lENmY5V2hKNmZ4SGFkNGsyZ1crMC9qTzNIblliWDVFNFNWRFJhVTl4R2MvVnJzRjZkbXRkajJMa1NnSGM2UU4vOWdNK3NtazVyc2FXcTFLaEZiVjhyVkkzR1lLdUNJeW4rQTNrT3BqdVYvaHQwY1ZoZEVUY2NnMEE3N2xrTTcrVGgyc0ZUOTVUSFJaVEZUdnNNY1M4Zm9tdDhDcWJCQWcxVUs0ai9OSG9HbjNiMU51MjlBbGtDSmdyUUd5dlNEWlUyMWFkK2lreUFTem9obnB0Y1FhUHlyMElaUXM0YklIOWN6V3Fvc3h3N1FNajVHdmRQNU1pTHN1R0ozajBaMzlUbCs3TFB2R29uS1VUeGFyWVBTNGZvZlZUMFQvRFdVSDYvalgvNmo5YnNSV3A3UFpnTzdoUWZzWFpkUUY4WHRoZHY0LzNESlJnQWtTajlhdXNNblM4WVd6Q3ZBUk03VU00azF6Y3RXa3ZUTUZMTTdrMG1idTc1SVEyVlFjckdpUGsvQWpjTEdMZm9WUFg2dmplQ0Z2OEt3Tm5BRnhTUGhqNnFaSzk1MGRKcEYvbWFiR2U5Wkx3PT0tLUtuME03TXNaWWdzdjUvMUd2VnlEbVE9PQ==--cd891a6b53d3315872932a9a1137077262714373',
                                        'billingAddress': {
                                            'streetAddress': {
                                                'address1': 'Bijipur Main Road Sundar Nagar',
                                                'address2': '',
                                                'city': 'Brahmapur',
                                                'countryCode': 'IN',
                                                'postalCode': '760001',
                                                'firstName': 'Subham',
                                                'lastName': 'Kumar',
                                                'zoneCode': 'OR',
                                                'phone': '+917853878533',
                                            },
                                        },
                                        'paymentMethod': 'CREDIT_CARD',
                                        'paymentMethodIdentifier': '12ba72fffce249eb2764c19cac64fb92',
                                    },
                                },
                            },
                            'walletsPlatformPaymentMethod': None,
                            'localPaymentMethod': None,
                            'paymentOnDeliveryMethod': None,
                            'paymentOnDeliveryMethod2': None,
                            'manualPaymentMethod': None,
                            'customPaymentMethod': None,
                            'offsitePaymentMethod': None,
                            'customOnsitePaymentMethod': None,
                            'deferredPaymentMethod': None,
                            'customerCreditCardPaymentMethod': None,
                            'paypalBillingAgreementPaymentMethod': None,
                            'remotePaymentInstrument': None,
                        },
                        'amount': {
                            'value': {
                                'amount': '5800',
                                'currencyCode': 'INR',
                            },
                        },
                    },
                ],
                'billingAddress': {
                    'streetAddress': {
                        'address1': 'Bijipur Main Road Sundar Nagar',
                        'address2': '',
                        'city': 'Brahmapur',
                        'countryCode': 'IN',
                        'postalCode': '760001',
                        'firstName': 'Subham',
                        'lastName': 'Kumar',
                        'zoneCode': 'OR',
                        'phone': '+917853878533',
                    },
                },
                'creditCardBin': '40089500',
                'allowStoreCredit': False,
            },
            'buyerIdentity': {
                'customer': {
                    'presentmentCurrency': 'INR',
                    'countryCode': 'IN',
                },
                'email': 'wizardlyaura999@gmail.com',
                'emailChanged': False,
                'phoneCountryCode': 'IN',
                'marketingConsent': [
                    {
                        'email': {
                            'consentState': 'DECLINED',
                            'value': 'wizardlyaura999@gmail.com',
                        },
                    },
                ],
                'shopPayOptInPhone': {
                    'number': '+917853878533',
                    'countryCode': 'IN',
                },
                'shopUserSecureData': 'eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s',
                'prefillSource': 'SHOP_PAY',
                'rememberMe': False,
            },
            'tip': {
                'tipLines': [],
            },
            'taxes': {
                'proposedAllocations': None,
                'proposedTotalAmount': {
                    'value': {
                        'amount': '0',
                        'currencyCode': 'INR',
                    },
                },
                'proposedTotalIncludedAmount': None,
                'proposedMixedStateTotalAmount': None,
                'proposedExemptions': [],
            },
            'note': {
                'message': None,
                'customAttributes': [],
            },
            'localizationExtension': {
                'fields': [],
            },
            'shopPayArtifact': {
                'shopUser': {
                    'uuid': 'eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s',
                },
            },
            'nonNegotiableTerms': None,
            'scriptFingerprint': {
                'signature': None,
                'signatureUuid': None,
                'lineItemScriptChanges': [],
                'paymentScriptChanges': [],
                'shippingScriptChanges': [],
            },
            'optionalDuties': {
                'buyerRefusesDuties': False,
            },
            'captcha': {
                'provider': 'hcaptcha',
                'challenge': 'comparison_challenge_type',
                'token': 'P1_eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.3gAHp3Bhc3NrZXnFBHR8Nu7dGvRjHJZWFQ5ftoV87npezg1Of8eb3el70cTYlkQyU9D-A1L0NP4tG0CAjXGnhUE7yp7CHEiQ6SB4bvxrb97mbRcgYkwQ1UVBlesg8zxjgWEa7JHzZYovuDl1oSs4syrJp6A_pVyFw2iKafJcgBjQ9862V1mkIioYjJp3cU1exp4hrUU5cqNM7ZO4f9424I1WSIZMullCsXR4CI2WxK6TO05Xe_RHORal0w1Jz5YHzBMr7O0Q4ijsuOgLA5u3a0mvG8nhz88pR9LzF8s--LQkyoQs2whEvhZFEU7cCzmBHA_kjzr6uEyn-Jfes-t-WAd-1tHco-dCXrJeZhC_VhjXmNUHoSFwx7Uvn0x_o2dgzLKpUKCTD82VcjrwVUggHRZheSGkzF1HIdsE4-cqpeDgKQIIufoHySFC1HsBcexgEE7MmPcR-K1AswC5GrMmbEMFvZ1sPIlfBiIeO3M_jMRAcYgNLFdb0Wpg5QIktwpME1agAavpK_2JZz_32VmxlJCCKe61Trj9yzkHLhwvQhl8fHjh3tBDlTufveuRw00VyBO-gPKKzAWEk1cDBhcxlE3RrG3HlHrwjQSLB1TR5Nj-yPWVEb-MD8l62czV0gI_rh0Rs4M96Iv4OX4I5zf2h1T_69tuo5FDujvyM4_hIyNmagn6Kg65e7zF4MsfWbMHZDTs0yuDr5CRC3zZmsTRQM5SpIv3rHs-LAJU-tDAV8U7MvXYT1RVlkVcYPB0FVtWmaaKeBVV7X3RpsXZ_QZruPBam4txZR837_vy6w-YHn-2AhYDTjOdH0s7gNM7pcK5qrzabNtmIOrRuEEPLei8jdagG7sTEEEoc9hFNmsnPWkwxymHxExPL-CfDqUQHb1hCqSAriUin1OyjNq3BhdHFGEMjR03nui3MDssCwrRmH3Lr6dzMLGvX777Nvyb5-LG5skt8jPR48CvceG30WScw1rN92sQmgY1Ac-tqg48yuDTewBrXGo-oXttCsYLd6Gp_sqNFjgaFCPt9pxHwP196DNPIBk9zT3E2i__RiGE5NnJ517DbbLhBXXk7ZyBqi9EzggnrGc8A-f38a67VLd_3xL8ZiAvH-zVeOKSOAG5CoJgXQy90qEl6s0Tllo_PUJgcqVgHMZMweLxLmcPVSaxlpfc07p1cEFA4j1X6JLhv045diod5fNR6OFIZouPp9js8Vp6HlBTXz9HV5Uk8C0c_jZfixC-PyXGrkbnYeZh-mtNq6Z6cIcNUFY76sVhKo7QNPa3wFLn6eu-Dzz6IHI969ybTtL6Wq6xiA-wzceDbHVIyt2Fu0RTzAv0FkWrMR2Z1IkfGQb5gCfkGODE7ibKbRWrSsbpeoFdIr107Gyja4URRzf5KHOLboqgce9lP9FKyFHrAgzso6q7LsCWGlEjNcJBVzqfcs46aJw6WA6ZRigeb4ICzvAA3KluwQPxrqOWaEnM2D_th17kXnYXgeR9NSkRhqgHwlKyKSaMxdpMZv7ExwBaCD4u50-c6ZVFyjdrfq-nc2l0ZWtledkkMWYyNjIzYjEtZWIxOS00OTE2LThiNDMtMDg0YThhNzg1YjIzo2V4cM5q0n9jonBkAKVjZGF0YdQAAKZjZGF0YTLUAACia3KoM2E1YWFiNmU.MF_TS7zYc2wPr3_WzUBV1x0sOyZaDNRM5PSg0nrKHHU',
            },
            'cartMetafields': [],
        },
        'attemptToken': 'hWNI32WWbY08l1Arphk2EFho-50lb0z3hbrx',
        'metafields': [],
        'analytics': {
            'requestUrl': 'https://shop.app/checkout/92554494298/cn/hWNI32WWbY08l1Arphk2EFho/en-in/shoppay?_r=AQABmZF3Ltqhl3wpt0SwuxklVyW0MgVzr1HrqXesuvADkXoltzmB',
            'pageId': '463db52b-67E3-4F5A-9822-978E79640BDB',
        },
    },
    'operationName': 'SubmitForCompletion',
    'id': 'f02c160f316aa090cc8d2746ab840109be3265dcac12fef341e51d697ac5b2b8',
}

response = requests.post(
    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"input":{"sessionInput":{"sessionToken":"AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew"},"queueToken":"A0HvoL68GXwj8y5jBoheY-10kRyWFB6pU2fDJ7g8Tm-79byPjLF0A5Zwi-KOb6rtJml68-hhL_RwnvUNX3G8M8cAEmovDIeVN0yo42UW3AC59Y5RxFet-GF2-wUTEM0WYg==","discounts":{"lines":[],"acceptUnexpectedDiscounts":true},"delivery":{"deliveryLines":[{"destination":{"streetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533","oneTimeUse":false}},"selectedDeliveryStrategy":{"deliveryStrategyByHandle":{"handle":"daadf5d473ea94fde5b8c3a5893e2c72-1857f5edbd56cb87c7e3af188778f2e4","customDeliveryRate":false},"options":{"phone":"+917853878533"}},"targetMerchandiseLines":{"lines":[{"stableId":"9720debd-5883-45ef-bf0d-fdc7d9558d88"}]},"deliveryMethodTypes":["SHIPPING"],"expectedTotalPrice":{"value":{"amount":"1700.00","currencyCode":"INR"}},"destinationChanged":false}],"noDeliveryRequired":[],"useProgressiveRates":false,"prefetchShippingRatesStrategy":null,"interfaceFlow":"SHOP_PAY","supportsSplitShipping":true},"deliveryExpectations":{"deliveryExpectationLines":[{"signedHandle":"glX4nh3EzMFGOJkMsrZNqFZ31obSW5y+WzHSh/DFysUU3ul7ixJNdSL07QjVQrNzRs8Dny1JOFl0SQ7KZXs/L9fpBQ9fcizTsPxZy3IjDZR/KGSP4Kse/BZHmg911lhNuKIryLDrKd+GsNLj0rSyGU//YaJOcgxyFHPcUbRGDkIUAbkgM/KtPfMBVaT++Wf39ldI08yu9fGrp6i38RGTIgzm0F8Hre9pQzpjW/nvRZNA6hqCXleaYlc9BVBh+UQEzpXBkK15WeVYlPNCYn6v1C1PiawyNma/7SDPIc32xbAj4XA8Zkn0mOoUTlqYU/V/r5Uipc6OfLr16YL5k0ekeZcIsCq3jWh3G4LX3Acb3RLqdD1a+JCBaFgsuxsxI1NvmSveu7vfXe5d629IJ95UAcNKZubfvf9OQuzZf2WE7ehM0FnsOrsQQza2llCeUhwfWAzJfjxu3QBUV2lcCYyvVrHL7hwIQ0GAm8X6TTiaR4wqhNLiZNPJdJvJlboDa2iLc1x8HkO5UJSdWx9ddl6SrUzy930s125Iqm8U46DNewTRLyFQi3jZPm6hGXRoTZdlJi2EiZnL6t3J9DLcHasS5RFTt67aw9D3cZwlp9yTF6O1n9mzdIzPhmjgSCYL2/9L0WVNoi/hYAMgpam79gZWqFdBn0IMuV7F6Lve/Jk+tSPJ762z3wSDyJ8K6WFzVbpKo6UlkpNyk6mHkfEyynu4MuFLUr9lj4A1tyggs0VuJXHcDeDDOYsKM0zeCjUw4OK2NC8rqZ5bUZI7zV8y17NKeJKeEOq+aFnBykWHbSMbr3c7Cw56dPMMc6oX2z2p07BTNufvTmyMBpHUIPBD8v213F7Rhg6xx10VJqolRYDGDk8RzWdgXfJ+X0LVQKJcyQ4TXdKXSlFCvSazfASaFDUcE5llwac26sE9eplmD4HyI2WiionPbItY+oL3sdy1pkOY/UyLWrAUD+pR10kQfW9DBTmaegvKdVfA9DUW1FQErm1SNy6RxSdTR9wreLZmzL8YcihZHlEx4hkI3Gd3MKDDWmobI9XNgzr6DJH/x2P7vTmWiVEZakVPatAMfLfyvm69r+ToCNrsMeM+NmnQ6WuA9SFaR2w6hCmoQN3pBGopsZRYLYXokPbfqmlrmcHxWaCiU8FQMrRZbY65vcszwaDI/RTkOuZVIeLfErMXVvob5Wj5dRB7fWbvpUi2xRGu6C6C5/RilrVe0Tpm/GDDxsiaTDT11nfDNOUyIuWqBO8Hryq2Oz4YWfcB/0nDOFMLKsHCGZLDFhkWD2k+lFc9xQW65beDBL0oGOickR/HO/Ig9ODNFTGT//b8qnhSRPOVPk7cEKyllNT+1Gky1N/xAWEOH+TM3YY510EITpMvNvhxZIWF1MR5tWQ6d9O1Rld9PVpS7/7yN/tpnKexREcda/otSMd20r9zklrGYOotmTqQaQxCLoYxVBVfAlg2Tbc3cUQlS68EZwxgT9slFJz/pee1cNEJb4uyuDlZY5rql+1VHOJgX+lm05ximcgRiGxh/2m2--BGaxSqjwpAMQc7Gc--dQF0+7FrX/iBBIwc/wmIvA=="}]},"merchandise":{"merchandiseLines":[{"stableId":"9720debd-5883-45ef-bf0d-fdc7d9558d88","merchandise":{"productVariantReference":{"id":"gid://shopify/ProductVariantMerchandise/51732384481626","variantId":"gid://shopify/ProductVariant/51732384481626","properties":[],"sellingPlanId":null,"sellingPlanDigest":null}},"quantity":{"items":{"value":1}},"expectedTotalPrice":{"value":{"amount":"4100.00","currencyCode":"INR"}},"lineComponentsSource":null,"lineComponents":[]}]},"memberships":{"memberships":[]},"payment":{"totalAmount":{"any":true},"paymentLines":[{"paymentMethod":{"directPaymentMethod":null,"giftCardPaymentMethod":null,"ownedGiftCardPaymentMethod":null,"redeemablePaymentMethod":null,"walletPaymentMethod":{"name":"SHOP_PAY","walletContent":{"shopPayWalletContent":{"sessionToken":"spt_eThlTWZBUTEvRGM3VEd6VUFMeCt6YWlyTlZkcldxbkxqZVBlSDV6K2RrZFZla1k1UE0zVVZHUm1jL0F1VWNsT1dNNUg1OE45TUxLdmNQMDlQMzZFa0N4MmZDaVltZ2NMMElyR3I4RXZFRTV0bUtOVnRBaWFhbGtIWUxCcFpTVi9uSnp6SUdYN2d6NXAxcUpVejE0T2xlNHRTK2dJVG5tRGVMeXJxaG5PQk1XNzluSytGTk1jK2pMQzZ6SXFoNzYwMUV5dUNnajh5TmI2SFhKRm5VQmFzd2hSMHljR2E2NVM0OEwyeXI5c1JKZ0ZaVW9XclVMSFNZNmhLNjR0QTJ3NmVQRU9RNTBwdnpWTFdOaWtUWExCK2dRVmw2MnRiZ3JhU1Z0ejN0N3lpWmtBQy9tL2YzMlM1bVp0NDVBVmZwc25Pd2xyS2lLMFVDU2RxNXVhNUhRQTBPWkI2L2paTzYyMjZVVE4vcHVLbjlOZjFzN3hRU24xSzlwY1UveWdtdWgzV1hGamptSFFxbktUYVhVeGsvVTVUYmlQaXo5dFk1THlNeXRiZHIxbVZCTHVrSG5XVUkvSHB3b3laUGJGamxpeWpSdnhnaC9tQWVkaVZRcldKQTFjelN6a1ozRHFISEh5eE92cUhvN2pxU3grZ0lCbEdIa2YxY2ptTWdlYk5hQVd0aFRsY2ZDakhzVHU5UjN2NUVhbVBLZXNSV0FrYkdDRGRwQ1h4T2pyZHVCU1RjYVZ5N0lXdHo2RzBMUTZrMWpMb2U3WGJodUdtT1pxVXd2RjBJRzB3ZDFwWGFlQVZBQlhmV3NRMlc4NENWU0tRK0tTV0ZRVUQvT0pSZ2dVT1pORUtGcmh6MmJoSXAwZUdsVXU3Q1lHK1QzSzg1Mk9yR21YQnlLaTNKQU5jNEs4aUFBMlhpQzJvQXc0ZDkwMXdJYmJQZVk1dmFrdEVXVCtvdUtFUVZJQWZLcks5T1o1QUxBc2owVmdyODMvNVVPZGNxOFdNUkRpYjhUWk1LNXRrbHJqeGRyL2ZxSUN0clV5ak5MV0krSXpnUGVtK3dQMU1scEl1UTllQTA2b1RKVnhLYml2MWJZczRtR0VXYTlOOVI1QWtUaGE0SFRjWHhGUkJXR0t6RVB2NHpZWHdyUWhDRTNKbDl0MGE1NHpDQzBheThsckx4MGFEUWcxK1RtLzZONldOK2Q3QWJoVjIxTVF0a1NSZlNVcExENmZCeUkxbFR1bVRKc2N1UzZhdVJ3NFgvSkIwRXJva0trUi85UTIrTjZoZnZuL1JUZkd1M1ZvVGdveTBKWHVvUTMzUzBLWURGMlc1TDZpd1JESHJWMGhMbFhxTzVabmZTeEhKaW5NVVVsUmJRQTVHdHNJbG5ZUGUwbU1ibmVWVDhVbDloYktkb1VlbmwrQktwMVhQTmNkMkhOOVRTNmhOd1owZ1kwZEtyYldvT21vVnM2clA5WEpaQVVmSXZlUDEvT0xVTjF1UGlPMHRLMk5RQW1yOGNOTDhIMzJPVmpBbzMxbE1SZFFtalYrM24rMEpXUGgwbU5ZeEphSnZCMGpRcmttM0YyaWRMYkowcFpsVVowdHY4WTRvb0hHdmgrM04zbEFYNDdpcjR5Mjd1dHdpd2JMNnRLbmhhaWQ0bncrbFlyVXZnbzk5bjJKL3lENmY5V2hKNmZ4SGFkNGsyZ1crMC9qTzNIblliWDVFNFNWRFJhVTl4R2MvVnJzRjZkbXRkajJMa1NnSGM2UU4vOWdNK3NtazVyc2FXcTFLaEZiVjhyVkkzR1lLdUNJeW4rQTNrT3BqdVYvaHQwY1ZoZEVUY2NnMEE3N2xrTTcrVGgyc0ZUOTVUSFJaVEZUdnNNY1M4Zm9tdDhDcWJCQWcxVUs0ai9OSG9HbjNiMU51MjlBbGtDSmdyUUd5dlNEWlUyMWFkK2lreUFTem9obnB0Y1FhUHlyMElaUXM0YklIOWN6V3Fvc3h3N1FNajVHdmRQNU1pTHN1R0ozajBaMzlUbCs3TFB2R29uS1VUeGFyWVBTNGZvZlZUMFQvRFdVSDYvalgvNmo5YnNSV3A3UFpnTzdoUWZzWFpkUUY4WHRoZHY0LzNESlJnQWtTajlhdXNNblM4WVd6Q3ZBUk03VU00azF6Y3RXa3ZUTUZMTTdrMG1idTc1SVEyVlFjckdpUGsvQWpjTEdMZm9WUFg2dmplQ0Z2OEt3Tm5BRnhTUGhqNnFaSzk1MGRKcEYvbWFiR2U5Wkx3PT0tLUtuME03TXNaWWdzdjUvMUd2VnlEbVE9PQ==--cd891a6b53d3315872932a9a1137077262714373","billingAddress":{"streetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533"}},"paymentMethod":"CREDIT_CARD","paymentMethodIdentifier":"12ba72fffce249eb2764c19cac64fb92"}}},"walletsPlatformPaymentMethod":null,"localPaymentMethod":null,"paymentOnDeliveryMethod":null,"paymentOnDeliveryMethod2":null,"manualPaymentMethod":null,"customPaymentMethod":null,"offsitePaymentMethod":null,"customOnsitePaymentMethod":null,"deferredPaymentMethod":null,"customerCreditCardPaymentMethod":null,"paypalBillingAgreementPaymentMethod":null,"remotePaymentInstrument":null},"amount":{"value":{"amount":"5800","currencyCode":"INR"}}}],"billingAddress":{"streetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533"}},"creditCardBin":"40089500","allowStoreCredit":false},"buyerIdentity":{"customer":{"presentmentCurrency":"INR","countryCode":"IN"},"email":"wizardlyaura999@gmail.com","emailChanged":false,"phoneCountryCode":"IN","marketingConsent":[{"email":{"consentState":"DECLINED","value":"wizardlyaura999@gmail.com"}}],"shopPayOptInPhone":{"number":"+917853878533","countryCode":"IN"},"shopUserSecureData":"eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s","prefillSource":"SHOP_PAY","rememberMe":false},"tip":{"tipLines":[]},"taxes":{"proposedAllocations":null,"proposedTotalAmount":{"value":{"amount":"0","currencyCode":"INR"}},"proposedTotalIncludedAmount":null,"proposedMixedStateTotalAmount":null,"proposedExemptions":[]},"note":{"message":null,"customAttributes":[]},"localizationExtension":{"fields":[]},"shopPayArtifact":{"shopUser":{"uuid":"eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s"}},"nonNegotiableTerms":null,"scriptFingerprint":{"signature":null,"signatureUuid":null,"lineItemScriptChanges":[],"paymentScriptChanges":[],"shippingScriptChanges":[]},"optionalDuties":{"buyerRefusesDuties":false},"captcha":{"provider":"hcaptcha","challenge":"comparison_challenge_type","token":"P1_eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.3gAHp3Bhc3NrZXnFBHR8Nu7dGvRjHJZWFQ5ftoV87npezg1Of8eb3el70cTYlkQyU9D-A1L0NP4tG0CAjXGnhUE7yp7CHEiQ6SB4bvxrb97mbRcgYkwQ1UVBlesg8zxjgWEa7JHzZYovuDl1oSs4syrJp6A_pVyFw2iKafJcgBjQ9862V1mkIioYjJp3cU1exp4hrUU5cqNM7ZO4f9424I1WSIZMullCsXR4CI2WxK6TO05Xe_RHORal0w1Jz5YHzBMr7O0Q4ijsuOgLA5u3a0mvG8nhz88pR9LzF8s--LQkyoQs2whEvhZFEU7cCzmBHA_kjzr6uEyn-Jfes-t-WAd-1tHco-dCXrJeZhC_VhjXmNUHoSFwx7Uvn0x_o2dgzLKpUKCTD82VcjrwVUggHRZheSGkzF1HIdsE4-cqpeDgKQIIufoHySFC1HsBcexgEE7MmPcR-K1AswC5GrMmbEMFvZ1sPIlfBiIeO3M_jMRAcYgNLFdb0Wpg5QIktwpME1agAavpK_2JZz_32VmxlJCCKe61Trj9yzkHLhwvQhl8fHjh3tBDlTufveuRw00VyBO-gPKKzAWEk1cDBhcxlE3RrG3HlHrwjQSLB1TR5Nj-yPWVEb-MD8l62czV0gI_rh0Rs4M96Iv4OX4I5zf2h1T_69tuo5FDujvyM4_hIyNmagn6Kg65e7zF4MsfWbMHZDTs0yuDr5CRC3zZmsTRQM5SpIv3rHs-LAJU-tDAV8U7MvXYT1RVlkVcYPB0FVtWmaaKeBVV7X3RpsXZ_QZruPBam4txZR837_vy6w-YHn-2AhYDTjOdH0s7gNM7pcK5qrzabNtmIOrRuEEPLei8jdagG7sTEEEoc9hFNmsnPWkwxymHxExPL-CfDqUQHb1hCqSAriUin1OyjNq3BhdHFGEMjR03nui3MDssCwrRmH3Lr6dzMLGvX777Nvyb5-LG5skt8jPR48CvceG30WScw1rN92sQmgY1Ac-tqg48yuDTewBrXGo-oXttCsYLd6Gp_sqNFjgaFCPt9pxHwP196DNPIBk9zT3E2i__RiGE5NnJ517DbbLhBXXk7ZyBqi9EzggnrGc8A-f38a67VLd_3xL8ZiAvH-zVeOKSOAG5CoJgXQy90qEl6s0Tllo_PUJgcqVgHMZMweLxLmcPVSaxlpfc07p1cEFA4j1X6JLhv045diod5fNR6OFIZouPp9js8Vp6HlBTXz9HV5Uk8C0c_jZfixC-PyXGrkbnYeZh-mtNq6Z6cIcNUFY76sVhKo7QNPa3wFLn6eu-Dzz6IHI969ybTtL6Wq6xiA-wzceDbHVIyt2Fu0RTzAv0FkWrMR2Z1IkfGQb5gCfkGODE7ibKbRWrSsbpeoFdIr107Gyja4URRzf5KHOLboqgce9lP9FKyFHrAgzso6q7LsCWGlEjNcJBVzqfcs46aJw6WA6ZRigeb4ICzvAA3KluwQPxrqOWaEnM2D_th17kXnYXgeR9NSkRhqgHwlKyKSaMxdpMZv7ExwBaCD4u50-c6ZVFyjdrfq-nc2l0ZWtledkkMWYyNjIzYjEtZWIxOS00OTE2LThiNDMtMDg0YThhNzg1YjIzo2V4cM5q0n9jonBkAKVjZGF0YdQAAKZjZGF0YTLUAACia3KoM2E1YWFiNmU.MF_TS7zYc2wPr3_WzUBV1x0sOyZaDNRM5PSg0nrKHHU"},"cartMetafields":[]},"attemptToken":"hWNI32WWbY08l1Arphk2EFho-50lb0z3hbrx","metafields":[],"analytics":{"requestUrl":"https://shop.app/checkout/92554494298/cn/hWNI32WWbY08l1Arphk2EFho/en-in/shoppay?_r=AQABmZF3Ltqhl3wpt0SwuxklVyW0MgVzr1HrqXesuvADkXoltzmB","pageId":"463db52b-67E3-4F5A-9822-978E79640BDB"}},"operationName":"SubmitForCompletion","id":"f02c160f316aa090cc8d2746ab840109be3265dcac12fef341e51d697ac5b2b8"}'
#response = requests.post(
#    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
#    params=params,
#    cookies=cookies,
#    headers=headers,
#    data=data,
#)




import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': 'id="hWNI32WWbY08l1Arphk2EFho", type="cn"',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-one-session-token': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shop-pay-token': 'eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaWQ6XC9cL3Nob3BpZnlcL1Nob3BcLzkyNTU0NDk0Mjk4IiwibmJmIjoxNzkyMTc5ODAxLCJzZXNzaW9uX3Rva2VuIjoiQUFFQld5Y0M5RnFEU19Lblg0MURKb1gzOF9RcjQwOVZZSnZfMU9fdTlVcURPMm5JSzh6RWpycDNqR0lpUDJzVi1lSy1WSVJPa3V4MmFGeWt2c2R1TndyS3BJQ00xQmxrNXdMVUgtMlVIeUU5UWFiQzJRcEd4dVdVa2x5dkNQRlYteXNOUVg3M29ITkEzNjlhYWVPdTh0by1lYnRMU3dKYzhqelZaSVF2MjROcmoxYU5OcmZrSno3d3VfM0ZMRVFPZF9USkxTMVlZVlB5TkdtRlA4OU94Q25Dc3VJYVJvcm9nMFN6dmV3Iiwic2Vzc2lvbl9jdXN0b21lcl9pZCI6MTA1MDczNjk4NDA5ODYsInNob3BfYWNjb3VudF91dWlkIjoiYTQ2ZWJiODUtNjc0Ny00NzhjLWE3ZmUtOTc5NDBjYzRiMWZmIiwic2hvcF9wYXlfZGF0YSI6IkNBSVNHWGRwZW1GeVpHeDVZWFZ5WVRrNU9VQm5iV0ZwYkM1amIyMGFFaGV3SEtTZEF1YVBZWVVfdkNNM3QwVU9oQ0lRcEc2N2hXZEhSNHluX3BlVURNU3hfempZX01uV0Jrb1NETm9uTXNVV2ZrX19wbHkwUTRDZGwxMEUiLCJjdXN0b21lcl9hdXRoZW50aWNhdGlvbl9hdXRoX3Byb3ZpZGVyIjoibG9naW5fd2l0aF9zaG9wIiwiZXhwIjoxNzkyMTgzNDAxLCJsYW5kaW5nX3BhZ2UiOiJcLyIsIm9yaWdfcmVmZXJyZXIiOiIiLCJtZXJjaGFudF9jb25zZW50IjoiM0FNUC5TIn0.eJ_036fE8fV7VlRQ_VrMQfgnE1KbP_duYqno-fhCrA0',
    'x-shopify-tracking-consent': '3S.AMP',
    'x-shopify-uniquetoken': 'c1e69033-8b91-45e6-8e70-d2adaeca3fe5',
    'x-shopify-visittoken': '9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2',
}

params = {
    'operationName': 'PollForReceipt',
}

json_data = {
    'variables': {
        'receiptId': 'gid://shopify/ProcessedReceipt/9a686188c040654dfc50eb7eda0c5988',
        'sessionToken': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    },
    'operationName': 'PollForReceipt',
    'id': '98f65f1b789aa2a58a4da4284e773c8d577787273e650e6823704d3715082c59',
}

response = requests.post(
    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"receiptId":"gid://shopify/ProcessedReceipt/9a686188c040654dfc50eb7eda0c5988","sessionToken":"AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew"},"operationName":"PollForReceipt","id":"98f65f1b789aa2a58a4da4284e773c8d577787273e650e6823704d3715082c59"}'
#response = requests.post(
#    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
#    params=params,
#    cookies=cookies,
#    headers=headers,
#    data=data,
#)




import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': 'id="hWNI32WWbY08l1Arphk2EFho", type="cn"',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-one-session-token': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shop-pay-token': 'eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaWQ6XC9cL3Nob3BpZnlcL1Nob3BcLzkyNTU0NDk0Mjk4IiwibmJmIjoxNzkyMTc5ODAxLCJzZXNzaW9uX3Rva2VuIjoiQUFFQld5Y0M5RnFEU19Lblg0MURKb1gzOF9RcjQwOVZZSnZfMU9fdTlVcURPMm5JSzh6RWpycDNqR0lpUDJzVi1lSy1WSVJPa3V4MmFGeWt2c2R1TndyS3BJQ00xQmxrNXdMVUgtMlVIeUU5UWFiQzJRcEd4dVdVa2x5dkNQRlYteXNOUVg3M29ITkEzNjlhYWVPdTh0by1lYnRMU3dKYzhqelZaSVF2MjROcmoxYU5OcmZrSno3d3VfM0ZMRVFPZF9USkxTMVlZVlB5TkdtRlA4OU94Q25Dc3VJYVJvcm9nMFN6dmV3Iiwic2Vzc2lvbl9jdXN0b21lcl9pZCI6MTA1MDczNjk4NDA5ODYsInNob3BfYWNjb3VudF91dWlkIjoiYTQ2ZWJiODUtNjc0Ny00NzhjLWE3ZmUtOTc5NDBjYzRiMWZmIiwic2hvcF9wYXlfZGF0YSI6IkNBSVNHWGRwZW1GeVpHeDVZWFZ5WVRrNU9VQm5iV0ZwYkM1amIyMGFFaGV3SEtTZEF1YVBZWVVfdkNNM3QwVU9oQ0lRcEc2N2hXZEhSNHluX3BlVURNU3hfempZX01uV0Jrb1NETm9uTXNVV2ZrX19wbHkwUTRDZGwxMEUiLCJjdXN0b21lcl9hdXRoZW50aWNhdGlvbl9hdXRoX3Byb3ZpZGVyIjoibG9naW5fd2l0aF9zaG9wIiwiZXhwIjoxNzkyMTgzNDAxLCJsYW5kaW5nX3BhZ2UiOiJcLyIsIm9yaWdfcmVmZXJyZXIiOiIiLCJtZXJjaGFudF9jb25zZW50IjoiM0FNUC5TIn0.eJ_036fE8fV7VlRQ_VrMQfgnE1KbP_duYqno-fhCrA0',
    'x-shopify-tracking-consent': '3S.AMP',
    'x-shopify-uniquetoken': 'c1e69033-8b91-45e6-8e70-d2adaeca3fe5',
    'x-shopify-visittoken': '9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2',
}

params = {
    'operationName': 'PollForReceipt',
}

json_data = {
    'variables': {
        'receiptId': 'gid://shopify/ProcessedReceipt/9a686188c040654dfc50eb7eda0c5988',
        'sessionToken': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    },
    'operationName': 'PollForReceipt',
    'id': '98f65f1b789aa2a58a4da4284e773c8d577787273e650e6823704d3715082c59',
}

response = requests.post(
    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"receiptId":"gid://shopify/ProcessedReceipt/9a686188c040654dfc50eb7eda0c5988","sessionToken":"AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew"},"operationName":"PollForReceipt","id":"98f65f1b789aa2a58a4da4284e773c8d577787273e650e6823704d3715082c59"}'
#response = requests.post(
#    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
#    params=params,
#    cookies=cookies,
#    headers=headers,
#    data=data,
#)



#from.here poll for receipt 8 times aftr that 


# this is last pollforreceipt

import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': 'id="hWNI32WWbY08l1Arphk2EFho", type="cn"',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-one-session-token': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shop-pay-token': 'eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaWQ6XC9cL3Nob3BpZnlcL1Nob3BcLzkyNTU0NDk0Mjk4IiwibmJmIjoxNzkyMTc5ODAxLCJzZXNzaW9uX3Rva2VuIjoiQUFFQld5Y0M5RnFEU19Lblg0MURKb1gzOF9RcjQwOVZZSnZfMU9fdTlVcURPMm5JSzh6RWpycDNqR0lpUDJzVi1lSy1WSVJPa3V4MmFGeWt2c2R1TndyS3BJQ00xQmxrNXdMVUgtMlVIeUU5UWFiQzJRcEd4dVdVa2x5dkNQRlYteXNOUVg3M29ITkEzNjlhYWVPdTh0by1lYnRMU3dKYzhqelZaSVF2MjROcmoxYU5OcmZrSno3d3VfM0ZMRVFPZF9USkxTMVlZVlB5TkdtRlA4OU94Q25Dc3VJYVJvcm9nMFN6dmV3Iiwic2Vzc2lvbl9jdXN0b21lcl9pZCI6MTA1MDczNjk4NDA5ODYsInNob3BfYWNjb3VudF91dWlkIjoiYTQ2ZWJiODUtNjc0Ny00NzhjLWE3ZmUtOTc5NDBjYzRiMWZmIiwic2hvcF9wYXlfZGF0YSI6IkNBSVNHWGRwZW1GeVpHeDVZWFZ5WVRrNU9VQm5iV0ZwYkM1amIyMGFFaGV3SEtTZEF1YVBZWVVfdkNNM3QwVU9oQ0lRcEc2N2hXZEhSNHluX3BlVURNU3hfempZX01uV0Jrb1NETm9uTXNVV2ZrX19wbHkwUTRDZGwxMEUiLCJjdXN0b21lcl9hdXRoZW50aWNhdGlvbl9hdXRoX3Byb3ZpZGVyIjoibG9naW5fd2l0aF9zaG9wIiwiZXhwIjoxNzkyMTgzNDAxLCJsYW5kaW5nX3BhZ2UiOiJcLyIsIm9yaWdfcmVmZXJyZXIiOiIiLCJtZXJjaGFudF9jb25zZW50IjoiM0FNUC5TIn0.eJ_036fE8fV7VlRQ_VrMQfgnE1KbP_duYqno-fhCrA0',
    'x-shopify-tracking-consent': '3S.AMP',
    'x-shopify-uniquetoken': 'c1e69033-8b91-45e6-8e70-d2adaeca3fe5',
    'x-shopify-visittoken': '9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2',
}

params = {
    'operationName': 'PollForReceipt',
}

json_data = {
    'variables': {
        'receiptId': 'gid://shopify/ProcessedReceipt/9a686188c040654dfc50eb7eda0c5988',
        'sessionToken': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    },
    'operationName': 'PollForReceipt',
    'id': '98f65f1b789aa2a58a4da4284e773c8d577787273e650e6823704d3715082c59',
}

response = requests.post(
    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"receiptId":"gid://shopify/ProcessedReceipt/9a686188c040654dfc50eb7eda0c5988","sessionToken":"AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew"},"operationName":"PollForReceipt","id":"98f65f1b789aa2a58a4da4284e773c8d577787273e650e6823704d3715082c59"}'
#response = requests.post(
#    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
#    params=params,
#    cookies=cookies,
#    headers=headers,
#    data=data,
#)




#ahow insufficient
import requests

cookies = {
    '_shop_app_essential': ':AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:',
    '_shopify_essential': ':AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:',
    'cart': 'hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278',
    'cart_currency': 'INR',
}

headers = {
    'authority': 'shop.app',
    'accept': 'application/json',
    'accept-language': 'en-IN',
    'content-type': 'application/json',
    # 'cookie': '_shop_app_essential=:AaFGPYGmAAEBoehi2G5pX40hkkXefPSQ5X_eRCj62M82VGeN_LQE16_K6MlVVEw95OizOsndNRz8hw8WCjSy9NvJR9y0jJcBdLET88W4QBF27Dzb6Z1DYaLx9no-PD_jPzWDyHEEJGHgHY4ni9fbqa2sYX7oV38A59mYX3M9SR_jgsdUasYtDp9RJPg0-3qkhlldOLHhg6maRFvKJ5oHNFWqcWUfgjpwU-ZWpnaOJUoukzYUaVQ0LwKqenIpB4Zh0lH0V7b6lVl7sgziI72CIjuKui31wtbV1oKJTaH3c7BKNy5BKPZoBm2ba8U9XdfqWHUq-7flcS5vqetSgwx-ZkVQqzjQ3ZHC_BCo5NJihKoD:; _shopify_essential=:AaFGPYu0AAH_v6MO9Uf2Dh3e9vOct8kZz23QVIp3ZLOOrmn7-xPomLzqk2eGQSSTCHgyinL6E2GKsohDm7qCUXFTN5w:; cart=hWNI32WWbY08l1Arphk2EFho%3Fkey%3D25b213c8113164d02651dcbac572e278; cart_currency=INR',
    'origin': 'https://shop.app',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'shopify-checkout-source': 'id="hWNI32WWbY08l1Arphk2EFho", type="cn"',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    'x-checkout-one-session-token': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
    'x-checkout-web-build-id': '1957883a1110044653c9478ad7405c3dac788c90',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWNI32WWbY08l1Arphk2EFho',
    'x-shop-pay-token': 'eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaWQ6XC9cL3Nob3BpZnlcL1Nob3BcLzkyNTU0NDk0Mjk4IiwibmJmIjoxNzkyMTc5ODAxLCJzZXNzaW9uX3Rva2VuIjoiQUFFQld5Y0M5RnFEU19Lblg0MURKb1gzOF9RcjQwOVZZSnZfMU9fdTlVcURPMm5JSzh6RWpycDNqR0lpUDJzVi1lSy1WSVJPa3V4MmFGeWt2c2R1TndyS3BJQ00xQmxrNXdMVUgtMlVIeUU5UWFiQzJRcEd4dVdVa2x5dkNQRlYteXNOUVg3M29ITkEzNjlhYWVPdTh0by1lYnRMU3dKYzhqelZaSVF2MjROcmoxYU5OcmZrSno3d3VfM0ZMRVFPZF9USkxTMVlZVlB5TkdtRlA4OU94Q25Dc3VJYVJvcm9nMFN6dmV3Iiwic2Vzc2lvbl9jdXN0b21lcl9pZCI6MTA1MDczNjk4NDA5ODYsInNob3BfYWNjb3VudF91dWlkIjoiYTQ2ZWJiODUtNjc0Ny00NzhjLWE3ZmUtOTc5NDBjYzRiMWZmIiwic2hvcF9wYXlfZGF0YSI6IkNBSVNHWGRwZW1GeVpHeDVZWFZ5WVRrNU9VQm5iV0ZwYkM1amIyMGFFaGV3SEtTZEF1YVBZWVVfdkNNM3QwVU9oQ0lRcEc2N2hXZEhSNHluX3BlVURNU3hfempZX01uV0Jrb1NETm9uTXNVV2ZrX19wbHkwUTRDZGwxMEUiLCJjdXN0b21lcl9hdXRoZW50aWNhdGlvbl9hdXRoX3Byb3ZpZGVyIjoibG9naW5fd2l0aF9zaG9wIiwiZXhwIjoxNzkyMTgzNDAxLCJsYW5kaW5nX3BhZ2UiOiJcLyIsIm9yaWdfcmVmZXJyZXIiOiIiLCJtZXJjaGFudF9jb25zZW50IjoiM0FNUC5TIn0.eJ_036fE8fV7VlRQ_VrMQfgnE1KbP_duYqno-fhCrA0',
    'x-shopify-tracking-consent': '3S.AMP',
    'x-shopify-uniquetoken': 'c1e69033-8b91-45e6-8e70-d2adaeca3fe5',
    'x-shopify-visittoken': '9f5c2d95-696f-4101-a28a-bd0fe8c2ffc2',
}

params = {
    'operationName': 'Proposal',
}

json_data = {
    'variables': {
        'sessionInput': {
            'sessionToken': 'AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew',
        },
        'queueToken': 'A0HvoL68GXwj8y5jBoheY-10kRyWFB6pU2fDJ7g8Tm-79byPjLF0A5Zwi-KOb6rtJml68-hhL_RwnvUNX3G8M8cAEmovDIeVN0yo42UW3AC59Y5RxFet-GF2-wUTEM0WYg==',
        'discounts': {
            'lines': [],
            'acceptUnexpectedDiscounts': True,
        },
        'delivery': {
            'deliveryLines': [
                {
                    'destination': {
                        'partialStreetAddress': {
                            'address1': 'Bijipur Main Road Sundar Nagar',
                            'address2': '',
                            'city': 'Brahmapur',
                            'countryCode': 'IN',
                            'postalCode': '760001',
                            'firstName': 'Subham',
                            'lastName': 'Kumar',
                            'zoneCode': 'OR',
                            'phone': '+917853878533',
                            'oneTimeUse': False,
                        },
                    },
                    'selectedDeliveryStrategy': {
                        'deliveryStrategyByHandle': {
                            'handle': 'daadf5d473ea94fde5b8c3a5893e2c72-1857f5edbd56cb87c7e3af188778f2e4',
                            'customDeliveryRate': False,
                        },
                        'options': {
                            'phone': '+917853878533',
                        },
                    },
                    'targetMerchandiseLines': {
                        'lines': [
                            {
                                'stableId': '9720debd-5883-45ef-bf0d-fdc7d9558d88',
                            },
                        ],
                    },
                    'deliveryMethodTypes': [
                        'SHIPPING',
                    ],
                    'expectedTotalPrice': {
                        'value': {
                            'amount': '1700.00',
                            'currencyCode': 'INR',
                        },
                    },
                    'destinationChanged': False,
                },
            ],
            'noDeliveryRequired': [],
            'useProgressiveRates': False,
            'prefetchShippingRatesStrategy': None,
            'interfaceFlow': 'SHOP_PAY',
            'supportsSplitShipping': True,
        },
        'deliveryExpectations': {
            'deliveryExpectationLines': [
                {
                    'signedHandle': 'glX4nh3EzMFGOJkMsrZNqFZ31obSW5y+WzHSh/DFysUU3ul7ixJNdSL07QjVQrNzRs8Dny1JOFl0SQ7KZXs/L9fpBQ9fcizTsPxZy3IjDZR/KGSP4Kse/BZHmg911lhNuKIryLDrKd+GsNLj0rSyGU//YaJOcgxyFHPcUbRGDkIUAbkgM/KtPfMBVaT++Wf39ldI08yu9fGrp6i38RGTIgzm0F8Hre9pQzpjW/nvRZNA6hqCXleaYlc9BVBh+UQEzpXBkK15WeVYlPNCYn6v1C1PiawyNma/7SDPIc32xbAj4XA8Zkn0mOoUTlqYU/V/r5Uipc6OfLr16YL5k0ekeZcIsCq3jWh3G4LX3Acb3RLqdD1a+JCBaFgsuxsxI1NvmSveu7vfXe5d629IJ95UAcNKZubfvf9OQuzZf2WE7ehM0FnsOrsQQza2llCeUhwfWAzJfjxu3QBUV2lcCYyvVrHL7hwIQ0GAm8X6TTiaR4wqhNLiZNPJdJvJlboDa2iLc1x8HkO5UJSdWx9ddl6SrUzy930s125Iqm8U46DNewTRLyFQi3jZPm6hGXRoTZdlJi2EiZnL6t3J9DLcHasS5RFTt67aw9D3cZwlp9yTF6O1n9mzdIzPhmjgSCYL2/9L0WVNoi/hYAMgpam79gZWqFdBn0IMuV7F6Lve/Jk+tSPJ762z3wSDyJ8K6WFzVbpKo6UlkpNyk6mHkfEyynu4MuFLUr9lj4A1tyggs0VuJXHcDeDDOYsKM0zeCjUw4OK2NC8rqZ5bUZI7zV8y17NKeJKeEOq+aFnBykWHbSMbr3c7Cw56dPMMc6oX2z2p07BTNufvTmyMBpHUIPBD8v213F7Rhg6xx10VJqolRYDGDk8RzWdgXfJ+X0LVQKJcyQ4TXdKXSlFCvSazfASaFDUcE5llwac26sE9eplmD4HyI2WiionPbItY+oL3sdy1pkOY/UyLWrAUD+pR10kQfW9DBTmaegvKdVfA9DUW1FQErm1SNy6RxSdTR9wreLZmzL8YcihZHlEx4hkI3Gd3MKDDWmobI9XNgzr6DJH/x2P7vTmWiVEZakVPatAMfLfyvm69r+ToCNrsMeM+NmnQ6WuA9SFaR2w6hCmoQN3pBGopsZRYLYXokPbfqmlrmcHxWaCiU8FQMrRZbY65vcszwaDI/RTkOuZVIeLfErMXVvob5Wj5dRB7fWbvpUi2xRGu6C6C5/RilrVe0Tpm/GDDxsiaTDT11nfDNOUyIuWqBO8Hryq2Oz4YWfcB/0nDOFMLKsHCGZLDFhkWD2k+lFc9xQW65beDBL0oGOickR/HO/Ig9ODNFTGT//b8qnhSRPOVPk7cEKyllNT+1Gky1N/xAWEOH+TM3YY510EITpMvNvhxZIWF1MR5tWQ6d9O1Rld9PVpS7/7yN/tpnKexREcda/otSMd20r9zklrGYOotmTqQaQxCLoYxVBVfAlg2Tbc3cUQlS68EZwxgT9slFJz/pee1cNEJb4uyuDlZY5rql+1VHOJgX+lm05ximcgRiGxh/2m2--BGaxSqjwpAMQc7Gc--dQF0+7FrX/iBBIwc/wmIvA==',
                },
            ],
        },
        'merchandise': {
            'merchandiseLines': [
                {
                    'stableId': '9720debd-5883-45ef-bf0d-fdc7d9558d88',
                    'merchandise': {
                        'productVariantReference': {
                            'id': 'gid://shopify/ProductVariantMerchandise/51732384481626',
                            'variantId': 'gid://shopify/ProductVariant/51732384481626',
                            'properties': [],
                            'sellingPlanId': None,
                            'sellingPlanDigest': None,
                        },
                    },
                    'quantity': {
                        'items': {
                            'value': 1,
                        },
                    },
                    'expectedTotalPrice': {
                        'value': {
                            'amount': '4100.00',
                            'currencyCode': 'INR',
                        },
                    },
                    'lineComponentsSource': None,
                    'lineComponents': [],
                },
            ],
        },
        'memberships': {
            'memberships': [],
        },
        'payment': {
            'totalAmount': {
                'any': True,
            },
            'paymentLines': [
                {
                    'paymentMethod': {
                        'directPaymentMethod': None,
                        'giftCardPaymentMethod': None,
                        'ownedGiftCardPaymentMethod': None,
                        'redeemablePaymentMethod': None,
                        'walletPaymentMethod': {
                            'name': 'SHOP_PAY',
                            'walletContent': {
                                'shopPayWalletContent': {
                                    'sessionToken': 'spt_eThlTWZBUTEvRGM3VEd6VUFMeCt6YWlyTlZkcldxbkxqZVBlSDV6K2RrZFZla1k1UE0zVVZHUm1jL0F1VWNsT1dNNUg1OE45TUxLdmNQMDlQMzZFa0N4MmZDaVltZ2NMMElyR3I4RXZFRTV0bUtOVnRBaWFhbGtIWUxCcFpTVi9uSnp6SUdYN2d6NXAxcUpVejE0T2xlNHRTK2dJVG5tRGVMeXJxaG5PQk1XNzluSytGTk1jK2pMQzZ6SXFoNzYwMUV5dUNnajh5TmI2SFhKRm5VQmFzd2hSMHljR2E2NVM0OEwyeXI5c1JKZ0ZaVW9XclVMSFNZNmhLNjR0QTJ3NmVQRU9RNTBwdnpWTFdOaWtUWExCK2dRVmw2MnRiZ3JhU1Z0ejN0N3lpWmtBQy9tL2YzMlM1bVp0NDVBVmZwc25Pd2xyS2lLMFVDU2RxNXVhNUhRQTBPWkI2L2paTzYyMjZVVE4vcHVLbjlOZjFzN3hRU24xSzlwY1UveWdtdWgzV1hGamptSFFxbktUYVhVeGsvVTVUYmlQaXo5dFk1THlNeXRiZHIxbVZCTHVrSG5XVUkvSHB3b3laUGJGamxpeWpSdnhnaC9tQWVkaVZRcldKQTFjelN6a1ozRHFISEh5eE92cUhvN2pxU3grZ0lCbEdIa2YxY2ptTWdlYk5hQVd0aFRsY2ZDakhzVHU5UjN2NUVhbVBLZXNSV0FrYkdDRGRwQ1h4T2pyZHVCU1RjYVZ5N0lXdHo2RzBMUTZrMWpMb2U3WGJodUdtT1pxVXd2RjBJRzB3ZDFwWGFlQVZBQlhmV3NRMlc4NENWU0tRK0tTV0ZRVUQvT0pSZ2dVT1pORUtGcmh6MmJoSXAwZUdsVXU3Q1lHK1QzSzg1Mk9yR21YQnlLaTNKQU5jNEs4aUFBMlhpQzJvQXc0ZDkwMXdJYmJQZVk1dmFrdEVXVCtvdUtFUVZJQWZLcks5T1o1QUxBc2owVmdyODMvNVVPZGNxOFdNUkRpYjhUWk1LNXRrbHJqeGRyL2ZxSUN0clV5ak5MV0krSXpnUGVtK3dQMU1scEl1UTllQTA2b1RKVnhLYml2MWJZczRtR0VXYTlOOVI1QWtUaGE0SFRjWHhGUkJXR0t6RVB2NHpZWHdyUWhDRTNKbDl0MGE1NHpDQzBheThsckx4MGFEUWcxK1RtLzZONldOK2Q3QWJoVjIxTVF0a1NSZlNVcExENmZCeUkxbFR1bVRKc2N1UzZhdVJ3NFgvSkIwRXJva0trUi85UTIrTjZoZnZuL1JUZkd1M1ZvVGdveTBKWHVvUTMzUzBLWURGMlc1TDZpd1JESHJWMGhMbFhxTzVabmZTeEhKaW5NVVVsUmJRQTVHdHNJbG5ZUGUwbU1ibmVWVDhVbDloYktkb1VlbmwrQktwMVhQTmNkMkhOOVRTNmhOd1owZ1kwZEtyYldvT21vVnM2clA5WEpaQVVmSXZlUDEvT0xVTjF1UGlPMHRLMk5RQW1yOGNOTDhIMzJPVmpBbzMxbE1SZFFtalYrM24rMEpXUGgwbU5ZeEphSnZCMGpRcmttM0YyaWRMYkowcFpsVVowdHY4WTRvb0hHdmgrM04zbEFYNDdpcjR5Mjd1dHdpd2JMNnRLbmhhaWQ0bncrbFlyVXZnbzk5bjJKL3lENmY5V2hKNmZ4SGFkNGsyZ1crMC9qTzNIblliWDVFNFNWRFJhVTl4R2MvVnJzRjZkbXRkajJMa1NnSGM2UU4vOWdNK3NtazVyc2FXcTFLaEZiVjhyVkkzR1lLdUNJeW4rQTNrT3BqdVYvaHQwY1ZoZEVUY2NnMEE3N2xrTTcrVGgyc0ZUOTVUSFJaVEZUdnNNY1M4Zm9tdDhDcWJCQWcxVUs0ai9OSG9HbjNiMU51MjlBbGtDSmdyUUd5dlNEWlUyMWFkK2lreUFTem9obnB0Y1FhUHlyMElaUXM0YklIOWN6V3Fvc3h3N1FNajVHdmRQNU1pTHN1R0ozajBaMzlUbCs3TFB2R29uS1VUeGFyWVBTNGZvZlZUMFQvRFdVSDYvalgvNmo5YnNSV3A3UFpnTzdoUWZzWFpkUUY4WHRoZHY0LzNESlJnQWtTajlhdXNNblM4WVd6Q3ZBUk03VU00azF6Y3RXa3ZUTUZMTTdrMG1idTc1SVEyVlFjckdpUGsvQWpjTEdMZm9WUFg2dmplQ0Z2OEt3Tm5BRnhTUGhqNnFaSzk1MGRKcEYvbWFiR2U5Wkx3PT0tLUtuME03TXNaWWdzdjUvMUd2VnlEbVE9PQ==--cd891a6b53d3315872932a9a1137077262714373',
                                    'billingAddress': {
                                        'streetAddress': {
                                            'address1': 'Bijipur Main Road Sundar Nagar',
                                            'address2': '',
                                            'city': 'Brahmapur',
                                            'countryCode': 'IN',
                                            'postalCode': '760001',
                                            'firstName': 'Subham',
                                            'lastName': 'Kumar',
                                            'zoneCode': 'OR',
                                            'phone': '+917853878533',
                                        },
                                    },
                                    'paymentMethod': 'CREDIT_CARD',
                                    'paymentMethodIdentifier': '12ba72fffce249eb2764c19cac64fb92',
                                },
                            },
                        },
                        'walletsPlatformPaymentMethod': None,
                        'localPaymentMethod': None,
                        'paymentOnDeliveryMethod': None,
                        'paymentOnDeliveryMethod2': None,
                        'manualPaymentMethod': None,
                        'customPaymentMethod': None,
                        'offsitePaymentMethod': None,
                        'customOnsitePaymentMethod': None,
                        'deferredPaymentMethod': None,
                        'customerCreditCardPaymentMethod': None,
                        'paypalBillingAgreementPaymentMethod': None,
                        'remotePaymentInstrument': None,
                    },
                    'amount': {
                        'any': True,
                    },
                },
            ],
            'billingAddress': {
                'streetAddress': {
                    'address1': 'Bijipur Main Road Sundar Nagar',
                    'address2': '',
                    'city': 'Brahmapur',
                    'countryCode': 'IN',
                    'postalCode': '760001',
                    'firstName': 'Subham',
                    'lastName': 'Kumar',
                    'zoneCode': 'OR',
                    'phone': '+917853878533',
                },
            },
            'allowStoreCredit': False,
        },
        'buyerIdentity': {
            'customer': {
                'presentmentCurrency': 'INR',
                'countryCode': 'IN',
            },
            'email': 'wizardlyaura999@gmail.com',
            'emailChanged': False,
            'phoneCountryCode': 'IN',
            'marketingConsent': [
                {
                    'email': {
                        'consentState': 'DECLINED',
                        'value': 'wizardlyaura999@gmail.com',
                    },
                },
            ],
            'shopPayOptInPhone': {
                'number': '+917853878533',
                'countryCode': 'IN',
            },
            'shopUserSecureData': 'eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s',
            'prefillSource': 'SHOP_PAY',
            'rememberMe': False,
        },
        'tip': {
            'tipLines': [],
        },
        'taxes': {
            'proposedAllocations': None,
            'proposedTotalAmount': {
                'value': {
                    'amount': '0',
                    'currencyCode': 'INR',
                },
            },
            'proposedTotalIncludedAmount': None,
            'proposedMixedStateTotalAmount': None,
            'proposedExemptions': [],
        },
        'note': {
            'message': None,
            'customAttributes': [],
        },
        'localizationExtension': {
            'fields': [],
        },
        'shopPayArtifact': {
            'shopUser': {
                'uuid': 'eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s',
            },
        },
        'nonNegotiableTerms': None,
        'scriptFingerprint': {
            'signature': None,
            'signatureUuid': None,
            'lineItemScriptChanges': [],
            'paymentScriptChanges': [],
            'shippingScriptChanges': [],
        },
        'optionalDuties': {
            'buyerRefusesDuties': False,
        },
        'captcha': {
            'provider': 'hcaptcha',
            'challenge': 'comparison_challenge_type',
            'token': 'P1_eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.3gAHp3Bhc3NrZXnFBHR8Nu7dGvRjHJZWFQ5ftoV87npezg1Of8eb3el70cTYlkQyU9D-A1L0NP4tG0CAjXGnhUE7yp7CHEiQ6SB4bvxrb97mbRcgYkwQ1UVBlesg8zxjgWEa7JHzZYovuDl1oSs4syrJp6A_pVyFw2iKafJcgBjQ9862V1mkIioYjJp3cU1exp4hrUU5cqNM7ZO4f9424I1WSIZMullCsXR4CI2WxK6TO05Xe_RHORal0w1Jz5YHzBMr7O0Q4ijsuOgLA5u3a0mvG8nhz88pR9LzF8s--LQkyoQs2whEvhZFEU7cCzmBHA_kjzr6uEyn-Jfes-t-WAd-1tHco-dCXrJeZhC_VhjXmNUHoSFwx7Uvn0x_o2dgzLKpUKCTD82VcjrwVUggHRZheSGkzF1HIdsE4-cqpeDgKQIIufoHySFC1HsBcexgEE7MmPcR-K1AswC5GrMmbEMFvZ1sPIlfBiIeO3M_jMRAcYgNLFdb0Wpg5QIktwpME1agAavpK_2JZz_32VmxlJCCKe61Trj9yzkHLhwvQhl8fHjh3tBDlTufveuRw00VyBO-gPKKzAWEk1cDBhcxlE3RrG3HlHrwjQSLB1TR5Nj-yPWVEb-MD8l62czV0gI_rh0Rs4M96Iv4OX4I5zf2h1T_69tuo5FDujvyM4_hIyNmagn6Kg65e7zF4MsfWbMHZDTs0yuDr5CRC3zZmsTRQM5SpIv3rHs-LAJU-tDAV8U7MvXYT1RVlkVcYPB0FVtWmaaKeBVV7X3RpsXZ_QZruPBam4txZR837_vy6w-YHn-2AhYDTjOdH0s7gNM7pcK5qrzabNtmIOrRuEEPLei8jdagG7sTEEEoc9hFNmsnPWkwxymHxExPL-CfDqUQHb1hCqSAriUin1OyjNq3BhdHFGEMjR03nui3MDssCwrRmH3Lr6dzMLGvX777Nvyb5-LG5skt8jPR48CvceG30WScw1rN92sQmgY1Ac-tqg48yuDTewBrXGo-oXttCsYLd6Gp_sqNFjgaFCPt9pxHwP196DNPIBk9zT3E2i__RiGE5NnJ517DbbLhBXXk7ZyBqi9EzggnrGc8A-f38a67VLd_3xL8ZiAvH-zVeOKSOAG5CoJgXQy90qEl6s0Tllo_PUJgcqVgHMZMweLxLmcPVSaxlpfc07p1cEFA4j1X6JLhv045diod5fNR6OFIZouPp9js8Vp6HlBTXz9HV5Uk8C0c_jZfixC-PyXGrkbnYeZh-mtNq6Z6cIcNUFY76sVhKo7QNPa3wFLn6eu-Dzz6IHI969ybTtL6Wq6xiA-wzceDbHVIyt2Fu0RTzAv0FkWrMR2Z1IkfGQb5gCfkGODE7ibKbRWrSsbpeoFdIr107Gyja4URRzf5KHOLboqgce9lP9FKyFHrAgzso6q7LsCWGlEjNcJBVzqfcs46aJw6WA6ZRigeb4ICzvAA3KluwQPxrqOWaEnM2D_th17kXnYXgeR9NSkRhqgHwlKyKSaMxdpMZv7ExwBaCD4u50-c6ZVFyjdrfq-nc2l0ZWtledkkMWYyNjIzYjEtZWIxOS00OTE2LThiNDMtMDg0YThhNzg1YjIzo2V4cM5q0n9jonBkAKVjZGF0YdQAAKZjZGF0YTLUAACia3KoM2E1YWFiNmU.MF_TS7zYc2wPr3_WzUBV1x0sOyZaDNRM5PSg0nrKHHU',
        },
        'cartMetafields': [],
    },
    'operationName': 'Proposal',
    'id': '218ca3f4634df050ead785d9692d50bc444d93ef926a6c0d820c1c01a02d474f',
}

response = requests.post(
    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"variables":{"sessionInput":{"sessionToken":"AAEBWycC9FqDS_KnX41DJoX38_Qr409VYJv_1O_u9UqDO2nIK8zEjrp3jGIiP2sV-eK-VIROkux2aFykvsduNwrKpICM1Blk5wLUH-2UHyE9QabC2QpGxuWUklyvCPFV-ysNQX73oHNA369aaeOu8to-ebtLSwJc8jzVZIQv24Nrj1aNNrfkJz7wu_3FLEQOd_TJLS1YYVPyNGmFP89OxCnCsuIaRorog0Szvew"},"queueToken":"A0HvoL68GXwj8y5jBoheY-10kRyWFB6pU2fDJ7g8Tm-79byPjLF0A5Zwi-KOb6rtJml68-hhL_RwnvUNX3G8M8cAEmovDIeVN0yo42UW3AC59Y5RxFet-GF2-wUTEM0WYg==","discounts":{"lines":[],"acceptUnexpectedDiscounts":true},"delivery":{"deliveryLines":[{"destination":{"partialStreetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533","oneTimeUse":false}},"selectedDeliveryStrategy":{"deliveryStrategyByHandle":{"handle":"daadf5d473ea94fde5b8c3a5893e2c72-1857f5edbd56cb87c7e3af188778f2e4","customDeliveryRate":false},"options":{"phone":"+917853878533"}},"targetMerchandiseLines":{"lines":[{"stableId":"9720debd-5883-45ef-bf0d-fdc7d9558d88"}]},"deliveryMethodTypes":["SHIPPING"],"expectedTotalPrice":{"value":{"amount":"1700.00","currencyCode":"INR"}},"destinationChanged":false}],"noDeliveryRequired":[],"useProgressiveRates":false,"prefetchShippingRatesStrategy":null,"interfaceFlow":"SHOP_PAY","supportsSplitShipping":true},"deliveryExpectations":{"deliveryExpectationLines":[{"signedHandle":"glX4nh3EzMFGOJkMsrZNqFZ31obSW5y+WzHSh/DFysUU3ul7ixJNdSL07QjVQrNzRs8Dny1JOFl0SQ7KZXs/L9fpBQ9fcizTsPxZy3IjDZR/KGSP4Kse/BZHmg911lhNuKIryLDrKd+GsNLj0rSyGU//YaJOcgxyFHPcUbRGDkIUAbkgM/KtPfMBVaT++Wf39ldI08yu9fGrp6i38RGTIgzm0F8Hre9pQzpjW/nvRZNA6hqCXleaYlc9BVBh+UQEzpXBkK15WeVYlPNCYn6v1C1PiawyNma/7SDPIc32xbAj4XA8Zkn0mOoUTlqYU/V/r5Uipc6OfLr16YL5k0ekeZcIsCq3jWh3G4LX3Acb3RLqdD1a+JCBaFgsuxsxI1NvmSveu7vfXe5d629IJ95UAcNKZubfvf9OQuzZf2WE7ehM0FnsOrsQQza2llCeUhwfWAzJfjxu3QBUV2lcCYyvVrHL7hwIQ0GAm8X6TTiaR4wqhNLiZNPJdJvJlboDa2iLc1x8HkO5UJSdWx9ddl6SrUzy930s125Iqm8U46DNewTRLyFQi3jZPm6hGXRoTZdlJi2EiZnL6t3J9DLcHasS5RFTt67aw9D3cZwlp9yTF6O1n9mzdIzPhmjgSCYL2/9L0WVNoi/hYAMgpam79gZWqFdBn0IMuV7F6Lve/Jk+tSPJ762z3wSDyJ8K6WFzVbpKo6UlkpNyk6mHkfEyynu4MuFLUr9lj4A1tyggs0VuJXHcDeDDOYsKM0zeCjUw4OK2NC8rqZ5bUZI7zV8y17NKeJKeEOq+aFnBykWHbSMbr3c7Cw56dPMMc6oX2z2p07BTNufvTmyMBpHUIPBD8v213F7Rhg6xx10VJqolRYDGDk8RzWdgXfJ+X0LVQKJcyQ4TXdKXSlFCvSazfASaFDUcE5llwac26sE9eplmD4HyI2WiionPbItY+oL3sdy1pkOY/UyLWrAUD+pR10kQfW9DBTmaegvKdVfA9DUW1FQErm1SNy6RxSdTR9wreLZmzL8YcihZHlEx4hkI3Gd3MKDDWmobI9XNgzr6DJH/x2P7vTmWiVEZakVPatAMfLfyvm69r+ToCNrsMeM+NmnQ6WuA9SFaR2w6hCmoQN3pBGopsZRYLYXokPbfqmlrmcHxWaCiU8FQMrRZbY65vcszwaDI/RTkOuZVIeLfErMXVvob5Wj5dRB7fWbvpUi2xRGu6C6C5/RilrVe0Tpm/GDDxsiaTDT11nfDNOUyIuWqBO8Hryq2Oz4YWfcB/0nDOFMLKsHCGZLDFhkWD2k+lFc9xQW65beDBL0oGOickR/HO/Ig9ODNFTGT//b8qnhSRPOVPk7cEKyllNT+1Gky1N/xAWEOH+TM3YY510EITpMvNvhxZIWF1MR5tWQ6d9O1Rld9PVpS7/7yN/tpnKexREcda/otSMd20r9zklrGYOotmTqQaQxCLoYxVBVfAlg2Tbc3cUQlS68EZwxgT9slFJz/pee1cNEJb4uyuDlZY5rql+1VHOJgX+lm05ximcgRiGxh/2m2--BGaxSqjwpAMQc7Gc--dQF0+7FrX/iBBIwc/wmIvA=="}]},"merchandise":{"merchandiseLines":[{"stableId":"9720debd-5883-45ef-bf0d-fdc7d9558d88","merchandise":{"productVariantReference":{"id":"gid://shopify/ProductVariantMerchandise/51732384481626","variantId":"gid://shopify/ProductVariant/51732384481626","properties":[],"sellingPlanId":null,"sellingPlanDigest":null}},"quantity":{"items":{"value":1}},"expectedTotalPrice":{"value":{"amount":"4100.00","currencyCode":"INR"}},"lineComponentsSource":null,"lineComponents":[]}]},"memberships":{"memberships":[]},"payment":{"totalAmount":{"any":true},"paymentLines":[{"paymentMethod":{"directPaymentMethod":null,"giftCardPaymentMethod":null,"ownedGiftCardPaymentMethod":null,"redeemablePaymentMethod":null,"walletPaymentMethod":{"name":"SHOP_PAY","walletContent":{"shopPayWalletContent":{"sessionToken":"spt_eThlTWZBUTEvRGM3VEd6VUFMeCt6YWlyTlZkcldxbkxqZVBlSDV6K2RrZFZla1k1UE0zVVZHUm1jL0F1VWNsT1dNNUg1OE45TUxLdmNQMDlQMzZFa0N4MmZDaVltZ2NMMElyR3I4RXZFRTV0bUtOVnRBaWFhbGtIWUxCcFpTVi9uSnp6SUdYN2d6NXAxcUpVejE0T2xlNHRTK2dJVG5tRGVMeXJxaG5PQk1XNzluSytGTk1jK2pMQzZ6SXFoNzYwMUV5dUNnajh5TmI2SFhKRm5VQmFzd2hSMHljR2E2NVM0OEwyeXI5c1JKZ0ZaVW9XclVMSFNZNmhLNjR0QTJ3NmVQRU9RNTBwdnpWTFdOaWtUWExCK2dRVmw2MnRiZ3JhU1Z0ejN0N3lpWmtBQy9tL2YzMlM1bVp0NDVBVmZwc25Pd2xyS2lLMFVDU2RxNXVhNUhRQTBPWkI2L2paTzYyMjZVVE4vcHVLbjlOZjFzN3hRU24xSzlwY1UveWdtdWgzV1hGamptSFFxbktUYVhVeGsvVTVUYmlQaXo5dFk1THlNeXRiZHIxbVZCTHVrSG5XVUkvSHB3b3laUGJGamxpeWpSdnhnaC9tQWVkaVZRcldKQTFjelN6a1ozRHFISEh5eE92cUhvN2pxU3grZ0lCbEdIa2YxY2ptTWdlYk5hQVd0aFRsY2ZDakhzVHU5UjN2NUVhbVBLZXNSV0FrYkdDRGRwQ1h4T2pyZHVCU1RjYVZ5N0lXdHo2RzBMUTZrMWpMb2U3WGJodUdtT1pxVXd2RjBJRzB3ZDFwWGFlQVZBQlhmV3NRMlc4NENWU0tRK0tTV0ZRVUQvT0pSZ2dVT1pORUtGcmh6MmJoSXAwZUdsVXU3Q1lHK1QzSzg1Mk9yR21YQnlLaTNKQU5jNEs4aUFBMlhpQzJvQXc0ZDkwMXdJYmJQZVk1dmFrdEVXVCtvdUtFUVZJQWZLcks5T1o1QUxBc2owVmdyODMvNVVPZGNxOFdNUkRpYjhUWk1LNXRrbHJqeGRyL2ZxSUN0clV5ak5MV0krSXpnUGVtK3dQMU1scEl1UTllQTA2b1RKVnhLYml2MWJZczRtR0VXYTlOOVI1QWtUaGE0SFRjWHhGUkJXR0t6RVB2NHpZWHdyUWhDRTNKbDl0MGE1NHpDQzBheThsckx4MGFEUWcxK1RtLzZONldOK2Q3QWJoVjIxTVF0a1NSZlNVcExENmZCeUkxbFR1bVRKc2N1UzZhdVJ3NFgvSkIwRXJva0trUi85UTIrTjZoZnZuL1JUZkd1M1ZvVGdveTBKWHVvUTMzUzBLWURGMlc1TDZpd1JESHJWMGhMbFhxTzVabmZTeEhKaW5NVVVsUmJRQTVHdHNJbG5ZUGUwbU1ibmVWVDhVbDloYktkb1VlbmwrQktwMVhQTmNkMkhOOVRTNmhOd1owZ1kwZEtyYldvT21vVnM2clA5WEpaQVVmSXZlUDEvT0xVTjF1UGlPMHRLMk5RQW1yOGNOTDhIMzJPVmpBbzMxbE1SZFFtalYrM24rMEpXUGgwbU5ZeEphSnZCMGpRcmttM0YyaWRMYkowcFpsVVowdHY4WTRvb0hHdmgrM04zbEFYNDdpcjR5Mjd1dHdpd2JMNnRLbmhhaWQ0bncrbFlyVXZnbzk5bjJKL3lENmY5V2hKNmZ4SGFkNGsyZ1crMC9qTzNIblliWDVFNFNWRFJhVTl4R2MvVnJzRjZkbXRkajJMa1NnSGM2UU4vOWdNK3NtazVyc2FXcTFLaEZiVjhyVkkzR1lLdUNJeW4rQTNrT3BqdVYvaHQwY1ZoZEVUY2NnMEE3N2xrTTcrVGgyc0ZUOTVUSFJaVEZUdnNNY1M4Zm9tdDhDcWJCQWcxVUs0ai9OSG9HbjNiMU51MjlBbGtDSmdyUUd5dlNEWlUyMWFkK2lreUFTem9obnB0Y1FhUHlyMElaUXM0YklIOWN6V3Fvc3h3N1FNajVHdmRQNU1pTHN1R0ozajBaMzlUbCs3TFB2R29uS1VUeGFyWVBTNGZvZlZUMFQvRFdVSDYvalgvNmo5YnNSV3A3UFpnTzdoUWZzWFpkUUY4WHRoZHY0LzNESlJnQWtTajlhdXNNblM4WVd6Q3ZBUk03VU00azF6Y3RXa3ZUTUZMTTdrMG1idTc1SVEyVlFjckdpUGsvQWpjTEdMZm9WUFg2dmplQ0Z2OEt3Tm5BRnhTUGhqNnFaSzk1MGRKcEYvbWFiR2U5Wkx3PT0tLUtuME03TXNaWWdzdjUvMUd2VnlEbVE9PQ==--cd891a6b53d3315872932a9a1137077262714373","billingAddress":{"streetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533"}},"paymentMethod":"CREDIT_CARD","paymentMethodIdentifier":"12ba72fffce249eb2764c19cac64fb92"}}},"walletsPlatformPaymentMethod":null,"localPaymentMethod":null,"paymentOnDeliveryMethod":null,"paymentOnDeliveryMethod2":null,"manualPaymentMethod":null,"customPaymentMethod":null,"offsitePaymentMethod":null,"customOnsitePaymentMethod":null,"deferredPaymentMethod":null,"customerCreditCardPaymentMethod":null,"paypalBillingAgreementPaymentMethod":null,"remotePaymentInstrument":null},"amount":{"any":true}}],"billingAddress":{"streetAddress":{"address1":"Bijipur Main Road Sundar Nagar","address2":"","city":"Brahmapur","countryCode":"IN","postalCode":"760001","firstName":"Subham","lastName":"Kumar","zoneCode":"OR","phone":"+917853878533"}},"allowStoreCredit":false},"buyerIdentity":{"customer":{"presentmentCurrency":"INR","countryCode":"IN"},"email":"wizardlyaura999@gmail.com","emailChanged":false,"phoneCountryCode":"IN","marketingConsent":[{"email":{"consentState":"DECLINED","value":"wizardlyaura999@gmail.com"}}],"shopPayOptInPhone":{"number":"+917853878533","countryCode":"IN"},"shopUserSecureData":"eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s","prefillSource":"SHOP_PAY","rememberMe":false},"tip":{"tipLines":[]},"taxes":{"proposedAllocations":null,"proposedTotalAmount":{"value":{"amount":"0","currencyCode":"INR"}},"proposedTotalIncludedAmount":null,"proposedMixedStateTotalAmount":null,"proposedExemptions":[]},"note":{"message":null,"customAttributes":[]},"localizationExtension":{"fields":[]},"shopPayArtifact":{"shopUser":{"uuid":"eyJhbGciOiJSUzI1NiJ9.IlUyZGFZak56Um1wM2FVb3hUV05oU1VwV2NXdHpOMDVNYTIwMGVHVTFlREpXVDJVM05USlNVR0pQT1Vod1JDdG1jMFJ5TkUxcVZHOU1XbVFyZG1VMFNHcG1kVUprUW1GSFVYWnpVRm9yVmpGeVNWUkVOR0pQWlVVcmMxVkVWVEppVUNzemRHWnBXRFV2TlhnME9GVlVUVk16V2twd2VHbG9TVXRFUVhZclVXSnRSbFJTYjB0dk4yaEJiMUZDV2t0b2NXOTRPRmhOUVZob05WSk9ORnBHWWxKdlFUazJRM1pHUTBwTk1FMXpVRk56Y1hGSVVISk5aMGx2VVVselNGaERkMUJ6TDFkeU56ZHNTR3RWYUd4cGNVTnlUMWszTmxsUFpWTnJlRVExUVhSNGMwbEtabmMzWW5aSGNtNVdWVEl3WTFSeWNITlBWRVpKTVhoTFNYZEZRa3cwUlZKS2JtOURiV1I0VldoRFNGQkdibXRpTVRkeVRtSmlSM3A0ZEdSMFNtWnlOWEJoZVhnMWRtNVdOakozTkRsQmRVSkxVbGxOWVVoRVRXdE9kazVPTjI1d2JYWlNibkpyYzBzMlJUbG5PWEZ3VVdSQlVqSTNMMk5CTTI1cFp6bDBLM0poUldGMFltbHhSemRpVVdORllWTTJkWFYxZDFWSldqWjZjRFZEYjFOQlRFaFpPR3BKY1VoQ2VITnJlVEI1U0RORVNuSnBZemRPYmxKRU1HWTJZVVoyTVVSVlMyc3JkVTF2VVhCQ2VqbFhaMU4xV25scUwyOHJjVFVyUlhCRVRFUXpiVEpNUlZORmJqRklWbW81U0RaTlpWRmxabW8wU1RNM1ltMDVaakJwY0V4UlNYTmxOV28zYXk5R1pYWjVTMjEzY21KTGMwb3hlalpaYlhRdlJTdHNaV3hPVG05eGFuTkVhR1ZVVGpoUGVrRTFiM0JzVnpkV1VUbDBZV3c0YWtKUVRGRkJaV2swUldKR1V6SjZMekpOTUVOaFRqTlBUV0ptUWs5NVkweE9aMmRaVkhJNVJGbHdRV05hTkVNd1QxUklNRkpXU0hrMVltZGhObmx1ZGpGbWFtWndOVXBWTm5WblRqYzBkVEUxSzJwTWNDOUxLemh4WXpGelYyMXRTalZaVlhaU2RXMUJibEo2VFdkTmJGaDJjRTl1V0UxUU1VdHJRa3hwVEN0UlZYcFRNR3BYWlhCVVJYZHpNbWxqWlVKYWFYSjJjSFJqZFZWS05FWTJWWHBXYVVsMFpESlZSRFpXVEhCRWFYZGxOMnhSUFQwdExYTmpRa3hrVUNzeFRWVlBWblJLUXpCYVdYTnlNSGM5UFE9PS0tMWU3Y2M3ODM3ZTRhMWRkYTNiMDZkZmE1MjJjZjk4Y2IzOGRmYjlkNCI.XF2bwtDUQ_TWo5oHEu8dJdYkY1w3CHkkHqqDa9NlJTqyDMyaDryhROXlh2QG3NBwxnnSkNmx1H4crk16L-ZZyPqdEfw57owre-olCA31fYeYWLWkDpWQUs8nuZIrvhGSdq708w373eRJsxLAJZHdgwnUslhETe4WUJThcnzAiN5Nv2ceDoSNx5f4IUPNiUCoRQ3Dl2ALjynHzxvae4RPxd-1DME5c_8HEJoar7yG1cTsotLckyLLNftkMAgPdMSXdxteN731COUzaBI_BUi_v2PC4zr648vnMY0x6mB9teRKH7eA6cCDBifBKYlST-IIizEux9XW55fuAfy1t4AS4SLXniFxffQDb46j0BKiEqrdUk8fpOvRDHubp5OWe6D-nGPX4kGgoDpT-SVTO8TJe7ev1XCJH9wVk_2qtT98QSjEdhwdbBD3yv00Rly_WbqDjZyiyHTHqAMVSiqadSmP2m-RAkccScjZsWB6KARJt-uGYdoAIXp53wJBT1KjJ4_60jEyenOQ-L7KunWDbnHxzV01pLmaiiHRN7tgAoosEcfhV4nJst6ya3w7oxynAJlzGJA8qKVo1ooFbcRRXWZWuIPzP8CpL9o2RUaaPUjoErPJO7ByxNedMPiXrNuuZzGksLHA_J0WtHxSHF2V_VUsgfXfmdjH6SfJbDVPW9sMb1s"}},"nonNegotiableTerms":null,"scriptFingerprint":{"signature":null,"signatureUuid":null,"lineItemScriptChanges":[],"paymentScriptChanges":[],"shippingScriptChanges":[]},"optionalDuties":{"buyerRefusesDuties":false},"captcha":{"provider":"hcaptcha","challenge":"comparison_challenge_type","token":"P1_eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.3gAHp3Bhc3NrZXnFBHR8Nu7dGvRjHJZWFQ5ftoV87npezg1Of8eb3el70cTYlkQyU9D-A1L0NP4tG0CAjXGnhUE7yp7CHEiQ6SB4bvxrb97mbRcgYkwQ1UVBlesg8zxjgWEa7JHzZYovuDl1oSs4syrJp6A_pVyFw2iKafJcgBjQ9862V1mkIioYjJp3cU1exp4hrUU5cqNM7ZO4f9424I1WSIZMullCsXR4CI2WxK6TO05Xe_RHORal0w1Jz5YHzBMr7O0Q4ijsuOgLA5u3a0mvG8nhz88pR9LzF8s--LQkyoQs2whEvhZFEU7cCzmBHA_kjzr6uEyn-Jfes-t-WAd-1tHco-dCXrJeZhC_VhjXmNUHoSFwx7Uvn0x_o2dgzLKpUKCTD82VcjrwVUggHRZheSGkzF1HIdsE4-cqpeDgKQIIufoHySFC1HsBcexgEE7MmPcR-K1AswC5GrMmbEMFvZ1sPIlfBiIeO3M_jMRAcYgNLFdb0Wpg5QIktwpME1agAavpK_2JZz_32VmxlJCCKe61Trj9yzkHLhwvQhl8fHjh3tBDlTufveuRw00VyBO-gPKKzAWEk1cDBhcxlE3RrG3HlHrwjQSLB1TR5Nj-yPWVEb-MD8l62czV0gI_rh0Rs4M96Iv4OX4I5zf2h1T_69tuo5FDujvyM4_hIyNmagn6Kg65e7zF4MsfWbMHZDTs0yuDr5CRC3zZmsTRQM5SpIv3rHs-LAJU-tDAV8U7MvXYT1RVlkVcYPB0FVtWmaaKeBVV7X3RpsXZ_QZruPBam4txZR837_vy6w-YHn-2AhYDTjOdH0s7gNM7pcK5qrzabNtmIOrRuEEPLei8jdagG7sTEEEoc9hFNmsnPWkwxymHxExPL-CfDqUQHb1hCqSAriUin1OyjNq3BhdHFGEMjR03nui3MDssCwrRmH3Lr6dzMLGvX777Nvyb5-LG5skt8jPR48CvceG30WScw1rN92sQmgY1Ac-tqg48yuDTewBrXGo-oXttCsYLd6Gp_sqNFjgaFCPt9pxHwP196DNPIBk9zT3E2i__RiGE5NnJ517DbbLhBXXk7ZyBqi9EzggnrGc8A-f38a67VLd_3xL8ZiAvH-zVeOKSOAG5CoJgXQy90qEl6s0Tllo_PUJgcqVgHMZMweLxLmcPVSaxlpfc07p1cEFA4j1X6JLhv045diod5fNR6OFIZouPp9js8Vp6HlBTXz9HV5Uk8C0c_jZfixC-PyXGrkbnYeZh-mtNq6Z6cIcNUFY76sVhKo7QNPa3wFLn6eu-Dzz6IHI969ybTtL6Wq6xiA-wzceDbHVIyt2Fu0RTzAv0FkWrMR2Z1IkfGQb5gCfkGODE7ibKbRWrSsbpeoFdIr107Gyja4URRzf5KHOLboqgce9lP9FKyFHrAgzso6q7LsCWGlEjNcJBVzqfcs46aJw6WA6ZRigeb4ICzvAA3KluwQPxrqOWaEnM2D_th17kXnYXgeR9NSkRhqgHwlKyKSaMxdpMZv7ExwBaCD4u50-c6ZVFyjdrfq-nc2l0ZWtledkkMWYyNjIzYjEtZWIxOS00OTE2LThiNDMtMDg0YThhNzg1YjIzo2V4cM5q0n9jonBkAKVjZGF0YdQAAKZjZGF0YTLUAACia3KoM2E1YWFiNmU.MF_TS7zYc2wPr3_WzUBV1x0sOyZaDNRM5PSg0nrKHHU"},"cartMetafields":[]},"operationName":"Proposal","id":"218ca3f4634df050ead785d9692d50bc444d93ef926a6c0d820c1c01a02d474f"}'
#response = requests.post(
#    'https://shop.app/checkout/92554494298/internal/graphql/persisted',
#    params=params,
#    cookies=cookies,
#    headers=headers,
#    data=data,
#)






#1st it show 

{
    "data": {
        "receipt": {
            "id": "gid://shopify/ProcessedReceipt/779f7d9e2ff7fd9098d1a3e39febd0a0",
            "processingError": {
                "code": "CAPTCHA_REQUIRED",
                "messageUntranslated": "",
                "hasOffsitePaymentMethod": false,
                "recoveryAction": null,
                "__typename": "PaymentFailed"
            },
            "__typename": "FailedReceipt"
        }
    }
}

#after captcha i solve manually 

{
    "data": {
        "paymentSessionGenerate": {
            "userErrors": [],
            "sessionId": "spt_eThlTWZBUTEvRGM3VEd6VUFMeCt6YWlyTlZkcldxbkxqZVBlSDV6K2RrZFZla1k1UE0zVVZHUm1jL0F1VWNsT1dNNUg1OE45TUxLdmNQMDlQMzZFa0N4MmZDaVltZ2NMMElyR3I4RXZFRTV0bUtOVnRBaWFhbGtIWUxCcFpTVi9uSnp6SUdYN2d6NXAxcUpVejE0T2xlNHRTK2dJVG5tRGVMeXJxaG5PQk1XNzluSytGTk1jK2pMQzZ6SXFoNzYwMUV5dUNnajh5TmI2SFhKRm5VQmFzd2hSMHljR2E2NVM0OEwyeXI5c1JKZ0ZaVW9XclVMSFNZNmhLNjR0QTJ3NmVQRU9RNTBwdnpWTFdOaWtUWExCK2dRVmw2MnRiZ3JhU1Z0ejN0N3lpWmtBQy9tL2YzMlM1bVp0NDVBVmZwc25Pd2xyS2lLMFVDU2RxNXVhNUhRQTBPWkI2L2paTzYyMjZVVE4vcHVLbjlOZjFzN3hRU24xSzlwY1UveWdtdWgzV1hGamptSFFxbktUYVhVeGsvVTVUYmlQaXo5dFk1THlNeXRiZHIxbVZCTHVrSG5XVUkvSHB3b3laUGJGamxpeWpSdnhnaC9tQWVkaVZRcldKQTFjelN6a1ozRHFISEh5eE92cUhvN2pxU3grZ0lCbEdIa2YxY2ptTWdlYk5hQVd0aFRsY2ZDakhzVHU5UjN2NUVhbVBLZXNSV0FrYkdDRGRwQ1h4T2pyZHVCU1RjYVZ5N0lXdHo2RzBMUTZrMWpMb2U3WGJodUdtT1pxVXd2RjBJRzB3ZDFwWGFlQVZBQlhmV3NRMlc4NENWU0tRK0tTV0ZRVUQvT0pSZ2dVT1pORUtGcmh6MmJoSXAwZUdsVXU3Q1lHK1QzSzg1Mk9yR21YQnlLaTNKQU5jNEs4aUFBMlhpQzJvQXc0ZDkwMXdJYmJQZVk1dmFrdEVXVCtvdUtFUVZJQWZLcks5T1o1QUxBc2owVmdyODMvNVVPZGNxOFdNUkRpYjhUWk1LNXRrbHJqeGRyL2ZxSUN0clV5ak5MV0krSXpnUGVtK3dQMU1scEl1UTllQTA2b1RKVnhLYml2MWJZczRtR0VXYTlOOVI1QWtUaGE0SFRjWHhGUkJXR0t6RVB2NHpZWHdyUWhDRTNKbDl0MGE1NHpDQzBheThsckx4MGFEUWcxK1RtLzZONldOK2Q3QWJoVjIxTVF0a1NSZlNVcExENmZCeUkxbFR1bVRKc2N1UzZhdVJ3NFgvSkIwRXJva0trUi85UTIrTjZoZnZuL1JUZkd1M1ZvVGdveTBKWHVvUTMzUzBLWURGMlc1TDZpd1JESHJWMGhMbFhxTzVabmZTeEhKaW5NVVVsUmJRQTVHdHNJbG5ZUGUwbU1ibmVWVDhVbDloYktkb1VlbmwrQktwMVhQTmNkMkhOOVRTNmhOd1owZ1kwZEtyYldvT21vVnM2clA5WEpaQVVmSXZlUDEvT0xVTjF1UGlPMHRLMk5RQW1yOGNOTDhIMzJPVmpBbzMxbE1SZFFtalYrM24rMEpXUGgwbU5ZeEphSnZCMGpRcmttM0YyaWRMYkowcFpsVVowdHY4WTRvb0hHdmgrM04zbEFYNDdpcjR5Mjd1dHdpd2JMNnRLbmhhaWQ0bncrbFlyVXZnbzk5bjJKL3lENmY5V2hKNmZ4SGFkNGsyZ1crMC9qTzNIblliWDVFNFNWRFJhVTl4R2MvVnJzRjZkbXRkajJMa1NnSGM2UU4vOWdNK3NtazVyc2FXcTFLaEZiVjhyVkkzR1lLdUNJeW4rQTNrT3BqdVYvaHQwY1ZoZEVUY2NnMEE3N2xrTTcrVGgyc0ZUOTVUSFJaVEZUdnNNY1M4Zm9tdDhDcWJCQWcxVUs0ai9OSG9HbjNiMU51MjlBbGtDSmdyUUd5dlNEWlUyMWFkK2lreUFTem9obnB0Y1FhUHlyMElaUXM0YklIOWN6V3Fvc3h3N1FNajVHdmRQNU1pTHN1R0ozajBaMzlUbCs3TFB2R29uS1VUeGFyWVBTNGZvZlZUMFQvRFdVSDYvalgvNmo5YnNSV3A3UFpnTzdoUWZzWFpkUUY4WHRoZHY0LzNESlJnQWtTajlhdXNNblM4WVd6Q3ZBUk03VU00azF6Y3RXa3ZUTUZMTTdrMG1idTc1SVEyVlFjckdpUGsvQWpjTEdMZm9WUFg2dmplQ0Z2OEt3Tm5BRnhTUGhqNnFaSzk1MGRKcEYvbWFiR2U5Wkx3PT0tLUtuME03TXNaWWdzdjUvMUd2VnlEbVE9PQ==--cd891a6b53d3315872932a9a1137077262714373",
            "batchCheckoutSessionIds": null,
            "__typename": "PaymentSessionGeneratePayload"
        }
    }
}


#after this do pollforreceipt 8 times and show 

{
    "data": {
        "receipt": {
            "id": "gid://shopify/ProcessedReceipt/9a686188c040654dfc50eb7eda0c5988",
            "processingError": {
                "code": "INSUFFICIENT_FUNDS",
                "messageUntranslated": "",
                "hasOffsitePaymentMethod": false,
                "recoveryAction": null,
                "__typename": "PaymentFailed"
            },
            "__typename": "FailedReceipt"
        }
    }
}