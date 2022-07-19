from typing import Callable, List, Tuple

_LISTENERS: List[Tuple[int, Callable[[], None]]] = []

def add_testdb_listener(listener:  Callable[[], None], priority=0):
    _LISTENERS.append((priority, listener))
    return listener


def on_testdb(priority: int = 0):
    def register(fun: Callable[[], None]):
        return add_testdb_listener(fun, priority)

    return register

def run_testdb():
    _LISTENERS.sort(key=lambda x: -x[0])
    for listener in _LISTENERS:
        listener[1]()
