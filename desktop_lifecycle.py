"""Remove the notification icon before an immediate process exit."""
import logging


def stop_tray_icon(icon):
    if icon is None:
        return
    # pystray.stop() posts a message; os._exit() can run before its loop hides
    # the icon. Setting visible=False performs NIM_DELETE synchronously first.
    try:
        icon.visible = False
    except Exception:
        logging.getLogger(__name__).exception('Falha ao remover ícone da bandeja')
    try:
        icon.stop()
    except Exception:
        logging.getLogger(__name__).exception('Falha ao parar bandeja')
