"""core/exceptions.py — все исключения проекта."""


class PullerError(Exception):
    """Ошибка при получении сессионных данных через браузер."""


class PushError(Exception):
    """Ошибка при записи данных в БД или .env."""


class CredentialsExpiredError(Exception):
    """Сессионные данные устарели — нужен повторный pull."""


class UnknownProviderError(ValueError):
    """Передан неизвестный провайдер."""


class BufferEmptyError(FileNotFoundError):
    """Буферный JSON файл не найден — нужно сначала запустить pull."""


class PlaylistNotFoundError(ValueError):
    """Плейлист не найден в БД."""


class TransferError(Exception):
    """Ошибка во время переноса треков."""
