"""Limitador de peticiones en memoria (por IP). Suficiente para un servidor local de un solo proceso."""
import threading
import time


class Limitador:
    def __init__(self, ventana_seg, limite):
        self.ventana = ventana_seg
        self.limite = limite
        self._eventos = {}
        self._lock = threading.Lock()

    def _podar(self, clave, ahora):
        lista = [t for t in self._eventos.get(clave, []) if ahora - t < self.ventana]
        self._eventos[clave] = lista
        return lista

    def excedido(self, clave):
        with self._lock:
            return len(self._podar(clave, time.time())) >= self.limite

    def registrar(self, clave):
        with self._lock:
            ahora = time.time()
            self._podar(clave, ahora).append(ahora)

    def reiniciar(self):
        with self._lock:
            self._eventos.clear()
