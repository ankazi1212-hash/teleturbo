import asyncio
import sys
import threading

from app.gui import TeleTurboGUI


def _run_loop(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


def main():
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=_run_loop, args=(loop,), daemon=True)
    t.start()

    app = TeleTurboGUI(loop)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        loop.call_soon_threadsafe(loop.stop)
        t.join(timeout=2)


if __name__ == "__main__":
    main()
