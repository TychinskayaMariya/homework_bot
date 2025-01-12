import logging
import os
import sys
import time
from http import HTTPStatus
from typing import Union

import requests
import telegram
from dotenv import load_dotenv

from exceptions import HTTPRequestError

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}
ERROR_SEND_MESSAGE = 'Отсутствует доступ к серверу Telegram'
ERROR_GET_API_ANSWER = 'Отсутствует доступ к серверу Яндекс.Практикум'
ERROR_CHECK_RESPONSE = 'Некорректный ответ API'
ERROR_PARSE_STATUS = 'Недокументированный статус проверки или отсуствие ключа'


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)


def check_tokens() -> bool:
    """Проверяет доступность переменных окружения."""
    list_tokens = [
        PRACTICUM_TOKEN,
        TELEGRAM_TOKEN,
        TELEGRAM_CHAT_ID
    ]
    return all(list_tokens)


def send_message(bot: telegram.Bot, message: str) -> None:
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Успешная отправка сообщения в Telegram')
    except Exception:
        logger.error(ERROR_SEND_MESSAGE, exc_info=True)


def get_api_answer(timestamp: int) -> Union[dict, str]:
    """Делает запрос к эндпоинту API-сервиса."""
    payload = {'from_date': timestamp}
    logger.info('Начало запроса к серверу Яндекс.Практикум')
    try:
        homework_statuses = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=payload
        )
        if homework_statuses.status_code != HTTPStatus.OK:
            raise HTTPRequestError(ERROR_GET_API_ANSWER)
        return homework_statuses.json()
    except Exception:
        raise HTTPRequestError(ERROR_GET_API_ANSWER)


def check_response(response: dict) -> list:
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(ERROR_CHECK_RESPONSE)
    if 'homeworks' not in response:
        raise KeyError(ERROR_CHECK_RESPONSE)
    if not isinstance(response.get('homeworks'), list):
        raise TypeError(ERROR_CHECK_RESPONSE)
    return response['homeworks']


def parse_status(homework: dict) -> str:
    """Извлекает статус домашней работы."""
    if 'homework_name' not in homework or 'status' not in homework:
        raise KeyError(ERROR_PARSE_STATUS)
    homework_name = homework['homework_name']
    status = homework['status']
    if not isinstance(homework_name, str) or not isinstance(status, str):
        raise TypeError(ERROR_PARSE_STATUS)
    if status not in HOMEWORK_VERDICTS:
        raise KeyError(ERROR_PARSE_STATUS)
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical(
            'Отсутствует обязательная переменная окружения.\n'
            'Программа принудительно остановлена.'
        )
        sys.exit()

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time()) - RETRY_PERIOD
    old_message = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if not homeworks:
                message = 'Ответ API пуст: нет домашних работ.'
                logger.debug(message)
            else:
                message = parse_status(homeworks[0])
            if old_message != message:
                old_message = message
                send_message(bot, message)
        except Exception as error:
            logger.error(error, exc_info=True)
            message = f'Сбой в работе программы: {error}'
            if old_message != message:
                old_message = message
                send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(filename)s/%(funcName)s %(message)s'
    )
    logger.addHandler(handler)
    handler.setFormatter(formatter)
    main()
