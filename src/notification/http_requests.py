import requests
import logging
logger = logging.getLogger('django')


def send_get_requests(urls, path, message):
    """
        Method to send GET request to the provided urls list with the message.
    """
    for url in urls:
        http_url = url + path
        logger.info("GET request to url {} with params {}".format(http_url, message))
        headers = None
        if 'headers' in message:
            headers = message.pop('headers')
        try:
            if headers:
                response = requests.get(url=http_url, params=message, headers=headers)
            else:
                response = requests.get(url=http_url, params=message)
            if response.status_code == 200:
                logger.info("success")
                logger.info(response.text)
            else:
                logger.error("Error: status {}, text: {}".format(response.status_code, response.text))
        except Exception as ex:
            logger.error(ex)


def send_post_requests(urls, path, data):
    """
        Method to send POST request to the provided urls list with the message.
    """
    for url in urls:

        http_url = url + path
        try:
            logger.info("POST request to url {} with data {}".format(http_url, data))
            headers = None
            if 'headers' in data:
                headers = data.pop('headers')
            if headers:
                response = requests.post(url=http_url, data=data, headers=headers)
            else:
                response = requests.post(url=http_url, data=data)
            if response.status_code in [200, 201]:
                logger.info("success")
                logger.info(response.text)
            else:
                logger.error("Error: status {}, text: {}".format(response.status_code, response.text))
        except Exception as e:
            logger.error(e)
