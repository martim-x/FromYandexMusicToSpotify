class FetcherError(Exception):
    """Ошибка при получении сессионных данных."""


class CredentialsExpiredError(Exception):
    """Сессионные данные устарели."""


class UnknownProviderError(ValueError):
    """Неизвестный провайдер."""


class BufferEmptyError(FileNotFoundError):
    """Буферный файл не найден или пуст."""
