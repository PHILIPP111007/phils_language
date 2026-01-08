import logging
from typing import Optional


class ColoredFormatter(logging.Formatter):
    # ANSI escape code constants for different colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    RESET = "\033[0m"

    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt=fmt, datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        # Map levels to colors
        if record.levelno == logging.DEBUG:
            color = self.BLUE
        elif record.levelno == logging.INFO:
            color = self.WHITE
        elif record.levelno == logging.WARNING:
            color = self.YELLOW
        elif record.levelno == logging.ERROR:
            color = self.RED
        elif record.levelno == logging.CRITICAL:
            color = self.MAGENTA
        else:
            color = self.WHITE

        # Apply color to message
        record.msg = f"{color}{record.getMessage()}{self.RESET}"
        return super().format(record)


def setup_logger(
    name: Optional[str] = None,
    level: int = logging.DEBUG,
    filename: Optional[str] = None,
    filemode: str = "a",
    stream=True,
    fmt: str = "%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)d | %(message)s",
    datefmt: str = "%Y-%m-%d %H:%M:%S",
):
    """
    Set up a custom logger with optional configuration parameters.
    :param name: Name of the logger instance.
    :param level: Logging level threshold.
    :param filename: Log file path.
    :param filemode: File mode ('w' for overwrite, 'a' for append).
    :param stream: Enable console output.
    :param fmt: Format string for log records.
    :param datefmt: Date format string.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Console handler
    if stream:
        ch = logging.StreamHandler()
        ch.setLevel(level)
        coloured_formatter = ColoredFormatter(fmt=fmt, datefmt=datefmt)
        ch.setFormatter(coloured_formatter)
        logger.addHandler(ch)

    # File handler
    if filename:
        fh = logging.FileHandler(filename, mode=filemode)
        fh.setLevel(level)
        plain_formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)
        fh.setFormatter(plain_formatter)
        logger.addHandler(fh)

    return logger


# Использование настроенного логгера
logger = setup_logger("app")
