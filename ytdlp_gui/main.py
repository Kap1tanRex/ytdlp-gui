"""Точка входа yt-dlp GUI.

Запуск:
    python main.py
    python -m ytdlp_gui.main
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

PACKAGE_NAME = "ytdlp_gui"


def _bootstrap_package() -> None:
    """Делает пакет ``ytdlp_gui`` импортируемым при запуске файла напрямую
    (``python main.py`` из каталога пакета) — добавляет родительский
    каталог в sys.path, чтобы ниже сработал обычный ``import ytdlp_gui``.

    В собранном PyInstaller-бандле (--windowed) main.py тоже исполняется
    как __main__ с пустым __package__, но при этом уже находится внутри
    архива вместе со всем пакетом — искать соседний каталог на диске не
    нужно (и нечего: __file__ там не указывает на реальный путь). Условие
    ниже просто не срабатывает в этом случае, ``import ytdlp_gui`` находит
    пакет через собственный импортный механизм PyInstaller.
    """
    package_dir = Path(__file__).resolve().parent
    if package_dir.name == PACKAGE_NAME:
        sys.path.insert(0, str(package_dir.parent))


if __package__ in (None, ""):  # pragma: no cover
    _bootstrap_package()

# Абсолютные импорты (а не `from .app...`) — намеренно: относительные
# импорты в файле, который сам служит входной точкой (запускается как
# __main__), PyInstaller не умеет статически разрешить при анализе
# зависимостей — просто не найдёт и не включит в сборку ytdlp_gui.app,
# ytdlp_gui.gui и т.д., и собранный .exe упадёт на первом же импорте.
import ytdlp_gui  # noqa: E402,F401 - гарантирует пакет в sys.modules при любом способе запуска
from ytdlp_gui.app.application import Application  # noqa: E402
from ytdlp_gui.app.state import APP_VERSION  # noqa: E402

log = logging.getLogger(__name__)

MISSING_GUI_MESSAGE = """
Не найдены библиотеки графического интерфейса.

Установите зависимости:
    pip install -r requirements.txt

Основные пакеты: customtkinter, pillow.
На Linux может потребоваться системный пакет python3-tk.
"""


def _show_fatal_error(title: str, message: str) -> None:
    """Последний рубеж перед тем, как приложение исчезнет без следа.

    В собранном .exe (--windowed, без консоли) sys.stdout/sys.stderr
    равны None — print()/логирование в них само по себе может упасть, а
    пользователь в любом случае не увидит консоль. Поэтому при фатальной
    ошибке запуска дополнительно пробуем показать обычный диалог Tk —
    он не требует уже работающего окна приложения.
    """
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:  # noqa: BLE001 - совсем ничего показать не можем
        pass


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ytdlp-gui", description="Графический интерфейс для yt-dlp")
    parser.add_argument("urls", nargs="*", help="ссылки на видео/плейлисты для добавления при запуске")
    parser.add_argument("--config-dir", help="каталог настроек", default=None)
    parser.add_argument("--log-level", default="INFO", help="уровень логирования")
    parser.add_argument("--version", action="version", version=f"yt-dlp GUI {APP_VERSION}")
    parser.add_argument(
        "--diagnostics", action="store_true", help="вывести диагностический отчёт в консоль и выйти"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):  # pragma: no cover
            pass

    arguments = parse_arguments(argv)
    log_level = getattr(logging, arguments.log_level.upper(), logging.INFO)
    log_format = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    try:
        # Логируем сразу в файл, а не в sys.stderr: в собранном .exe
        # (--windowed) sys.stderr равен None, и штатный StreamHandler
        # логирования просто молча теряет все сообщения ещё до того, как
        # Application._setup_logging() успевает настроить свои файлы.
        startup_log = Path(tempfile.gettempdir()) / "ytdlp_gui_startup.log"
        logging.basicConfig(
            level=log_level, format=log_format,
            handlers=[logging.FileHandler(startup_log, encoding="utf-8")],
        )
    except OSError:
        logging.basicConfig(level=log_level, format=log_format)

    config_dir = Path(arguments.config_dir) if arguments.config_dir else None
    try:
        app = Application(config_dir)
    except Exception as exc:  # noqa: BLE001 - без этого приложение просто исчезнет без следа
        log.exception("Не удалось инициализировать приложение")
        _show_fatal_error("yt-dlp GUI — ошибка запуска", f"Не удалось запустить приложение:\n\n{exc}")
        return 1

    if arguments.diagnostics:
        try:
            print(app.diagnostics().to_text())
        except Exception:  # noqa: BLE001 - sys.stdout может быть недоступен в --windowed сборке
            pass
        app.shutdown()
        return 0

    try:
        from ytdlp_gui.gui.main_window import MainWindow
    except ImportError as exc:
        log.error("GUI недоступен: %s", exc)
        _show_fatal_error("yt-dlp GUI", MISSING_GUI_MESSAGE)
        return 2

    try:
        window = MainWindow(app)
    except Exception as exc:  # noqa: BLE001 - см. комментарий у Application(...)
        log.exception("Не удалось создать окно приложения")
        _show_fatal_error("yt-dlp GUI — ошибка запуска", f"Не удалось открыть окно приложения:\n\n{exc}")
        app.shutdown()
        return 1

    if arguments.urls:
        window.after(600, lambda: app.fetch_urls(arguments.urls))

    try:
        window.mainloop()
    except KeyboardInterrupt:  # pragma: no cover
        app.shutdown()
    except Exception as exc:  # noqa: BLE001 - последний рубеж главного цикла
        log.exception("Необработанная ошибка в главном цикле приложения")
        _show_fatal_error("yt-dlp GUI — ошибка", f"Произошла непредвиденная ошибка:\n\n{exc}")
        app.shutdown()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
