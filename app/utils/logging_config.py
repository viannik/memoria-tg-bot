import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from functools import wraps
import traceback
import inspect

import os
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
LOG_DIR = os.environ.get('LOG_DIR', 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'bot.log')
ERROR_LOG_FILE = os.path.join(LOG_DIR, 'error.log')

os.makedirs(LOG_DIR, exist_ok=True)

# Formatter
LOG_FORMAT = '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

import logging
logger = logging.getLogger('memoria_bot')
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

from logging.handlers import RotatingFileHandler
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
file_handler.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

error_file_handler = RotatingFileHandler(ERROR_LOG_FILE, maxBytes=2*1024*1024, backupCount=3, encoding='utf-8')
error_file_handler.setLevel(logging.ERROR)
error_file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

try:
    from colorlog import ColoredFormatter
    COLOR_FORMAT = '[%(asctime)s] [%(log_color)s%(levelname)s%(reset)s] [%(name)s] %(message)s'
    COLOR_LOG_COLORS = {
        'DEBUG':    'cyan',
        'INFO':     'green',
        'WARNING':  'yellow',
        'ERROR':    'red',
        'CRITICAL': 'bold_red',
    }
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    console_handler.setFormatter(ColoredFormatter(
        COLOR_FORMAT,
        DATE_FORMAT,
        log_colors=COLOR_LOG_COLORS,
        reset=True
    ))
except ImportError:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

# Apply our handlers and level to the root logger so all loggers (including aiogram) use our style
# Remove all existing handlers from root logger to guarantee only our handlers are used (required for colorlog to work)
root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
root_logger.handlers.clear()
for handler in [file_handler, error_file_handler, console_handler]:
    root_logger.addHandler(handler)

# Prevent double logging by not adding handlers to memoria_bot logger
logger.handlers.clear()
logger.propagate = True  # Ensure logs go to root logger only

# Usage:
#   Set LOG_LEVEL=INFO in your .env to see only standard log messages.
#   Set LOG_LEVEL=DEBUG for detailed debug output.

# Patch logger.error to always include traceback and function name
def error_with_traceback(msg, *args, **kwargs):
    tb = traceback.format_exc()
    stack = inspect.stack()
    func_name = stack[1].function
    if tb.strip() == 'NoneType: None':
        logger._old_error(f"[{func_name}] {msg}", *args, **kwargs)
    else:
        logger._old_error(f"[{func_name}] {msg}\nTraceback:\n{tb}", *args, **kwargs)

if not hasattr(logger, '_old_error'):
    logger._old_error = logger.error
    logger.error = error_with_traceback

def log_exception(exc: Exception, msg: str = None):
    """Log an exception with traceback."""
    tb = traceback.format_exc()
    stack = inspect.stack()
    func_name = stack[1].function
    logger._old_error(f"[{func_name}] {msg or 'Exception occurred'}: {exc}\nTraceback:\n{tb}")

def _short_repr(val):
    if isinstance(val, str):
        if len(val) > 50:
            return str(len(val))
        return repr(val)
    elif isinstance(val, (list, tuple, set)):
        return f"{type(val).__name__}({len(val)})"
    elif isinstance(val, dict):
        return f"dict({len(val)})"
    elif val is None:
        return "None"
    else:
        return repr(val)

def log_function_call(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        arg_preview = ', '.join(_short_repr(a) for a in args)
        kwarg_preview = ', '.join(f"{k}={_short_repr(v)}" for k, v in kwargs.items())
        logger.debug(f"Called {func.__name__} with args=[{arg_preview}], kwargs=[{kwarg_preview}]")
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            log_exception(exc, f"Exception in {func.__name__}")
            raise
    return wrapper

__all__ = ['logger', 'log_exception', 'log_function_call', '_short_repr']
